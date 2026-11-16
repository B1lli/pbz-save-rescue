import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import complete_quest as C
import transplant as T


class MissingQuestRecipeTests(unittest.TestCase):
    def setUp(self):
        self.recipe = json.loads((ROOT / "references/recipes/BaiXue.json").read_bytes())
        self.target = {
            "PBZGameSystem": {"CycleCount": 0, "DateTimeString": "2020.02.03-04.05.06", "HasGameTime": 12345},
            "Narrative": {"NarrativeSavedQuests": [{"QuestClass": "/unrelated", "QuestCompletion": "untouched"}],
                          "QuestGameTimes": []},
            "Player": {"Dust": 123},
        }
        for check in self.recipe["requires"]:
            path = T.de_path(check["path"])
            if check["value"] is not None:
                T.parent(self.target, path)[path[-1]] = copy.deepcopy(check["value"])
        self.target["Inventory"]["AccessoryInfos"] = {}

    def command(self, root, targets, extra=(), quest="BaiXue"):
        args = [sys.executable, "-I", "-B", "-X", "utf8", str(ROOT / "scripts/complete_quest.py"),
                "--quest", quest, "--out-dir", str(root / "out"), *extra]
        for path in targets:
            args.extend(("--target", str(path)))
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=15)

    def write_target(self, root, name, data=None):
        path = root / name
        path.write_text(json.dumps(self.target if data is None else data), encoding="utf-8")
        return path

    def test_creates_missing_quest_and_records_rewards_at_target_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = self.write_target(root, "slot.json")
            dry = self.command(root, [target], ("--dry-run",))
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse((root / "out").exists())
            result = self.command(root, [target])
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = json.loads((root / "out/slot.json").read_bytes())
            rec, _ = C.find_quest(saved, "BaiXue")
            self.assertEqual(rec["QuestCompletion"], "EQuestCompletion::QC_Succeded")
            self.assertEqual(saved["Narrative"]["NarrativeSavedQuests"][0], self.target["Narrative"]["NarrativeSavedQuests"][0])
            self.assertEqual(saved["Narrative"]["QuestGameTimes"][0]["GameTime"], 12345)
            stamp = self.target["PBZGameSystem"]["DateTimeString"]
            self.assertTrue(all(b["DirtyTime"] == stamp for b in rec["QuestBranches"]))
            self.assertEqual(saved["Inventory"]["AccessoryInfos"]["AC_Bleed"]["DirtyTime"], stamp)
            for item in ("F_06004", "F_06022", "FA_0602"):
                self.assertEqual(saved["Inventory"]["InventoryInfos"][item]["CurrentAmount"], 1)
            self.assertEqual(saved["Inventory"]["InventoryInfos"]["I_10003"]["CurrentAmount"], 0)
            self.assertEqual(saved["Player"], self.target["Player"])
            self.assertEqual(saved["MapSubsystem"], self.target["MapSubsystem"])
            with self.assertRaises(ValueError):
                C.check_requirements(saved, self.recipe)

    def test_other_choices_and_cycles_and_unopened_courtyard_are_rejected(self):
        cases = [
            (("PBZGameSystem", "CycleCount"), 1),
            (("EventPipeline", "GlobalTags"), ["ddsd.获得物品.赎罪名单", "ddsd.杀气怪面.不放走"]),
            (("Inventory", "InventoryInfos", "K_05007", "CurrentAmount"), 1),
            (("MapSubsystem", "EndedLockObjGuids"), []),
        ]
        for path, value in cases:
            with self.subTest(path=path):
                target = copy.deepcopy(self.target)
                T.parent(target, path)[path[-1]] = value
                with self.assertRaises(ValueError):
                    C.check_requirements(target, self.recipe)

    def test_missing_destination_list_leaves_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            valid = self.write_target(root, "valid.json")
            invalid = copy.deepcopy(self.target)
            del invalid["Narrative"]["QuestGameTimes"]
            invalid_path = self.write_target(root, "invalid.json", invalid)
            result = self.command(root, [valid, invalid_path])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not apply all operations", result.stderr)
            self.assertFalse((root / "out").exists())

    def test_untracked_quest_without_a_recipe_still_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = self.write_target(root, "slot.json")
            result = self.command(root, [target], quest="UntrackedQuest")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "out/slot.json").exists())


if __name__ == "__main__":
    unittest.main()
