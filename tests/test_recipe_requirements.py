import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import complete_quest as C
import transplant as T


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.recipe = T.load(ROOT / 'references/recipes/BaiShanMiWen.json')
        self.target = {
            'PBZGameSystem': {'CycleCount': 0, 'HasGameTime': 123456,
                              'DateTimeString': '2025.01.01-00.00.00'},
            'Narrative': {'NarrativeSavedQuests': [], 'QuestGameTimes': []},
            'Inventory': {'AccessoryInfos': {}, 'MainWeaponInfos': {}},
            'EventPipeline': {'GlobalTags': [], 'ComponentInfoJson': {},
                              'ComponentsOwnerActorInfo': {}, 'ExecuteNodeGuid': {}},
            'Player': {'Dust': 7654321}, 'MapSubsystem': {'unrelated': True},
        }
        quest_op = next(o for o in T.de_ops(self.recipe['slot_ops']) if o[0] == 'oreplace')
        self.target['Narrative']['NarrativeSavedQuests'] = [copy.deepcopy(quest_op[2])]
        self.target['Narrative']['QuestGameTimes'] = [
            {'QuestClass': quest_op[2]['QuestClass'], 'GameTime': 1}]
        for check in self.recipe['requires']:
            p = T.de_path(check['path'])
            # Keyed quest/branch lists already exist above.
            T.parent(self.target, p)[p[-1]] = copy.deepcopy(check['value'])
        self.target['Narrative']['NarrativeSavedQuests'].append(
            {'QuestClass': '/unrelated', 'QuestCompletion': 'untouched'})
        self.flow = next(k for k in self.target['EventPipeline']['ComponentInfoJson'])
        self.target['EventPipeline']['ComponentInfoJson'][self.flow]['EventTag'].append(
            'quest.幻术琵琶.收集背板')

    def test_repair_preserves_unrelated_state(self):
        original = copy.deepcopy(self.target)
        C.check_requirements(self.target, self.recipe)
        p = T.Patcher(self.target, 'synthetic')
        for op in T.de_ops(self.recipe['slot_ops']):
            p.apply(op)
        for key in ('PBZGameSystem', 'Player', 'MapSubsystem'):
            self.assertEqual(self.target[key], original[key])
        self.assertEqual(self.target['Inventory']['MainWeaponInfos'],
                         original['Inventory']['MainWeaponInfos'])
        quests = self.target['Narrative']['NarrativeSavedQuests']
        self.assertEqual(quests[-1], original['Narrative']['NarrativeSavedQuests'][-1])
        self.assertEqual(quests[0]['QuestCompletion'], 'EQuestCompletion::QC_Succeded')
        branch = next(b for b in quests[0]['QuestBranches'] if b['BranchID'] == 'PBZQuestBranch_4')
        self.assertEqual(branch['BranchType'], 'EBranchType::None')
        tags = self.target['EventPipeline']['ComponentInfoJson'][self.flow]['EventTag']
        self.assertIn('quest.幻术琵琶.收集背板', tags)
        self.assertNotIn('bsmw.剑偶.死亡无任务', tags)
        self.assertIn('bsmw.剑偶.死亡有任务', tags)
        item = self.target['Inventory']['AccessoryInfos']['AC_HeavyAttackDamage']
        self.assertEqual(item['CurrentLevel'], 0)
        self.assertEqual(item['DirtyTime'], original['PBZGameSystem']['DateTimeString'])
        with self.assertRaises(ValueError):
            C.check_requirements(self.target, self.recipe)

    def test_rejects_each_missing_requirement(self):
        for check in self.recipe['requires']:
            with self.subTest(path=check['path']):
                target = copy.deepcopy(self.target)
                p = T.de_path(check['path'])
                T.parent(target, p)[p[-1]] = None
                with self.assertRaises(ValueError):
                    C.check_requirements(target, self.recipe)

    def test_unknown_check_and_legacy_recipe(self):
        with self.assertRaises(ValueError):
            C.check_requirements({}, {'requires': [{'op': 'typo', 'path': ['x'], 'value': 1}]})
        C.check_requirements({}, T.load(ROOT / 'references/recipes/JianXiYiShi.json'))

    def test_existing_upgraded_accessory_is_preserved(self):
        item = {'CurrentLevel': 3, 'AcquiredCycle': 0, 'DirtyTime': '2024.01.01-00.00.00'}
        self.target['Inventory']['AccessoryInfos']['AC_HeavyAttackDamage'] = copy.deepcopy(item)
        C.check_requirements(self.target, self.recipe)
        p = T.Patcher(self.target, 'synthetic')
        for op in T.de_ops(self.recipe['slot_ops']):
            p.apply(op)
        self.assertEqual(self.target['Inventory']['AccessoryInfos']['AC_HeavyAttackDamage'], item)

    def test_cli_preflights_all_targets_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            valid, invalid, ach = root/'valid.json', root/'invalid.json', root/'ach.json'
            valid.write_text(json.dumps(self.target), encoding='utf8')
            self.target['PBZGameSystem']['CycleCount'] = 1
            invalid.write_text(json.dumps(self.target), encoding='utf8')
            ach.write_text('{"UnlockedIds":["sentinel"]}', encoding='utf8')
            output = root/'out'
            result = subprocess.run([sys.executable, '-I', str(ROOT/'scripts/complete_quest.py'),
                '--quest', 'BaiShanMiWen', '--target', str(valid), '--target', str(invalid),
                '--ach-target', str(ach), '--out-dir', str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'recipe does not apply', result.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(ach.read_text()), {'UnlockedIds': ['sentinel']})
            dry = subprocess.run([sys.executable, '-I', str(ROOT/'scripts/complete_quest.py'),
                '--quest', 'BaiShanMiWen', '--target', str(valid), '--out-dir', str(output),
                '--dry-run'], capture_output=True)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
