#!/usr/bin/env python3
"""Phantom Blade Zero (影之刃零) PBZSaveGame.sav toolkit.

Container format (reverse-engineered by the open-source SaveSmith project,
https://github.com/gundamff/SaveSmith, MIT):

  outer header (12 B): "PBZS" | u16 0x0103 | u16 slot_count | u32 dir_block_len
  directory block    : sealed PBZS block, plaintext = outer header copy +
                       per slot: u16 name_len | name | u8 compression | u8 sealed
                                 | u32 uncompressed | u32 rel_offset | u32 block_len
  slot blocks        : sealed PBZS blocks, contiguous
  sealed block       : "PBZS" 01 <sealed> 00 00 | nonce(12) | tag(16) | AES-256-GCM ciphertext
  compression        : 0 = none, 1 = zlib, 2 = Oodle (Mermaid). Payload is UTF-8 JSON.

The game writes Oodle; we write zlib (compression=1), which the game loads
(the same approach SaveSmith uses).

Sub-commands
  unpack  SAV OUTDIR [--ooz-dir D]   decrypt+decompress every slot to OUTDIR/<slot>.json
  unpack-tree SAVEDIR OUTROOT        unpack every *.sav under a save folder (incl. 1RealTime/2Hourly/3Daily)
  summary DIR...                     table of slots: save time, play time, level, bell, quest counts
  pack    ORIG_SAV JSONDIR OUT_SAV   rebuild ORIG_SAV, re-encoding only slots whose JSON changed
  backup  SAVEDIR [--to DIR]         zip the whole save folder with a timestamp
  update-key SAV [--source URL]      after a game update: fetch the newest key from SaveSmith,
                                     keep it only if it decrypts SAV (saved to ~/.cache/pbz-save-rescue/key.txt)
  find                               locate PBZ save folders on this computer (Steam libraries, Proton)
  install SAVEDIR NEW_SAV            back up SAVEDIR, then copy NEW_SAV in as PBZSaveGame.sav
                                     (game must be closed; ask the user first)
"""
import argparse, datetime, glob, hashlib, json, os, shutil, struct, subprocess, sys, tempfile, zipfile, zlib

BUILTIN_KEY = "15a1fe0f55e0eb298e7c9461548351696a2a0700ed2d17ba1f871457e8f93e2d"  # PBZS_BUILD 26266538
CACHE_DIR = os.path.expanduser("~/.cache/pbz-save-rescue")
KEY_FILE = os.path.join(CACHE_DIR, "key.txt")  # written by `update-key`, overrides the built-in key
# Where newer keys are published when the game updates (SaveSmith keeps this file current):
KEY_UPSTREAM = [
    "https://raw.githubusercontent.com/gundamff/SaveSmith/main/src/games/phantom-blade-zero/crypto/pbzsCrypto.ts",
    "https://raw.githubusercontent.com/gundamff/SaveSmith/master/src/games/phantom-blade-zero/crypto/pbzsCrypto.ts",
]
KEY_UPSTREAM_HUMAN = "https://github.com/gundamff/SaveSmith/blob/main/src/games/phantom-blade-zero/crypto/pbzsCrypto.ts"


def _load_key():
    k = os.environ.get("PBZ_KEY")
    if not k and os.path.exists(KEY_FILE):
        k = open(KEY_FILE).read().split()[0]
    return bytes.fromhex(k or BUILTIN_KEY), ("PBZ_KEY env" if os.environ.get("PBZ_KEY") else
                                             KEY_FILE if k else "built-in key (PBZS_BUILD 26266538)")


KEY, KEY_SOURCE = _load_key()
HERE = os.path.dirname(os.path.abspath(__file__))
OOZ_WASM_SHA256 = "a4207524a1edee6a67bd8fb3707011adb32a244595149d3ddf86fddedbc32a94"
DEFAULT_OOZ_DIRS = [
    os.environ.get("PBZ_OOZ_DIR", ""),
    os.path.expanduser("~/.cache/pbz-save-rescue/oozextract"),
]


# ---------------------------------------------------------------- crypto
def _aes(key=None):
    key = key or KEY
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        a = AESGCM(key)
        return (lambda n, c, t: a.decrypt(n, c + t, None),
                lambda n, p: (lambda e: (e[:-16], e[-16:]))(a.encrypt(n, p, None)))
    except ImportError:
        from Crypto.Cipher import AES  # pycryptodome
        def dec(n, c, t):
            return AES.new(key, AES.MODE_GCM, nonce=n).decrypt_and_verify(c, t)
        def enc(n, p):
            return AES.new(key, AES.MODE_GCM, nonce=n).encrypt_and_digest(p)
        return dec, enc


_DEC, _ENC = _aes()


class PbzError(Exception):
    pass


def unseal(block):
    if block[:4] != b"PBZS" or block[4] != 1:
        raise PbzError("bad block header")
    if block[5] == 0:
        return block[8:]
    try:
        return _DEC(block[8:20], block[36:], block[20:36])
    except Exception:
        raise PbzError(f"AES-GCM authentication failed with the {KEY_SOURCE}. The game was probably "
                       "updated and uses a new key: run `pbzsave.py update-key <this .sav>` to fetch and test "
                       f"the newest key from {KEY_UPSTREAM_HUMAN}")


def seal(plain):
    nonce = os.urandom(12)
    c, t = _ENC(nonce, plain)
    return b"PBZS\x01\x01\x00\x00" + nonce + t + c


# ---------------------------------------------------------------- container
def parse(raw):
    if raw[:4] != b"PBZS" or struct.unpack_from("<H", raw, 4)[0] != 0x0103:
        raise PbzError("not a PBZS v3 container")
    count, dlen = struct.unpack_from("<HI", raw, 6)
    d = unseal(raw[12:12 + dlen])
    if d[:12] != raw[:12]:
        raise PbzError("directory header copy mismatch")
    cur, ents = 12, []
    for _ in range(count):
        nl, = struct.unpack_from("<H", d, cur); cur += 2
        name = d[cur:cur + nl].decode(); cur += nl
        comp, sealed = d[cur], d[cur + 1]; cur += 2
        us, off, ln = struct.unpack_from("<III", d, cur); cur += 12
        ents.append(dict(name=name, comp=comp, sealed=sealed, us=us, off=off, ln=ln))
    base = 12 + dlen
    for e in ents:
        e["blk"] = raw[base + e["off"]: base + e["off"] + e["ln"]]
        if len(e["blk"]) != e["ln"]:
            raise PbzError(f"slot {e['name']} truncated")
    return ents


def build(ents):
    off = 0
    for e in ents:
        e["off"], e["ln"] = off, len(e["blk"])
        off += e["ln"]
    dlen = 12 + sum(16 + len(e["name"].encode()) for e in ents) + 36
    hdr = b"PBZS" + struct.pack("<HHI", 0x0103, len(ents), dlen)
    dp = bytearray(hdr)
    for e in ents:
        n = e["name"].encode()
        dp += struct.pack("<H", len(n)) + n + bytes([e["comp"], e["sealed"]])
        dp += struct.pack("<III", e["us"], e["off"], e["ln"])
    dblk = seal(bytes(dp))
    assert len(dblk) == dlen
    return hdr + dblk + b"".join(e["blk"] for e in ents)


# ---------------------------------------------------------------- oodle
def find_ooz_dir(explicit=None):
    for d in [explicit] + DEFAULT_OOZ_DIRS:
        if d and os.path.isfile(os.path.join(d, "oozextract_bg.wasm")):
            wasm = open(os.path.join(d, "oozextract_bg.wasm"), "rb").read()
            if hashlib.sha256(wasm).hexdigest() != OOZ_WASM_SHA256:
                raise PbzError(f"{d}/oozextract_bg.wasm SHA-256 mismatch; refusing to run it")
            return d
    raise PbzError("Oodle decoder not installed. Run scripts/setup_oodle.py (needs network; Node.js to run it), "
                   "or pass --ooz-dir / set PBZ_OOZ_DIR to a folder holding oozextract.js + oozextract_bg.wasm")


def decompress_many(jobs, ooz_dir=None):
    """jobs: list of (compression, data, uncompressed_size). Returns list of bytes."""
    out = [None] * len(jobs)
    oodle = []
    for i, (comp, data, us) in enumerate(jobs):
        if comp == 0:
            out[i] = data
        elif comp == 1:
            out[i] = zlib.decompress(data)
        elif comp == 2:
            oodle.append(i)
        else:
            raise PbzError(f"unknown compression {comp}")
    if oodle:
        d = find_ooz_dir(ooz_dir)
        with tempfile.TemporaryDirectory() as tmp:
            spec = []
            for i in oodle:
                p = os.path.join(tmp, f"{i}.in")
                open(p, "wb").write(jobs[i][1])
                spec.append({"in": p, "out": p + ".out", "size": jobs[i][2]})
            json.dump(spec, open(os.path.join(tmp, "jobs.json"), "w"))
            subprocess.run(["node", os.path.join(HERE, "ooz_decode.mjs"), d, os.path.join(tmp, "jobs.json")],
                           check=True)
            for i, s in zip(oodle, spec):
                out[i] = open(s["out"], "rb").read()
    for i, (_, _, us) in enumerate(jobs):
        if len(out[i]) != us:
            raise PbzError("decompressed size mismatch")
    return out


def read_slots(path, ooz_dir=None):
    """-> (entries, {slot_name: payload bytes})"""
    ents = parse(open(path, "rb").read())
    plains = decompress_many([(e["comp"], unseal(e["blk"]), e["us"]) for e in ents], ooz_dir)
    return ents, {e["name"]: p for e, p in zip(ents, plains)}


# ---------------------------------------------------------------- commands
def cmd_unpack(sav, outdir, ooz_dir=None):
    ents, slots = read_slots(sav, ooz_dir)
    os.makedirs(outdir, exist_ok=True)
    meta = {"source": os.path.abspath(sav), "slots": []}
    for e in ents:
        open(os.path.join(outdir, e["name"] + ".json"), "wb").write(slots[e["name"]])
        meta["slots"].append({k: e[k] for k in ("name", "comp", "sealed", "us", "ln")})
    json.dump(meta, open(os.path.join(outdir, "_meta.json"), "w"), indent=1)
    return ents


def cmd_unpack_tree(savedir, outroot, ooz_dir=None):
    n = 0
    for sav in sorted(glob.glob(os.path.join(savedir, "**", "*.sav"), recursive=True)):
        rel = os.path.relpath(sav, savedir)
        out = os.path.join(outroot, rel[:-4].replace(os.sep, "__"))
        try:
            cmd_unpack(sav, out, ooz_dir)
            n += 1
        except PbzError as ex:
            print(f"skip {rel}: {ex}", file=sys.stderr)
    print(f"unpacked {n} save files into {outroot}")


def slot_info(path):
    d = json.load(open(path, encoding="utf-8"))
    g = d.get("PBZGameSystem")
    if not g:
        return None
    t = g.get("HasGameTime", 0)
    qs = d.get("Narrative", {}).get("NarrativeSavedQuests", [])
    cnt = {}
    for q in qs:
        k = q.get("QuestCompletion", "").split("::")[-1]
        cnt[k] = cnt.get(k, 0) + 1
    return dict(file=path, saved=g.get("DateTimeString"), play=t,
                playstr=f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}",
                level=g.get("CurrentLevelName"), bell=g.get("LastSaveActorID"),
                cycle=g.get("CycleCount", 0), quests=cnt)


def cmd_summary(dirs):
    rows = []
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            if os.path.basename(f).startswith("_"):
                continue
            i = slot_info(f)
            if i:
                rows.append(i)
    rows.sort(key=lambda r: (r["cycle"], r["play"]))
    for r in rows:
        print(f"{r['saved']}  play {r['playstr']:>9}  {r['level'] or '':20s} {str(r['bell']):16s} "
              f"{r['file']}  {r['quests']}")


def cmd_pack(orig, jsondir, out, ooz_dir=None):
    ents, slots = read_slots(orig, ooz_dir)
    changed = []
    for e in ents:
        p = os.path.join(jsondir, e["name"] + ".json")
        if not os.path.exists(p):
            continue
        new = open(p, "rb").read()
        if new == slots[e["name"]]:
            continue
        new_obj = json.loads(new)  # must be valid JSON
        if new_obj == json.loads(slots[e["name"]]):
            continue
        e.update(comp=1, sealed=1, us=len(new), blk=seal(zlib.compress(new, 9)))
        slots[e["name"]] = new
        changed.append(e["name"])
    data = build(ents)
    # verify by reading back
    ents2, slots2 = read_slots_bytes(data, ooz_dir)
    orig_ents = parse(open(orig, "rb").read())
    for a, b in zip(orig_ents, ents2):
        assert a["name"] == b["name"]
        if a["name"] not in changed:
            assert a["blk"] == b["blk"], a["name"]
        else:
            json.loads(slots2[a["name"]])
            assert slots2[a["name"]] == slots[a["name"]]
    if os.path.abspath(out) == os.path.abspath(orig):
        raise PbzError("refusing to overwrite the original; write to a new path")
    open(out, "wb").write(data)
    print(f"wrote {out} ({len(data)} bytes); re-encoded slots: {changed or 'none'}; verified OK")
    return changed


def read_slots_bytes(data, ooz_dir=None):
    ents = parse(data)
    # only zlib/raw slots need decoding for verification of changed slots; oodle untouched ones compared by bytes
    plains = {}
    for e in ents:
        if e["comp"] in (0, 1):
            plains[e["name"]] = decompress_many([(e["comp"], unseal(e["blk"]), e["us"])])[0]
        else:
            unseal(e["blk"])  # authenticate
    return ents, plains


def cmd_update_key(sav, source=None):
    """Fetch the newest key published upstream, keep it only if it decrypts SAV."""
    import re, urllib.request
    global _DEC, _ENC, KEY, KEY_SOURCE
    raw = open(sav, "rb").read()
    count, dlen = struct.unpack_from("<HI", raw, 6)
    dirblock = raw[12:12 + dlen]
    candidates = []
    for url in ([source] if source else KEY_UPSTREAM):
        try:
            text = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
        except Exception as ex:
            print(f"cannot fetch {url}: {ex}", file=sys.stderr)
            continue
        candidates += [(m, url) for m in re.findall(r"\b[0-9a-fA-F]{64}\b", text)]
    if not candidates:
        raise PbzError("no key found upstream; open " + KEY_UPSTREAM_HUMAN +
                       " in a browser and pass the 64-hex key with PBZ_KEY=<hex>")
    for k, url in candidates:
        dec, _ = _aes(bytes.fromhex(k))
        try:
            dec(dirblock[8:20], dirblock[36:], dirblock[20:36])
        except Exception:
            continue
        os.makedirs(CACHE_DIR, exist_ok=True)
        open(KEY_FILE, "w").write(k.lower() + "\n")
        KEY, KEY_SOURCE = bytes.fromhex(k), KEY_FILE
        _DEC, _ENC = _aes(KEY)
        print(f"new key verified against {sav} and saved to {KEY_FILE} (from {url})")
        return k
    raise PbzError("none of the upstream keys decrypts this save yet; the community may not have "
                   "published the new key. Check " + KEY_UPSTREAM_HUMAN + " later.")


def cmd_backup(savedir, to=None):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    to = to or os.path.join(os.path.dirname(os.path.abspath(savedir)), "pbz-save-backups")
    os.makedirs(to, exist_ok=True)
    dst = os.path.join(to, f"{os.path.basename(os.path.abspath(savedir))}-backup-{stamp}.zip")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(savedir):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, savedir))
    print(f"backup written: {dst}")
    return dst


def _steam_roots():
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                   (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        roots.append(winreg.QueryValueEx(k, val)[0])
                except OSError:
                    pass
        except ImportError:
            pass
        roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        roots += [os.path.expanduser(x) for x in ("~/.steam/steam", "~/.local/share/Steam",
                  "~/.var/app/com.valvesoftware.Steam/.local/share/Steam", "~/Library/Application Support/Steam")]
    libs = []
    for r in roots:
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            import re
            libs += [m.replace("\\\\", "\\") for m in re.findall(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="ignore").read())]
        libs.append(r)
    out = []
    for l in libs:
        if os.path.isdir(l) and os.path.normcase(os.path.abspath(l)) not in [os.path.normcase(os.path.abspath(x)) for x in out]:
            out.append(l)
    return out


def cmd_find():
    cands = []
    for lib in _steam_roots():
        cands += glob.glob(os.path.join(lib, "steamapps", "common", "*", "ProjectPBZ", "Saved", "SaveGames", "**", "PBZSaveGame.sav"), recursive=True)
        cands += glob.glob(os.path.join(lib, "steamapps", "compatdata", "4115450", "pfx", "**", "PBZSaveGame.sav"), recursive=True)
    for base in (os.environ.get("LOCALAPPDATA"), os.path.expanduser("~/Documents"), os.path.expanduser("~/Saved Games")):
        if base:
            cands += glob.glob(os.path.join(base, "*PBZ*", "**", "PBZSaveGame.sav"), recursive=True)
    seen, rows = set(), []
    for c in cands:
        d = os.path.dirname(os.path.abspath(c))
        if os.path.basename(d) in ("1RealTime", "2Hourly", "3Daily") or d in seen:
            continue
        seen.add(d)
        rows.append((os.path.getmtime(c), d))
    if not rows:
        print("没找到。请让用户在 Steam 里右键游戏 → 管理 → 浏览本地文件，再进入 ProjectPBZ\\Saved\\SaveGames\\Steam\\<一串数字> 文件夹，把路径告诉你。")
        return []
    rows.sort(reverse=True)
    for t, d in rows:
        print(f"{datetime.datetime.fromtimestamp(t):%Y-%m-%d %H:%M}  {d}")
    print("（最上面这个最近修改过，通常就是要用的存档文件夹；文件夹名是用户的 SteamID64。）")
    return [d for _, d in rows]


def cmd_install(savedir, new_sav, ooz_dir=None):
    read_slots(new_sav, ooz_dir)  # refuse to install something the toolkit cannot read back
    dst = os.path.join(savedir, "PBZSaveGame.sav")
    if not os.path.isfile(dst):
        raise PbzError(f"{dst} not found; is {savedir} really the save folder?")
    if os.path.abspath(new_sav) == os.path.abspath(dst):
        raise PbzError("NEW_SAV is already the installed file")
    bk = cmd_backup(savedir)
    shutil.copyfile(new_sav, dst)
    print(f"installed {new_sav} -> {dst}")
    print(f"如需还原：退出游戏，把 {bk} 里的 PBZSaveGame.sav 解压回 {savedir} 即可。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ooz-dir")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("unpack"); p.add_argument("sav"); p.add_argument("outdir")
    p = sp.add_parser("unpack-tree"); p.add_argument("savedir"); p.add_argument("outroot")
    p = sp.add_parser("summary"); p.add_argument("dirs", nargs="+")
    p = sp.add_parser("pack"); p.add_argument("orig"); p.add_argument("jsondir"); p.add_argument("out")
    p = sp.add_parser("backup"); p.add_argument("savedir"); p.add_argument("--to")
    p = sp.add_parser("update-key"); p.add_argument("sav"); p.add_argument("--source", help="URL of a file containing the key")
    sp.add_parser("find")
    p = sp.add_parser("install"); p.add_argument("savedir"); p.add_argument("new_sav")
    a = ap.parse_args()
    try:
        if a.cmd == "unpack":
            ents = cmd_unpack(a.sav, a.outdir, a.ooz_dir)
            print(f"unpacked {len(ents)} slots: {[e['name'] for e in ents]}")
        elif a.cmd == "unpack-tree":
            cmd_unpack_tree(a.savedir, a.outroot, a.ooz_dir)
        elif a.cmd == "summary":
            cmd_summary(a.dirs)
        elif a.cmd == "pack":
            cmd_pack(a.orig, a.jsondir, a.out, a.ooz_dir)
        elif a.cmd == "backup":
            cmd_backup(a.savedir, a.to)
        elif a.cmd == "update-key":
            cmd_update_key(a.sav, a.source)
        elif a.cmd == "find":
            cmd_find()
        elif a.cmd == "install":
            cmd_install(a.savedir, a.new_sav, a.ooz_dir)
    except PbzError as ex:
        sys.exit(f"error: {ex}")


if __name__ == "__main__":
    main()
