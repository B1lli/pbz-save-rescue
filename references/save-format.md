# 影之刃零 存档格式参考

读这份文档的时机：脚本报错、需要手工查看或修改某个字段、或者遗憾不是"任务失败"而是别的东西（比如没开的宝箱、没拿到的饰品）的时候。

## 目录
1. 存档文件夹
2. 容器格式
3. 槽位 JSON 的主要部分
4. 任务记录
5. 剧情标记与 NPC 状态
6. 物品
7. 成就
8. 哪些差异属于噪音

## 1. 存档文件夹

Steam 版：`<Steam库>\steamapps\common\PBZ\ProjectPBZ\Saved\SaveGames\Steam\<SteamID64>\`。社区资料对这个路径说法不一，以用户电脑上实际看到的为准。

```
PBZSaveGame.sav          当前主存档（游戏读写的就是它）
1RealTime\*.sav          最近几次写入的滚动备份（分钟级）
2Hourly\*.sav            每小时一份
3Daily\*.sav             每天一份
steam_autocloud.vdf      Steam 云同步标记
```

每个 .sav 都是一个**完整的容器**，里面装着当时所有的槽位。所以备份文件夹就是一部"时光机"：一个已经失败的任务，往往能在某个旧备份里找到它还能完成时的样子。

## 2. 容器格式

格式最早由开源项目 SaveSmith（gundamff/SaveSmith，MIT 协议）逆向出来，脚本里用的密钥也来自它。

```
外层头 12 字节：  "PBZS" | u16 0x0103 | u16 槽位数 | u32 目录块长度
目录块：          加密块，明文 = 外层头副本 + 每个槽位一条记录：
                  u16 名字长度 | 名字 | u8 压缩方式 | u8 是否加密 | u32 解压后大小 | u32 相对偏移 | u32 块长度
槽位块：          紧挨着排列的加密块
加密块：          "PBZS" 01 <是否加密> 00 00 | nonce(12) | tag(16) | AES-256-GCM 密文
压缩方式：        0 = 不压缩，1 = zlib，2 = Oodle（Mermaid）
```

- 游戏自己写入用的是 Oodle，我们写回用 zlib（压缩方式 = 1）。SaveSmith 也是这么做的，游戏可以正常读取。
- 如果出现 AES 校验失败，最可能的原因是游戏更新后换了密钥（脚本内置的是 build 26266538 的密钥）。运行 `pbzsave.py update-key <存档>`，它会从 SaveSmith 的 `crypto/pbzsCrypto.ts` 拉取新密钥，用这份存档验证通过后再保存。
- 槽位名有：`AutoSave0..2`、`ManualSave1..N`、`__Advanced__`（加载提示等全局杂项）、`__Achievements__`（全局成就进度）。

## 3. 槽位 JSON 的主要部分

| 键 | 内容 |
|---|---|
| `PBZGameSystem` | 存档时间 `DateTimeString`、游戏时长（秒）`HasGameTime`、地图 `CurrentLevelName`、存档点 `LastSaveActorID`、坐标、周目 `CycleCount` |
| `Narrative` | 任务：`NarrativeSavedQuests`、`QuestGameTimes`、`MainQuestUpdateRecords`、正在追踪的任务 |
| `EventPipeline` | 剧情状态：`GlobalTags`（全局剧情标签）、`ComponentInfoJson`（每个 NPC/机关的 `EventTag`）、`ExecuteNodeGuid`（已播放过的对话/流程节点） |
| `Inventory` | `InventoryInfos`（材料、道具、书页）、`AccessoryInfos`（饰品）、武器、药 |
| `LevelActorManager` | 场景物件的状态（雾门、宝箱、音乐触发器等） |
| `MapSubsystem` | 地图迷雾、已解锁区域 |
| `BossRecord`、`ShopSystem`、`Player`（尘 `Dust` 等） | 见字面意思 |

## 4. 任务记录

```json
{"QuestClass": "/Game/PBZstory/PBZQuest/Simple/JianXiYiShi.JianXiYiShi_C",
 "QuestBranches": [
   {"BranchID": "1", "TasksProgress": [0,0,0], "BranchType": "EBranchType::BranchCompleted", "DirtyTime": "..."},
   {"BranchID": "2", "BranchType": "EBranchType::BranchLocked", "DirtyTime": "..."}],
 "QuestCompletion": "EQuestCompletion::QC_Failed",
 "CompletedBranches": ["1"], "ReachedStateNames": []}
```

- `QuestCompletion`：`QC_Started`（进行中）、`QC_Succeded`（成功，游戏原文就是这么拼的）、`QC_Failed`（失败）。
- `BranchType`：`None`（还没触达）、`BranchActivating`（进行中）、`BranchCompleted`（已完成）、`BranchLocked`（被锁死，通常意味着错过了）。
- 任务路径里的分类目录：`Main` 主线、`Branch` 分支剧情、`Simple` 普通支线、`Collect` 收集、`Tutorial` 教学。
- 类名是拼音，比如 JianXiYiShi = 见习医师。确认过的中文名记在 `quest_names.json` 里，每确认一个新的就补进去。
- **`CompletedBranches` 与实际进度可能脱节。** 这个列表是"哪些分支曾经完成过"的独立账本，游戏不会拿 `BranchType` 反推它。真实出现过的情况：某分支记着 `BranchCompleted`，但 ID 从没进过 `CompletedBranches`（多见于任务中途被打断、之后靠改档恢复）。此后玩家每次走回该分支的入口触发点（存档点、牌坊/钟、地图切换），游戏都会把它重新置为 `BranchActivating`，任务栏和地图上于是又冒出一个早就走完的目标 —— 不是存档损坏，是这一步从来没落账。
  - 判据：该分支 `DirtyTime` 恰好等于这次重回触发点的时间；这一步对应的 `GlobalTags`（进出、对话、交物）早已齐全；依赖它的物证也在（拿到过的道具、打过的 BOSS 记录）。
  - 处理：`BranchType` 改为 `BranchCompleted`，分支 ID 追加进 `CompletedBranches`，**`QuestCompletion` 不要动** —— 同一任务常有多条分支并行，全部走完才 `QC_Succeded`。
- **同一任务并存多个 `BranchActivating` 是正常状态。** `TrackedBranchID` 指向的分支不一定就是任务栏当前显示的那条；补掉一个目标后，游戏会把下一条的目标顶上来。不要因为"地图上还剩一个图标"就把其它 `BranchActivating` 一起判完成，那等于跳过整段剧情。

## 5. 剧情标记与 NPC 状态

- `GlobalTags` 是中文的，形如 `地区缩写.角色.事件`，比如 `xg.营地玉儿.收集药材可提交`。`xg` 是西谷，`fjzl` 是伏几之林。理解剧情时，这是信息量最大的地方。
- `ComponentInfoJson[<NPC 生成器 ID>].EventTag` 是这个 NPC 当前的状态，决定她站在哪里、说什么。
- `ExecuteNodeGuid` 记录一段对话或流程是否已经播放过。补上它，NPC 就不会重复那段对话。

## 6. 物品

- `InventoryInfos[ID] = {CurrentAmount, MaxAmount, FirstAddTime, DirtyTime, AcquiredCycle}`。`MaxAmount` 看起来是累计获得数。任务道具交掉后 `CurrentAmount` 会变成 0，但记录本身不删除。
- 饰品放在 `AccessoryInfos[ID] = {CurrentLevel, DirtyTime, AcquiredCycle}`。
- ID 前缀：`I_` 道具，`T_` 可能是信物，`R_`/`F_`/`FA_`/`K_` 是各类收集品，`Page_` 是书页，`AC_` 是饰品。
- SaveSmith 的物品目录（`catalog/items.json`）里有部分 ID 的中文名，但不含任务道具。

## 7. 成就（`__Achievements__` 槽位，全局共享）

```json
{"UnlockedIds": [...], "Counters": {"__ACH_046_Accessory": 14}, "CompletedElements": {"__ACH_046_Accessory": ["AC_Loot", ...]}, "PlatformPending": []}
```

如果某个计数器对应着 `CompletedElements` 里的列表，它的值应该等于列表长度，`transplant.py` 会自动修正。只往里加，不删除。

## 8. 哪些差异属于噪音

只要重新存档就会变、或者只跟玩家所在位置有关的东西：存档时间、游戏时长、坐标和视角、存档点（钟）、当前地图、敌人刷新器（`AISystem`）、当前武器选择、正在追踪的任务、`__Advanced__` 里的加载提示。

`transplant.py` 默认会过滤掉这些。如果确实需要移植其中某项（比如解锁了一个钟），用 `--keep 路径片段` 把它保留下来。
