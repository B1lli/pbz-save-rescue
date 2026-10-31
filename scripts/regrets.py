#!/usr/bin/env python3
"""Find "regrets" (failed / locked / stalled quests) in the latest PBZ save and,
using every older snapshot (other slots + 1RealTime/2Hourly/3Daily backups),
locate the last point where each one could still be saved.

Usage: regrets.py UNPACKED_ROOT [--json out.json] [--quest NAME]
  UNPACKED_ROOT = output of `pbzsave.py unpack-tree` (one sub-folder per .sav)
"""
import argparse, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES_FILE = os.path.join(HERE, "..", "references", "quest_names.json")


def short(qc):
    return qc.rsplit("/", 1)[-1].split(".")[0]


def qtype(qc):
    parts = qc.split("/")
    return parts[-2] if len(parts) > 2 else ""


def load_names():
    try:
        return json.load(open(NAMES_FILE, encoding="utf-8"))
    except Exception:
        return {}


def enum(v):
    return (v or "").split("::")[-1]


def load_snapshots(root):
    snaps = {}
    for f in sorted(glob.glob(os.path.join(root, "*", "*.json"))):
        if os.path.basename(f).startswith("_"):
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        g = d.get("PBZGameSystem")
        if not g or "Narrative" not in d:
            continue
        key = (g.get("CycleCount", 0), g.get("HasGameTime", 0), g.get("DateTimeString"))
        meta_p = os.path.join(os.path.dirname(f), "_meta.json")
        src = json.load(open(meta_p)).get("source") if os.path.exists(meta_p) else os.path.dirname(f)
        loc = {"sav": src, "slot": os.path.basename(f)[:-5], "json": f}
        if key in snaps:
            snaps[key]["locs"].append(loc)
            continue
        snaps[key] = {"key": key, "data": d, "locs": [loc]}
    return [snaps[k] for k in sorted(snaps)]


def quests(d):
    return {q["QuestClass"]: q for q in d["Narrative"].get("NarrativeSavedQuests", [])}


def tags(d):
    t = d.get("EventPipeline", {}).get("GlobalTags", [])
    return set(t) if isinstance(t, list) else set()


def fmt_play(t):
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def snap_label(s):
    g = s["data"]["PBZGameSystem"]
    return f"{g.get('DateTimeString')} (游戏时长 {fmt_play(g.get('HasGameTime', 0))}, 存档点 {g.get('LastSaveActorID')})"


def best_loc(s):
    # prefer a manual slot, then the newest backup file
    locs = sorted(s["locs"], key=lambda l: (not l["slot"].startswith("Manual"), l["sav"]))
    return locs[0]


def branch_str(q):
    return ", ".join(f"{b['BranchID']}:{enum(b.get('BranchType'))}" for b in q.get("QuestBranches", []))


def items_near(d, q, window=15):
    """Inventory items picked up shortly before a branch of q changed -> likely quest items."""
    times = {b.get("DirtyTime") for b in q.get("QuestBranches", []) if b.get("DirtyTime", "0001").startswith("2")}
    import datetime as dt
    def p(s):
        try:
            return dt.datetime.strptime(s, "%Y.%m.%d-%H.%M.%S")
        except Exception:
            return None
    tt = [p(t) for t in times if p(t)]
    out = []
    for k, v in d.get("Inventory", {}).get("InventoryInfos", {}).items():
        fa = p(v.get("FirstAddTime", ""))
        if fa and any(0 <= (t - fa).total_seconds() <= window for t in tt):
            out.append((k, v.get("CurrentAmount")))
    return out


def analyse(root, only=None):
    names = load_names()
    snaps = load_snapshots(root)
    if not snaps:
        sys.exit("no snapshots found; run pbzsave.py unpack-tree first")
    latest = snaps[-1]
    cyc = latest["key"][0]
    timeline = [s for s in snaps if s["key"][0] == cyc]
    lq = quests(latest["data"])
    report = {"latest": {"label": snap_label(latest), "locs": latest["locs"]}, "regrets": [], "started": [], "untaken": []}

    for qc, q in lq.items():
        if only and only not in qc:
            continue
        status = enum(q.get("QuestCompletion"))
        locked = [b["BranchID"] for b in q.get("QuestBranches", []) if enum(b.get("BranchType")) == "BranchLocked"]
        if status != "QC_Failed" and not locked:
            if status == "QC_Started" and qtype(qc) != "Tutorial":
                last = max((b.get("DirtyTime", "") for b in q.get("QuestBranches", [])), default="")
                report["started"].append({"quest": short(qc), "name": names.get(short(qc), ""), "type": qtype(qc),
                                          "branches": branch_str(q), "last_progress": last})
            if status == "QC_Succeded":
                done = [b["BranchID"] for b in q.get("QuestBranches", []) if enum(b.get("BranchType")) == "BranchCompleted"]
                none = [b["BranchID"] for b in q.get("QuestBranches", []) if enum(b.get("BranchType")) == "None"]
                if none and done:
                    report["untaken"].append({"quest": short(qc), "name": names.get(short(qc), ""),
                                              "completed": done, "never_reached": none})
            continue
        # walk the timeline for this quest
        hist = []
        for s in timeline:
            sq = quests(s["data"]).get(qc)
            hist.append((s, enum(sq.get("QuestCompletion")) if sq else "-", sq))
        first_bad = next((i for i, h in enumerate(hist) if h[1] == "QC_Failed" or
                          (h[2] and any(b["BranchID"] in locked and enum(b.get("BranchType")) == "BranchLocked"
                                        for b in h[2].get("QuestBranches", [])))), None)
        salvage = None
        if first_bad is not None:
            for i in range(first_bad - 1, -1, -1):
                if hist[i][1] not in ("-", "QC_Failed"):
                    salvage = i
                    break
        start = next((i for i, h in enumerate(hist) if h[1] != "-"), None)
        r = {"quest": short(qc), "name": names.get(short(qc), ""), "class": qc, "type": qtype(qc),
             "status": status, "branches": branch_str(q), "locked_branches": locked,
             "first_seen": snap_label(hist[start][0]) if start is not None else None,
             "likely_quest_items": items_near(latest["data"], q)}
        if first_bad is not None:
            bad = hist[first_bad][0]
            r["failed_by"] = snap_label(bad)
            if salvage is not None:
                good = hist[salvage][0]
                r["salvage_point"] = {"label": snap_label(good), "branches": branch_str(hist[salvage][2]),
                                      "load": best_loc(good), "all_locs": good["locs"]}
                gt, bt = tags(good["data"]), tags(bad["data"])
                r["tags_added_in_fail_window"] = sorted(bt - gt)
                gq, bq = quests(good["data"]), quests(bad["data"])
                r["other_quest_changes_in_window"] = sorted(
                    f"{short(k)}: {enum(gq[k].get('QuestCompletion')) if k in gq else '-'} -> {enum(v.get('QuestCompletion'))}"
                    for k, v in bq.items() if k != qc and json.dumps(gq.get(k), sort_keys=True) != json.dumps(v, sort_keys=True))
                comp_g = good["data"].get("EventPipeline", {}).get("ComponentInfoJson", {})
                comp_b = bad["data"].get("EventPipeline", {}).get("ComponentInfoJson", {})
                r["npc_state_changes_in_window"] = {k: [comp_g.get(k), v] for k, v in comp_b.items()
                                                    if comp_g.get(k) != v}
            else:
                r["salvage_point"] = None
        report["regrets"].append(r)
    return report


def to_markdown(rep):
    L = [f"# 存档遗憾报告", "", f"最新存档：{rep['latest']['label']}", ""]
    if not rep["regrets"]:
        L.append("没有发现失败或被锁定的任务。")
    for i, r in enumerate(rep["regrets"], 1):
        nm = f"{r['name']}（{r['quest']}）" if r["name"] else r["quest"]
        L += [f"## {i}. {nm} — {r['type']} — {r['status']}", "",
              f"- 分支状态：{r['branches']}"]
        if r.get("first_seen"):
            L.append(f"- 首次出现：{r['first_seen']}")
        if r.get("likely_quest_items"):
            L.append(f"- 疑似任务道具（拾取后数秒内任务推进）：{r['likely_quest_items']}")
        if r.get("failed_by"):
            L.append(f"- 首次失败于：{r['failed_by']}")
        sp = r.get("salvage_point")
        if sp:
            L += [f"- **最后可挽救点**：{sp['label']}，当时分支：{sp['branches']}",
                  f"  - 读取：`{sp['load']['sav']}` 里的 `{sp['load']['slot']}`"]
            if r.get("tags_added_in_fail_window"):
                L.append(f"- 失败窗口内新增剧情标签（失败原因线索）：{', '.join(r['tags_added_in_fail_window'][:40])}")
            if r.get("other_quest_changes_in_window"):
                L.append(f"- 同期其他任务变化：{'; '.join(r['other_quest_changes_in_window'][:20])}")
            if r.get("npc_state_changes_in_window"):
                L.append(f"- 同期 NPC 状态变化：{len(r['npc_state_changes_in_window'])} 处")
        elif r.get("failed_by"):
            L.append("- 没有找到失败前的快照（备份里最早的记录已是失败状态）→ 只能直接修补")
        L.append("")
    if rep["started"]:
        L += ["## 进行中的支线（可能仍可完成，或已悄悄卡死）", ""]
        for s in sorted(rep["started"], key=lambda x: x["last_progress"]):
            nm = f"{s['name']}（{s['quest']}）" if s["name"] else s["quest"]
            L.append(f"- {nm} [{s['type']}] 最后推进 {s['last_progress']}；{s['branches']}")
        L.append("")
    if rep["untaken"]:
        L += ["## 已完成但有分支从未触达（可能是另一种结局/选择）", ""]
        for u in rep["untaken"]:
            nm = f"{u['name']}（{u['quest']}）" if u["name"] else u["quest"]
            L.append(f"- {nm}：完成 {u['completed']}，未触达 {u['never_reached']}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    ap.add_argument("--quest")
    a = ap.parse_args()
    rep = analyse(a.root, a.quest)
    if a.json:
        json.dump(rep, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(to_markdown(rep))


if __name__ == "__main__":
    main()
