# 实例：挽救支线"见习医师"（JianXiYiShi）

这是一次真实的挽救过程，按顺序记录。可以把它当作每一步"正常情况下应该看到什么"的参照。

## 起因

玩家在西谷收齐了金疮草、凝脂叶、止血藤，准备回去交给营地里的小姑娘玉儿时，剧情已经推进到伏几之林，这个支线就被锁成了失败。

## 1. 扫描

`regrets.py` 的输出（节选）：

```
## 1. JianXiYiShi — Simple — QC_Failed
- 分支状态：1:BranchCompleted, 2:BranchLocked
- 疑似任务道具：[('I_01008', 1)]
- 首次失败于：2026.10.31-04.21.42 (游戏时长 8:06:26)
- 最后可挽救点：2026.10.31-03.50.12 (游戏时长 7:35:15)，当时分支：1:BranchCompleted, 2:BranchActivating
  - 读取：2Hourly/20261031-161934-168.sav 里的 AutoSave2
- 失败窗口内新增剧情标签：... fjzl.营地玉儿.到达营地 ...
```

怎么解读：

- 分支 1 是"收集 3 株草药"，分支 2 是"交给玉儿"。
- 失败窗口里出现了"营地玉儿·到达营地"，推测玉儿随剧情去了伏几之林的营地，西谷这边的交付就被锁死了。
- 三株草药是 `I_01009`、`I_01007`、`I_01008`。启发式只抓到了 `I_01008`，因为它是在分支完成前 3 秒拾取的。另外两株是通过对比"首次出现"前后的背包、以及它们交任务后数量变成 0 确认的。

## 2. 走过的弯路（值得吸取的教训）

一开始想把草药加进玩家指定的旧手动存档（ManualSave5，游戏时长 1:45:10）。检查后发现，那时**任务还没接**（任务是在那之后约 20 分钟才接的），而游戏是在拾取草药时记录任务进度的，背包里早有的草药可能不被承认。最后改用备份里的挽救点（路线 A），一次成功。

教训：动手前先确认挽救点那一刻任务处于什么状态。

## 3. 玩家重玩

玩家把那个备份文件改名为 `PBZSaveGame.sav`，读取 AutoSave2，直接去找玉儿交了任务，然后手动存档。发回来的文件里：

- `AutoSave2`（游戏时长 7:35:21）：任务 `QC_Started`，分支 2 正在进行 → 作为 before
- `ManualSave6`（游戏时长 7:36:27）：任务 `QC_Succeded` → 作为 after

## 4. 移植时发现的事件差异（共 13 条，另有 22 条噪音被忽略）

```
NPC 玉儿 EventTag: -收集药材可提交  +收集药材结束  +隐藏药盒
GlobalTags: +xg.营地玉儿.收集药材结束  +xg.营地玉儿.显示药盒  +xg.营地玉儿.隐藏药盒
ExecuteNodeGuid: +<玉儿的交付对话节点> = true
I_01007 / I_01008 / I_01009: CurrentAmount 1 -> 0（三株草药被交掉）
AccessoryInfos: +AC_Drink（奖励饰品）
QuestGameTimes[JianXiYiShi].GameTime -> 目标槽位的游戏时长
NarrativeSavedQuests[JianXiYiShi]: 整条替换（分支 2 BranchCompleted，CompletedBranches 加上 "2"，QC_Succeded）
成就 __ACH_046_Accessory: +AC_Drink，计数 14 -> 15
```

目标是 AutoSave0、AutoSave1、AutoSave2、ManualSave7，即最新这次游玩的全部槽位，四个槽位各 13 条全部为 `apply`。ManualSave1~6 保持原样。`pack` 回读校验通过。

## 5. 交付

用一张剧情语言的改动表，加上安装和验证步骤交给玩家（参照 SKILL.md 的"交付"一节）。
