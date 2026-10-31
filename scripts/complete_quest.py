#!/usr/bin/env python3
"""Mark a failed / locked / unfinished quest as completed directly in the latest save,
without replaying it. This is the DEFAULT rescue route.

  complete_quest.py --quest JianXiYiShi --target T.json [--target T2.json ...]
                    [--ach-target __Achievements__.json] --out-dir OUT [--dry-run]

How it completes the quest:
  * recipe (best): if references/recipes/<Quest>.json exists, it was recorded from a real
    in-game completion of this quest, so applying it gives the same result as playing it:
    quest record, story tags, NPC state, dialogue nodes, quest items handed in, rewards,
    achievement progress.
  * generic (no recipe): sets QuestCompletion = QC_Succeded and every branch to
    BranchCompleted. Rewards, NPC follow-up state and story tags are NOT known, so they are
    not added; say so to the player. Related tags are printed so you can explain the state.

Writes patched copies into OUT plus OUT/plan.md; pack them with pbzsave.py pack.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import transplant as T

RECIPES = os.path.join(HERE, "..", "references", "recipes")


def find_quest(target, q):
    for x in target.get("Narrative", {}).get("NarrativeSavedQuests", []):
        cls = x.get("QuestClass", "")
        short = cls.rsplit(".", 1)[-1].removesuffix("_C")
        if q in (cls, short) or q.lower() == short.lower():
            return x, short
    return None, None


def generic_complete(rec):
    changed = []
    if rec.get("QuestCompletion") != "EQuestCompletion::QC_Succeded":
        changed.append(f"QuestCompletion {rec.get('QuestCompletion')} -> QC_Succeded")
        rec["QuestCompletion"] = "EQuestCompletion::QC_Succeded"
    done = rec.setdefault("CompletedBranches", [])
    for b in rec.get("QuestBranches", []):
        if b.get("BranchType") != "EBranchType::BranchCompleted":
            changed.append(f"branch {b.get('BranchID')} {b.get('BranchType')} -> BranchCompleted")
            b["BranchType"] = "EBranchType::BranchCompleted"
        if b.get("BranchID") is not None and b["BranchID"] not in done:
            done.append(b["BranchID"])
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quest", required=True, help="quest class short name, e.g. JianXiYiShi")
    ap.add_argument("--target", action="append", required=True)
    ap.add_argument("--ach-target")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--recipe", help="recipe file (default: references/recipes/<Quest>.json)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rp = a.recipe or os.path.join(RECIPES, f"{a.quest}.json")
    recipe = json.load(open(rp, encoding="utf-8")) if os.path.isfile(rp) else None
    mode = "recipe" if recipe else "generic"
    plan = [f"# 直接完成任务：{a.quest}", "", f"- 方式：{'配方（来自真实通关记录）' if recipe else '通用（只改任务状态）'}"]
    if recipe:
        plan.append(f"- 配方：{rp} — {recipe.get('note', '')}")
    if not a.dry_run:
        os.makedirs(a.out_dir, exist_ok=True)

    for tp in a.target:
        t = T.load(tp)
        rec, short = find_quest(t, a.quest)
        if rec is None:
            msg = f"{tp}: 这个槽位里没有任务 {a.quest}（还没接到），跳过"
            print(msg); plan += ["", msg]
            continue
        if mode == "recipe":
            P = T.Patcher(t, os.path.basename(tp))
            for op in T.de_ops(recipe["slot_ops"]):
                P.apply(op)
            log = [f"[{s}] {x}" for s, x in P.log]
        else:
            log = generic_complete(rec) or ["已经是完成状态，无需修改"]
            tags = [g for g in t.get("EventPipeline", {}).get("GlobalTags", [])]
            plan += ["", f"相关线索（供解释用，未修改）：共 {len(tags)} 个全局剧情标签，请按任务相关角色名筛选查看"]
        state = find_quest(t, a.quest)[0].get("QuestCompletion")
        plan += ["", f"## {tp}", f"结果：{state}", ""] + [f"- {x}" for x in log]
        print(f"{tp}: {state} ({len(log)} changes)")
        if not a.dry_run:
            open(os.path.join(a.out_dir, os.path.basename(tp)), "w", encoding="utf-8").write(
                json.dumps(t, ensure_ascii=False, separators=(",", ":")))

    if a.ach_target and recipe and recipe.get("ach_ops"):
        t = T.load(a.ach_target)
        P = T.Patcher(t, "achievements")
        for op in T.de_ops(recipe["ach_ops"]):
            P.apply(op)
        T.achievements_fix(t)
        plan += ["", "## 成就进度（本地）", ""] + [f"- [{s}] {x}" for s, x in P.log]
        if not a.dry_run:
            open(os.path.join(a.out_dir, os.path.basename(a.ach_target)), "w", encoding="utf-8").write(
                json.dumps(t, ensure_ascii=False, separators=(",", ":")))

    if mode == "generic":
        plan += ["", "注意：没有这个任务的配方，奖励道具、NPC 后续状态、剧情标签都没有补。"
                 "要如实告诉玩家：任务列表会显示已完成，但奖励可能缺失、NPC 可能还停在旧状态。"]
    text = "\n".join(plan)
    if a.dry_run:
        print(text)
    else:
        open(os.path.join(a.out_dir, "plan.md"), "w", encoding="utf-8").write(text)
        print(f"plan written to {os.path.join(a.out_dir, 'plan.md')}")
    print("下一步：pbzsave.py pack <原始存档> <out-dir> <新存档>，再用 pbzsave.py install 装回（先征得玩家同意）。")


if __name__ == "__main__":
    main()
