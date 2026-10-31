#!/usr/bin/env python3
"""Achievement helper for 影之刃零 (PBZ).

How achievements work (what we can rely on):
  * The real achievement record lives on Steam. The game unlocks a Steam achievement
    at the moment its condition is met in-game, and Steam keeps it forever, no matter
    which save is loaded later.
  * The save's __Achievements__ slot is only the game's local bookkeeping:
    UnlockedIds, progress Counters, CompletedElements (e.g. accessories collected),
    PlatformPending (probably unlocks waiting to be pushed to Steam while offline).
    It is GLOBAL, but every backup .sav carries its own (older) copy.
  * So editing the save alone does not unlock anything on Steam. The way to win back a
    lost achievement is to let the game itself fire it: replay from a backup and meet
    the condition again (with Steam online). Because progress counters in an old backup
    are behind, merge the latest __Achievements__ into the backup first
    (`prepare-replay`), otherwise collection achievements may fall short.

Commands (each prints what to do next):
  status   UNPACKED_ROOT                    local achievement state + when each ID first appeared
  prepare-replay BACKUP_SAV LATEST_SAV OUT  copy of BACKUP_SAV whose __Achievements__ = latest ∪ backup
  steam    STEAMID64 [--appid 4115450] [--unpacked UNPACKED_ROOT]
                                            list locked/unlocked achievements from the public Steam
                                            profile XML and compare with the local save (needs network,
                                            public game details; ask the user before fetching)
"""
import argparse, glob, json, os, sys, urllib.request
import xml.etree.ElementTree as ET

PBZ_APPID = "4115450"  # Phantom Blade Zero on Steam (steamdb.info/app/4115450)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbzsave


def load_ach_snapshots(root):
    """-> list of (DateTimeString of newest slot in that container, achievements dict, container dir)"""
    out = []
    for d in sorted(glob.glob(os.path.join(root, "*"))):
        a = os.path.join(d, "__Achievements__.json")
        if not os.path.exists(a):
            continue
        newest = ""
        for f in glob.glob(os.path.join(d, "*Save*.json")):
            try:
                g = json.load(open(f, encoding="utf-8")).get("PBZGameSystem", {})
                newest = max(newest, g.get("DateTimeString", ""))
            except Exception:
                pass
        out.append((newest, json.load(open(a, encoding="utf-8")), d))
    out.sort(key=lambda x: x[0])
    return out


def merge(latest, older):
    """Union of two __Achievements__ dicts; never loses progress."""
    m = json.loads(json.dumps(latest))
    for i in older.get("UnlockedIds", []):
        if i not in m.setdefault("UnlockedIds", []):
            m["UnlockedIds"].append(i)
    for k, lst in older.get("CompletedElements", {}).items():
        dst = m.setdefault("CompletedElements", {}).setdefault(k, [])
        for x in lst:
            if x not in dst:
                dst.append(x)
    for k, v in older.get("Counters", {}).items():
        m.setdefault("Counters", {})[k] = max(m["Counters"].get(k, 0), v)
    for k, lst in m.get("CompletedElements", {}).items():
        if k in m.get("Counters", {}) and m["Counters"][k] < len(lst):
            m["Counters"][k] = len(lst)
    for x in older.get("PlatformPending", []):
        if x not in m.setdefault("PlatformPending", []):
            m["PlatformPending"].append(x)
    return m


def cmd_status(root):
    snaps = load_ach_snapshots(root)
    if not snaps:
        sys.exit("no __Achievements__.json found; run pbzsave.py unpack-tree first")
    t, cur, d = snaps[-1]
    print(f"最新成就数据（来自 {os.path.basename(d)}，最新槽位存档时间 {t}）")
    print(f"  已解锁 {len(cur.get('UnlockedIds', []))} 个：{', '.join(cur.get('UnlockedIds', []))}")
    for k, v in cur.get("Counters", {}).items():
        els = cur.get("CompletedElements", {}).get(k)
        print(f"  进度 {k} = {v}" + (f"，已收集：{', '.join(els)}" if els else ""))
    print(f"  待推送给平台（PlatformPending）：{cur.get('PlatformPending') or '无'}")
    print("\n各成就首次出现在本地记录的时间：")
    seen = {}
    for t, a, d in snaps:
        for i in a.get("UnlockedIds", []):
            seen.setdefault(i, (t, os.path.basename(d)))
    for i, (t, d) in sorted(seen.items(), key=lambda x: x[1]):
        print(f"  {i}: {t}  ({d})")
    print("\n下一步：想知道 Steam 上哪些还没解锁、各叫什么名字，请运行 steam 子命令（需要用户同意联网）；"
          "想补回某个成就，按 SKILL.md 的「成就补救」一节操作。")


def cmd_prepare(backup, latest, out, ooz_dir=None):
    ents_b, slots_b = pbzsave.read_slots(backup, ooz_dir)
    _, slots_l = pbzsave.read_slots(latest, ooz_dir)
    if "__Achievements__" not in slots_l or "__Achievements__" not in slots_b:
        sys.exit("both files need an __Achievements__ slot")
    a_b = json.loads(slots_b["__Achievements__"])
    a_l = json.loads(slots_l["__Achievements__"])
    m = merge(a_l, a_b)
    tmp = out + ".tmpdir"
    os.makedirs(tmp, exist_ok=True)
    open(os.path.join(tmp, "__Achievements__.json"), "w", encoding="utf-8").write(
        json.dumps(m, ensure_ascii=False, separators=(",", ":")))
    pbzsave.cmd_pack(backup, tmp, out, ooz_dir)
    os.remove(os.path.join(tmp, "__Achievements__.json"))
    os.rmdir(tmp)
    print(f"成就进度：备份里原有 {a_b.get('Counters')}，合并后 {m.get('Counters')}；"
          f"已解锁 {len(a_b.get('UnlockedIds', []))} -> {len(m.get('UnlockedIds', []))}")
    print(f"下一步：把 {out} 改名为 PBZSaveGame.sav 交给用户，让他在 Steam 在线时读档重玩，"
          f"达成条件后成就会由游戏直接解锁到 Steam。")


def cmd_steam(steamid, appid, root=None):
    url = f"https://steamcommunity.com/profiles/{steamid}/stats/{appid}/achievements/?xml=1&l=schinese"
    try:
        data = urllib.request.urlopen(url, timeout=30).read()
        tree = ET.fromstring(data)
    except Exception as ex:
        sys.exit(f"无法读取 {url}：{ex}\n（需要网络，且用户的 Steam 个人资料与游戏详情设为公开）")
    if tree.find("error") is not None:
        sys.exit(f"Steam 返回错误：{tree.findtext('error')}（个人资料或游戏详情可能未公开）")
    local = set()
    if root:
        snaps = load_ach_snapshots(root)
        if snaps:
            local = set(snaps[-1][1].get("UnlockedIds", []))
    locked, unlocked = [], []
    for a in tree.iter("achievement"):
        api = (a.findtext("apiname") or "").strip()
        row = (api, (a.findtext("name") or "").strip(), (a.findtext("description") or "").strip())
        (unlocked if a.get("closed") == "1" else locked).append(row)
    print(f"Steam 上已解锁 {len(unlocked)} 个，未解锁 {len(locked)} 个\n")
    print("未解锁：")
    for api, name, desc in locked:
        flag = "  ← 本地存档记为已解锁，可能是当时离线没推送上去" if api.upper() in {x.upper() for x in local} else ""
        print(f"  {api}  {name}：{desc}{flag}")
    if local:
        steam_up = {u[0].upper() for u in unlocked}
        only_local = [x for x in local if x.upper() not in steam_up and x.upper() not in {l[0].upper() for l in locked}]
        if only_local:
            print(f"\n本地有、Steam 列表里对不上名字的 ID：{only_local}（apiname 命名可能不同，需人工对照）")
    print("\n下一步：对每个想补的成就，判断它属于哪类（见 SKILL.md「成就补救」表格），再按对应路线操作。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ooz-dir")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("status"); p.add_argument("root")
    p = sp.add_parser("prepare-replay"); p.add_argument("backup"); p.add_argument("latest"); p.add_argument("out")
    p = sp.add_parser("steam"); p.add_argument("steamid"); p.add_argument("--appid", default=PBZ_APPID); p.add_argument("--unpacked")
    a = ap.parse_args()
    if a.cmd == "status":
        cmd_status(a.root)
    elif a.cmd == "prepare-replay":
        cmd_prepare(a.backup, a.latest, a.out, a.ooz_dir)
    else:
        cmd_steam(a.steamid, a.appid, a.unpacked)


if __name__ == "__main__":
    main()
