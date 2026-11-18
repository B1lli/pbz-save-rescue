import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import complete_quest as C
import transplant as T


class XiaoCuiTests(unittest.TestCase):
    def setUp(self):
        self.recipe = T.load(ROOT / "references/recipes/XiaoCui.json")
        cls = "/Game/PBZstory/PBZQuest/Simple/XiaoCui.XiaoCui_C"
        done = ["1", "2", "2-ex", "3", "4-A"]
        self.quest = dict(QuestClass=cls, QuestCompletion="EQuestCompletion::QC_Failed",
                          CompletedBranches=done[:], QuestBranches=[])
        states = [(i, "BranchCompleted") for i in done]
        for i, state in states + [("4-B", "None"), ("5", "BranchLocked"), ("6", "None")]:
            self.quest["QuestBranches"].append(dict(BranchID=i, BranchType="EBranchType::" + state,
                                                    DirtyTime="2024.01.01-00.00.00"))
        self.target = {
            "PBZGameSystem": dict(CycleCount=0, DateTimeString="2025.01.01-00.00.00", HasGameTime=321),
            "Narrative": dict(NarrativeSavedQuests=[self.quest], QuestGameTimes=[dict(QuestClass=cls, GameTime=1)]),
            "Inventory": {"InventoryInfos": {}},
            "EventPipeline": {"GlobalTags": ["dhy.力者战斗.1阶段击杀", "dhy.力者战斗.2阶段击杀", "dhy.Seq116处决力者.播放结束"]},
        }

    def test_completion_and_reward_use_slot_time(self):
        C.check_requirements(self.target, self.recipe)
        p = T.Patcher(self.target, "test")
        original = copy.deepcopy(self.quest["QuestBranches"])
        for op in C.slot_ops(self.target, self.recipe):
            p.apply(op)
        self.assertEqual(self.quest["QuestBranches"][:-2], original[:-2])
        for branch in self.quest["QuestBranches"][-2:]:
            self.assertEqual(branch["BranchType"], "EBranchType::BranchCompleted")
            self.assertEqual(branch["DirtyTime"], "2025.01.01-00.00.00")
        self.assertEqual(self.quest["CompletedBranches"][-2:], ["5", "6"])
        self.assertEqual(self.quest["QuestCompletion"], "EQuestCompletion::QC_Succeded")
        self.assertEqual(self.target["Narrative"]["QuestGameTimes"][0]["GameTime"], 321)
        self.assertEqual(self.target["Inventory"]["InventoryInfos"]["TU_11007"],
                         dict(CurrentAmount=1, MaxAmount=1, AcquiredCycle=0,
                              FirstAddTime="2025.01.01-00.00.00", DirtyTime="2025.01.01-00.00.00"))
        with self.assertRaises(ValueError):
            C.check_requirements(self.target, self.recipe)

    def test_refuses_spent_reward_and_wrong_route(self):
        bag = self.target["Inventory"]["InventoryInfos"]
        bag["TU_11007"] = {"CurrentAmount": 0}
        with self.assertRaises(ValueError):
            C.check_requirements(self.target, self.recipe)
        del bag["TU_11007"]
        self.quest["CompletedBranches"][-1] = "4-B"
        with self.assertRaises(ValueError):
            C.check_requirements(self.target, self.recipe)
