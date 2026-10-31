#!/usr/bin/env python3
"""Transplant the effect of a replayed event (quest hand-in, a different dialogue
choice, ...) from a "before/after" pair of PBZ slot JSONs into target slots.

  transplant.py --before B.json --after A.json --target T.json [--target T2.json ...]
                --out-dir OUT [--revert-before RB.json --revert-after RA.json]
                [--ach-before X --ach-after Y --ach-target Z] [--dry-run]
                [--keep PATH_SUBSTR ...] [--exclude SUBSTR ...]

before/after : the same playthrough right before and right after the event (ideally
               consecutive saves with only the event in between).
revert pair  : optional; a before/after pair that captures the WRONG outcome that the
               target currently carries (e.g. the bad dialogue choice). Its changes are
               undone in the target before the good outcome is applied.
ach-*        : __Achievements__.json of before / after / target container.

Writes patched copies of each target into OUT (same file names) plus OUT/plan.md,
a human-readable list of every change applied, skipped, or in conflict.
Nothing is written with --dry-run.
"""
import argparse, copy, json, os, re, sys

KEY_FIELDS = ("QuestClass", "BranchID", "ID", "Id", "Name", "Guid")
TS = re.compile(r"^\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}$")
TIME_FIELDS = ("DirtyTime", "FirstAddTime")

# Paths (joined with "/") that change on every save or only describe the player's
# position / camera / UI, not story state. Matched as regex against the path string.
NOISE = [
    r"^PBZGameSystem/(?!CompleteAddItemMobDomainNames)",
    r"^BellManager/", r"^BellSaveID$",
    r"/OwnerTransform/", r"Transform/", r"CameraRotation",
    r"^Inventory/(CurrentWeaponIndex|CurrentMainWeaponID|CurrentShaqiWeaponIndex)$",
    r"^Narrative/(Tracked|ManualTrackingOptOut)",
    r"^AISystem/", r"^TutorialHint/", r"^PBZDeathMeta/",
    r"^EventPipeline/(CurrentPlayingID|FlowLocation|FlowRotation|FlowPlaySeqID|FlowTags|"
    r"LoadedDataLayer|UnLoadedDataLayer|CurrentPlayerClass|PreSpawnPlayerClass|PreSpawnPlayerMap|CurrentWeaponName)",
    r"^LoadingTips/",
]


def pstr(path):
    out = []
    for p in path:
        out.append(f"[{p[1]}={p[2]}]" if isinstance(p, tuple) else str(p))
    return "/".join(out)


def is_noise(path, keep):
    s = pstr(path)
    if any(k in s for k in keep):
        return False
    return any(re.search(n, s) for n in NOISE)


def keyfield(a, b):
    """Field that identifies elements of both lists (present everywhere, unique within each list)."""
    both = a + b
    if not both or not all(isinstance(x, dict) for x in both):
        return None
    for k in KEY_FIELDS:
        if all(k in x for x in both):
            ok = True
            for lst in (a, b):
                vals = [json.dumps(x[k], sort_keys=True) for x in lst]
                ok &= len(set(vals)) == len(vals)
            if ok:
                return k
    return None


def diff(a, b, path=()):
    """Yield ops: (kind, path, old, new)."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in b:
            if k not in a:
                yield ("set", path + (k,), None, b[k])
            else:
                yield from diff(a[k], b[k], path + (k,))
        for k in a:
            if k not in b:
                yield ("del", path + (k,), a[k], None)
    elif isinstance(a, list) and isinstance(b, list):
        if all(not isinstance(x, (dict, list)) for x in a + b):
            for x in b:
                if x not in a:
                    yield ("ladd", path, None, x)
            for x in a:
                if x not in b:
                    yield ("ldel", path, x, None)
            return
        kf = keyfield(a, b)
        if kf:
            ia = {json.dumps(x[kf], sort_keys=True): x for x in a}
            ib = {json.dumps(x[kf], sort_keys=True): x for x in b}
            for k, x in ib.items():
                if k not in ia:
                    yield ("oadd", path + (("k", kf, x[kf]),), None, x)
                elif json.dumps(ia[k], sort_keys=True) != json.dumps(x, sort_keys=True):
                    if kf == "QuestClass" and path and path[-1] == "NarrativeSavedQuests":
                        yield ("oreplace", path + (("k", kf, x[kf]),), ia[k], x)
                    else:
                        yield from diff(ia[k], x, path + (("k", kf, x[kf]),))
            for k, x in ia.items():
                if k not in ib:
                    yield ("odel", path + (("k", kf, x[kf]),), x, None)
        elif a != b:
            yield ("replace", path, a, b)
    elif a != b:
        yield ("chg", path, a, b)


def invert(op):
    kind, path, old, new = op
    return {"set": ("del", path, new, old), "del": ("set", path, new, old),
            "ladd": ("ldel", path, new, old), "ldel": ("ladd", path, new, old),
            "oadd": ("odel", path, new, old), "odel": ("oadd", path, new, old),
            "oreplace": ("oreplace", path, new, old), "replace": ("replace", path, new, old),
            "chg": ("chg", path, new, old)}[kind]


# ---------------------------------------------------------------- navigation
def _child(node, p, create=False):
    if isinstance(p, tuple):
        _, kf, val = p
        for x in node:
            if isinstance(x, dict) and x.get(kf) == val:
                return x
        return None
    if isinstance(node, dict):
        if p not in node and create:
            node[p] = {}
        return node.get(p)
    return None


def get(root, path):
    node = root
    for p in path:
        node = _child(node, p) if node is not None else None
    return node


def parent(root, path, create=True):
    node = root
    for p in path[:-1]:
        nxt = _child(node, p, create=create)
        if nxt is None:
            return None
        node = nxt
    return node


class Patcher:
    def __init__(self, target, label):
        self.t = target
        self.label = label
        g = target.get("PBZGameSystem", {})
        self.stamp = g.get("DateTimeString")
        self.gametime = g.get("HasGameTime")
        self.log = []  # (status, text)

    def fix_times(self, v):
        """Values copied from the replay save may carry timestamps later than the
        target's own save time; clamp them so nothing appears to come from the future."""
        v = copy.deepcopy(v)
        def walk(o):
            if isinstance(o, dict):
                for k, x in o.items():
                    if k in TIME_FIELDS and isinstance(x, str) and TS.match(x) and self.stamp and x > self.stamp:
                        o[k] = self.stamp
                    else:
                        walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(v)
        return v

    def note(self, status, op, extra=""):
        kind, path, old, new = op
        s = lambda x: json.dumps(x, ensure_ascii=False)[:160]
        self.log.append((status, f"{kind} {pstr(path)} | {s(old)} => {s(new)} {extra}".rstrip()))

    def inv_amount(self, path):
        return (len(path) >= 4 and path[0] == "Inventory" and path[1] == "InventoryInfos"
                and path[-1] in ("CurrentAmount", "MaxAmount"))

    def apply(self, op):
        kind, path, old, new = op
        t = self.t
        if kind == "chg":
            cur = get(t, path)
            par = parent(t, path, create=False)
            if par is None:
                return self.note("skip", op, "(path missing in target)")
            if self.inv_amount(path) and isinstance(cur, (int, float)):
                val = max(0, cur + (new - old))
                par[path[-1]] = val
                return self.note("apply", op, f"(item amount {cur} -> {val}, delta {new - old:+})")
            if path[-1] == "GameTime" and "QuestGameTimes" in [p for p in path if isinstance(p, str)]:
                par[path[-1]] = self.gametime
                return self.note("apply", op, f"(set to target play time {self.gametime})")
            if cur == new:
                return self.note("same", op)
            par[path[-1]] = self.fix_times(new) if not (path[-1] in TIME_FIELDS) else \
                (self.stamp if isinstance(new, str) and self.stamp and new > self.stamp else new)
            return self.note("apply" if cur == old else "conflict", op,
                             "" if cur == old else f"(target had {json.dumps(cur, ensure_ascii=False)[:80]})")
        if kind == "set":
            par = parent(t, path)
            cur = par.get(path[-1]) if isinstance(par, dict) else None
            if par is None:
                return self.note("skip", op, "(parent missing)")
            if cur is None:
                par[path[-1]] = self.fix_times(new)
                return self.note("apply", op)
            if path[:2] == ("Inventory", "InventoryInfos") and len(path) == 3 and isinstance(new, dict):
                for f in ("CurrentAmount", "MaxAmount"):
                    if isinstance(new.get(f), (int, float)):
                        cur[f] = cur.get(f, 0) + new[f]
                return self.note("apply", op, "(item already owned: amounts added)")
            if cur == new:
                return self.note("same", op)
            return self.note("conflict", op, "(target already has a different value; kept target)")
        if kind == "del":
            par = parent(t, path, create=False)
            if isinstance(par, dict) and path[-1] in par:
                del par[path[-1]]
                return self.note("apply", op)
            return self.note("same", op)
        if kind in ("ladd", "ldel"):
            lst = get(t, path)
            if lst is None and kind == "ladd":
                parent(t, path)[path[-1]] = lst = []
            if not isinstance(lst, list):
                return self.note("skip", op, "(list missing)")
            if kind == "ladd":
                if new in lst:
                    return self.note("same", op)
                lst.append(new)
            else:
                if old not in lst:
                    return self.note("same", op)
                lst.remove(old)
            return self.note("apply", op)
        if kind in ("oadd", "oreplace", "odel"):
            lst = get(t, path[:-1])
            if not isinstance(lst, list):
                return self.note("skip", op, "(list missing)")
            _, kf, val = path[-1]
            idx = next((i for i, x in enumerate(lst) if isinstance(x, dict) and x.get(kf) == val), None)
            if kind == "odel":
                if idx is None:
                    return self.note("same", op)
                lst.pop(idx)
                return self.note("apply", op)
            v = self.fix_times(new)
            if isinstance(v, dict) and "GameTime" in v and self.gametime is not None:
                v["GameTime"] = min(v["GameTime"], self.gametime) if kind == "oadd" else self.gametime
            if idx is None:
                lst.append(v)
            else:
                if lst[idx] == v:
                    return self.note("same", op)
                lst[idx] = v
            return self.note("apply", op)
        if kind == "replace":
            par = parent(t, path, create=False)
            if par is None:
                return self.note("skip", op, "(parent missing)")
            par[path[-1]] = self.fix_times(new)
            return self.note("conflict" if get(t, path) != old else "apply", op, "(whole list replaced)")


def achievements_fix(target):
    """Counters that track a CompletedElements list must equal the list length."""
    ce, cnt = target.get("CompletedElements", {}), target.get("Counters", {})
    for k, lst in ce.items():
        if k in cnt and isinstance(lst, list) and cnt[k] < len(lst):
            cnt[k] = len(lst)


def load(p):
    return json.load(open(p, encoding="utf-8"))


def ops_between(b, a, keep):
    ops = list(diff(b, a))
    return [o for o in ops if not is_noise(o[1], keep)], [o for o in ops if is_noise(o[1], keep)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--target", action="append", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--revert-before")
    ap.add_argument("--revert-after")
    ap.add_argument("--ach-before"); ap.add_argument("--ach-after"); ap.add_argument("--ach-target")
    ap.add_argument("--keep", action="append", default=[], help="path substring to never treat as noise")
    ap.add_argument("--exclude", action="append", default=[],
                    help="drop event changes whose path or new value contains this substring "
                         "(use for unrelated things the player did during the replay)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    fwd, noise = ops_between(load(a.before), load(a.after), a.keep)
    excluded = [o for o in fwd if any(x in pstr(o[1]) or x in json.dumps(o[3], ensure_ascii=False) for x in a.exclude)]
    fwd = [o for o in fwd if o not in excluded]
    rev = []
    if a.revert_before and a.revert_after:
        r, _ = ops_between(load(a.revert_before), load(a.revert_after), a.keep)
        rev = [invert(o) for o in r]

    plan = ["# Transplant plan", "",
            f"- event diff: {a.before} -> {a.after}",
            f"- {len(fwd)} story/inventory changes, {len(noise)} noise changes ignored "
            f"(position, save time, bells, enemy spawners, ...)"]
    if rev:
        plan.append(f"- revert diff: {a.revert_before} -> {a.revert_after} ({len(rev)} changes undone first)")
    plan += ["", "## Event changes found", ""]
    plan += [f"- {o[0]} {pstr(o[1])} | {json.dumps(o[2], ensure_ascii=False)[:120]} => "
             f"{json.dumps(o[3], ensure_ascii=False)[:120]}" for o in fwd]
    if excluded:
        plan += ["", "## Excluded by --exclude", ""] + [f"- {o[0]} {pstr(o[1])}" for o in excluded]
    plan += ["", "## Ignored as noise", ""] + [f"- {pstr(o[1])}" for o in noise[:200]]

    os.makedirs(a.out_dir, exist_ok=True) if not a.dry_run else None
    for tp in a.target:
        t = load(tp)
        P = Patcher(t, os.path.basename(tp))
        for op in rev + fwd:
            P.apply(op)
        counts = {}
        for s, _ in P.log:
            counts[s] = counts.get(s, 0) + 1
        plan += ["", f"## Target {tp}", "", f"result: {counts}", ""] + [f"- [{s}] {x}" for s, x in P.log]
        print(f"{tp}: {counts}")
        if not a.dry_run:
            out = os.path.join(a.out_dir, os.path.basename(tp))
            open(out, "w", encoding="utf-8").write(json.dumps(t, ensure_ascii=False, separators=(",", ":")))

    if a.ach_before and a.ach_after and a.ach_target:
        ops, _ = ops_between(load(a.ach_before), load(a.ach_after), a.keep)
        ops = [o for o in ops if not (o[0] == "chg" and o[1][:1] == ("Counters",))]  # recomputed below
        t = load(a.ach_target)
        P = Patcher(t, "achievements")
        for op in ops:
            if op[0] in ("ldel", "del", "odel"):
                continue  # never take achievements away
            P.apply(op)
        achievements_fix(t)
        plan += ["", f"## Achievements {a.ach_target}", ""] + [f"- [{s}] {x}" for s, x in P.log]
        print(f"{a.ach_target}: {len(P.log)} achievement changes")
        if not a.dry_run:
            open(os.path.join(a.out_dir, os.path.basename(a.ach_target)), "w", encoding="utf-8").write(
                json.dumps(t, ensure_ascii=False, separators=(",", ":")))

    text = "\n".join(plan)
    if a.dry_run:
        print(text)
    else:
        open(os.path.join(a.out_dir, "plan.md"), "w", encoding="utf-8").write(text)
        print(f"plan written to {os.path.join(a.out_dir, 'plan.md')}")


if __name__ == "__main__":
    main()
