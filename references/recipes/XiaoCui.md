# 小翠 · 白山派头带

首周目走 4-A 路线，在断魂山打完力者与锯者后，小翠的任务可能显示失败。此配方将第 5、6 步及任务日志设为完成，并在背包中补一份白山风雷剑的铸魂材料「白山派头带」（`TU_11007`）。

只有存档记录了力者两阶段击杀和处决结束、4-A 已完成、4-B 未触发、第 5 步被锁且第 6 步未触发时适用。背包中已有头带记录（包括数量为零）时会拒绝补发，以免重复领取已消耗的材料。

先按仓库说明备份、解包，再用当前版本的脚本预演。以下示例只选一个失败槽位：

```sh
python -I scripts/complete_quest.py --quest XiaoCui --target unpacked/PBZSaveGame/AutoSave0.json --out-dir patched --dry-run
```

确认后去掉 `--dry-run` 生成修补后的 JSON，再按主流程打包和安装。游戏中读取刚修补的槽位，检查任务日志和铸魂材料栏。

配方来自对真实失败档的定向修补。已用存档副本核对结果，尚缺正常交付前后的游戏内样本。适用范围为任务日志和材料，陆解元对话、过场、成就及实际铸魂效果未经验证。材料编号可在 [SaveSmith 物品表](https://github.com/gundamff/SaveSmith/blob/927eebaaa2f78c8cb0c397dc2e18cf20a6c8f4ca/src/games/phantom-blade-zero/catalog/items.json#L589)中核对。
