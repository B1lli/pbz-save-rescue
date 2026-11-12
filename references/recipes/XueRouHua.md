# 血肉之花：交付 NPC 被隐藏导致的坏结局修复

本配方来自一次真实的玩家存档修复，并在游戏内完整验证（交付 → 见爹过场 → 结算奖励）。它是**限定状态**的修复：只覆盖「任务仍在进行、只差交付」的失败档，不覆盖没接任务、已经播过坏结局、或换周目的情况。

## 现象

- 第二章支线「血肉之花」当年没把血肉花交给营地里的玉儿。
- 进庞镇后街玉儿家见爹时，播的是“爹已死”过场，奖励「失去光彩的破损玉佩」`I_06003`。
- 飞贼营地里该出现的玉儿、以及和她并排站的被救飞贼，都不在场（但营地其他 NPC、栅栏、僧人都正常）。

## 根因

任务账本没有问题：`XueRouHua` 的分支 1 一直是 `BranchCompleted`，S2 交付分支一直是 `BranchActivating [1,0]`，十份历史槽位（11-02 至 11-08）完全一致——游戏从头到尾都在等交付。

真正的病根在 NPC 物件的可见性：

| 物件 | UAID | 待机 | 坐标 |
|---|---|---|---|
| 营地玉儿 | `…_BCFCE706288DC5AE02_1084126799` | `XSSL_XiaoHuLu`（小葫芦） | (-70672, 156206, -523) |
| 被救飞贼归队 | `…_60CF848A6677DFBD02_1141928986` | `Special1` | (-71063, 156156, -516) |

两者 `EventPipeline.ComponentsOwnerActorInfo[…].OwnerVisible` 均为 `false`。记录完好、坐标正确、任务条件也满足，就是不出现在世界里。两者相距约 400 单位，即“并排站着”。

身份来源：`JiuSiFuShang.json`（救死扶伤真实完成差异）的备注与 `slot_ops` 点名了这两个 UAID。注意该配方只把飞贼在“归队前”设为不可见，**并没有把玉儿的可见性打开**，所以需要本配方的两条 `chg`。

## 适用条件

`requires` 检查两项：

1. `XueRouHua` 的 `S2` 分支为 `EBranchType::BranchActivating`（任务仍在进行、只差交付）；
2. `GlobalTags` 含 `fjzl.营地玉儿.到达营地`（玉儿已经随剧情到过飞贼营地）。

任一不满足，`complete_quest.py` 会在写出任何目标文件之前整体报错。不要删掉检查强行使用。

## 修改范围

- 只改两个物件的 `OwnerVisible: false → true`。
- 不碰任务账本、不碰世界层、不碰 `GlobalTags`、不碰背包与主线。
- `ach_ops` 留空：`AC_RandomDrink`（静心小葫芦）是游戏在交付后好结局结算时自己写进 `AccessoryInfos` 的（实测 `DirtyTime` 为结算时刻），不是本配方补的。因此不推断、不伪造成就解锁或饰品收集计数。

## 修复后由游戏自己写入的状态（供判断是否成功）

| 项目 | 修复前 | 交付并见爹之后 |
|---|---|---|
| XueRouHua S2 | `BranchActivating [1,0]` | `BranchCompleted` |
| CompletedBranches | `["1"]` | `["1","S2"]` |
| 新标签 | — | `xg.玉儿.显示双生血肉花` / `演出双生血肉花` / `交出双生血肉花` / `收下血肉花` |
| 后街层 | `HouJie_Before_YuErDie` ×2 加载 | `HouJie_After_YuErDie1` ×2 加载 |
| 爹标签 | 无 | `pz.玉儿爹.对话1/2/3`、`等待平复…`、`禁止离开`、`允许离开` |
| 饰品 | 40 件 | 41 件（新增 `AC_RandomDrink`） |

注意：应用配方后任务列表里它仍是 `QC_Started`，因为配方只负责“让人出现”；真正的交付必须由玩家在游戏里完成，任务完成与奖励都由游戏写入。这一点请在引导玩家时说明。

## 验证

```bash
python3 -I scripts/complete_quest.py --quest XueRouHua \
  --target <解包后的槽位.json> --recipe references/recipes/XueRouHua.json \
  --out-dir patched --dry-run
```

实测输出（对一份真实失败槽位）：

```
[apply] chg EventPipeline/ComponentsOwnerActorInfo/PBZ_Fujizhilin_WP-BP_NPCSpawner_C_UAID_BCFCE706288DC5AE02_1084126799/OwnerVisible | false => true
[apply] chg EventPipeline/ComponentsOwnerActorInfo/PBZ_Fujizhilin_WP-BP_NPCSpawner_C_UAID_60CF848A6677DFBD02_1141928986/OwnerVisible | false => true
```

确认适用后去掉 `--dry-run`，按技能的备份、打包、退出游戏、安装流程进行。

## 限制

- 只用一条任务、一位玩家、一个版本验证过；其他失败路线、其他版本、后续周目未验证。
- 若目标存档里这两个键名不同（子关卡前缀差异），操作会被静默 `skip`；请先用解包结果核对整键，或按 UAID 尾号匹配。
- 不提交原始存档、完整槽位、Steam ID 或本地路径。

## 收尾：交付已经完成，地图上却还挂着这一步的图标

症状出现在“修复之后再进游戏”的存档上：交付、见爹、好结局都正常，但庞镇地图上仍挂着一条「血肉之花 · 如果到达了庞镇，就回来接玉儿回家吧」，底部提示“取消追踪”。点掉追踪后图标依然在。

取证结论（当时那份存档）：

- `Narrative`：`TrackedBranchID = S1`、`S1` 为 `EBranchType::BranchActivating`，而交付用的 `S2` 已是 `BranchCompleted`。
- 交付成功的那一刻，游戏立刻激活了下一环 `S1` 并设为当前追踪：`S1` 与 `S2` 的 `DirtyTime` 完全相同（`2026.11.08-15.20.59`）。
- 点“取消追踪”并保存后（`TrackedQuestPath` 变空、`TrackedBranchID = None`、`ManualTrackingOptOut = true`），**图标仍在**。
- `MapSubsystem` 各子节（XiGu / FuJiZhiLin / LuJiaCun / PangZhen / HouJie / ZhengDaoDaYing 等）里搜任务名：0 命中；全档除 `Narrative` 外搜 `XueRouHua`：也是 0 命中。

也就是说，这个图标是运行时按“该任务仍有 `BranchActivating` 分支”画出来的，不是地图数据，所以改地图、清追踪都没有用。

处理方式（只对“这一步已经无法再走”的档使用）：把 `S1` 置为 `EBranchType::BranchCompleted`、`CompletedBranches` 追加 `"S1"`、`QuestCompletion` 置 `EQuestCompletion::QC_Succeded`，其余一字不动；只改已经交付过的槽位，交付前的历史槽位保持原样以便回退。

实测结果：装回后进游戏，图标消失、任务列表显示「血肉之花（已完成）」；随后游戏自行存盘，解包复核 `QC_Succeded` 与 `CompletedBranches` 含 `S1` 均未被游戏重算回去。

注意事项：

- 只有当该分支的触发点确实已经耗尽（补玩也走不到）时才这样处理；仍能走通的步骤应该让玩家自己在游戏里完成，不要替他判完成。
- 改档不会补发成就。「杏林有继」这类成就依赖游戏内条件，账本里写成完成也不会触发。
- `dhs.决战前Npc.血肉花` 这类后续剧情 NPC 是否会因任务被判完成而不再出场，当时未验证，无法给出结论。