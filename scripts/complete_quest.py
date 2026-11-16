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


def quest_matches(quest_class, name):
    short = quest_class.rsplit(".", 1)[-1].removesuffix("_C")
    return name == quest_class or name.lower() == short.lower()


def find_quest(target, q):
    for x in target.get("Narrative", {}).get("NarrativeSavedQuests", []):
        cls = x.get("QuestClass", "")
        if quest_matches(cls, q):
            return x, cls.rsplit(".", 1)[-1].removesuffix("_C")
    return None, None


def recipe_adds_quest(recipe, ops, name):
    """A scoped recipe may explicitly create the requested missing quest."""
    if not recipe.get("requires"):
        return False
    for kind, path, _, value in ops:
        if kind != "oadd" or not isinstance(value, dict):
            continue
        cls = value.get("QuestClass", "")
        if (path == ("Narrative", "NarrativeSavedQuests", ("k", "QuestClass", cls))
                and cls and quest_matches(cls, name)):
            return True
    return False


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


def check_requirements(target, recipe):
    """Optional recipe scope checks, evaluated before writing any output.

    Paths use transplant's serialized path format. Unknown checks fail closed.
    Recipes without requirements retain their existing behavior.
    """
    for check in recipe.get("requires", []):
        path = T.de_path(check["path"])
        value = T.get(target, path)
        if check["op"] == "equals":
            ok = value == check["value"]
        elif check["op"] == "contains_all":
            ok = isinstance(value, list) and all(x in value for x in check["value"])
        else:
            raise ValueError(f"unknown recipe requirement: {check['op']}")
        if not ok:
            raise ValueError(f"recipe does not apply: {T.pstr(path)} ({check['op']})")


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
    ops = T.de_ops(recipe["slot_ops"]) if recipe else []
    can_add_quest = bool(recipe and recipe_adds_quest(recipe, ops, a.quest))
    plan = [f"# 直接完成任务：{a.quest}", "", f"- 方式：{'配方（来自真实通关记录）' if recipe else '通用（只改任务状态）'}"]
    pending = []
    targets = [(tp, T.load(tp)) for tp in a.target]
    if recipe:
        plan.append(f"- 配方：{rp} — {recipe.get('note', '')}")
        # Preflight every requested slot before creating output or touching achievements.
        try:
            for tp, target in targets:
                check_requirements(target, recipe)
        except ValueError as ex:
            ap.error(f"{tp}: {ex}")
    for tp, t in targets:
        rec, _ = find_quest(t, a.quest)
        if rec is None and not can_add_quest:
            msg = f"{tp}: 这个槽位里没有任务 {a.quest}（还没接到），跳过"
            print(msg); plan += ["", msg]
            continue
        if rec is None:
            game = t.get("PBZGameSystem", {})
            stamp, play = game.get("DateTimeString"), game.get("HasGameTime")
            if not isinstance(stamp, str) or not T.TS.fullmatch(stamp) or type(play) is not int or play < 0:
                ap.error(f"{tp}: cannot add a quest without a valid save timestamp and play time")
        if mode == "recipe":
            P = T.Patcher(t, os.path.basename(tp))
            for op in ops:
                P.apply(op)
            if rec is None and any(status in ("conflict", "skip") for status, _ in P.log):
                ap.error(f"{tp}: could not apply all operations for the missing quest")
            log = [f"[{s}] {x}" for s, x in P.log]
        else:
            log = generic_complete(rec) or ["已经是完成状态，无需修改"]
            tags = [g for g in t.get("EventPipeline", {}).get("GlobalTags", [])]
            plan += ["", f"相关线索（供解释用，未修改）：共 {len(tags)} 个全局剧情标签，请按任务相关角色名筛选查看"]
        patched, _ = find_quest(t, a.quest)
        if patched is None or (rec is None and patched.get("QuestCompletion") != "EQuestCompletion::QC_Succeded"):
            ap.error(f"{tp}: recipe did not produce the requested completed quest")
        state = patched.get("QuestCompletion")
        plan += ["", f"## {tp}", f"结果：{state}", ""] + [f"- {x}" for x in log]
        print(f"{tp}: {state} ({len(log)} changes)")
        if not a.dry_run:
            pending.append((os.path.basename(tp), t))

    if a.ach_target and recipe and recipe.get("ach_ops"):
        t = T.load(a.ach_target)
        P = T.Patcher(t, "achievements")
        for op in T.de_ops(recipe["ach_ops"]):
            P.apply(op)
        T.achievements_fix(t)
        plan += ["", "## 成就进度（本地）", ""] + [f"- [{s}] {x}" for s, x in P.log]
        if not a.dry_run:
            pending.append((os.path.basename(a.ach_target), t))

    if mode == "generic":
        plan += ["", "注意：没有这个任务的配方，奖励道具、NPC 后续状态、剧情标签都没有补。"
                 "要如实告诉玩家：任务列表会显示已完成，但奖励可能缺失、NPC 可能还停在旧状态。"]
    text = "\n".join(plan)
    if a.dry_run:
        print(text)
    else:
        os.makedirs(a.out_dir, exist_ok=True)
        for name, data in pending:
            with open(os.path.join(a.out_dir, name), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        open(os.path.join(a.out_dir, "plan.md"), "w", encoding="utf-8").write(text)
        print(f"plan written to {os.path.join(a.out_dir, 'plan.md')}")
    print("下一步：pbzsave.py pack <原始存档> <out-dir> <新存档>，再用 pbzsave.py install 装回（先征得玩家同意）。")


if __name__ == "__main__":
    main()
