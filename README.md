# pbz-save-rescue · 影之刃零存档遗憾挽救

支线断了、剧情选错、成就错过？把这个仓库的地址丢给你的 AI 助手，它会自动找到你的存档，先做备份，再把遗憾补回来。整个过程中，你只需要回答它一个问题，然后重新读档。

## 玩家怎么用

1. 打开一个能操作你电脑的 AI 助手。我们演示用的是 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)：下载见 [Releases](https://github.com/deepseek-ai/deepseek-harness/releases)，也可以在命令行运行 `npx @deepseek-ai/dsh web`。第一次使用时，在 设置 → 模型 里填上 DeepSeek API Key。
2. 把这个仓库的地址发给它，说：**"用这个帮我挽救影之刃零存档里的遗憾：https://github.com/B1lli/pbz-save-rescue"**。
3. 它问你怎么处理时，直接回 **"好"**，就会按默认方式把断掉的支线设为已完成。想自己在游戏里补玩的话，选第 2 项。
4. 它提醒你关游戏时，就把游戏关掉。改好之后打开游戏，读取最近的存档。

能做到的事：

- **找遗憾**：列出失败或锁死的支线、选错的分支，以及最后还能挽救的备份。
- **直接完成**（默认）：这个任务有配方的话，奖励、NPC 状态、剧情标记都会一起补上。
- **亲自补玩**（可选）：把你送回过去，玩完后把结果搬回最新存档，主线进度不丢。
- **补成就**：送你回还能达成条件的时间点，由游戏自己向 Steam 解锁。

动手前会备份整个存档文件夹，换回去随时可以；所有操作都在你的电脑上本地完成。

## 给 AI 助手的说明

用户把这个仓库地址发给你，就表示请你帮他挽救《影之刃零》的存档。按下面做：

1. 把仓库下载或克隆到本地（`git clone https://github.com/B1lli/pbz-save-rescue`，没有 git 就下载 https://github.com/B1lli/pbz-save-rescue/archive/refs/heads/main.zip ），完整阅读 `SKILL.md`，从第 0 步开始照着执行。尽量自己完成所有操作，用户只需要回答一个问题、关闭游戏、重新读档。
2. 运行环境：Python 3.9+，需要先 `pip install cryptography`；还需要 Node.js。Windows 上用 `python` 或 `py -3`。
3. 运行 `scripts/setup_oodle.py` 之前，先征得用户同意：它会下载第三方解码器，并校验哈希。
4. 修改任何东西之前，先运行 `scripts/pbzsave.py backup`。替换存档之前，先确认用户已经完全退出游戏。

## 已收录的任务配方

| 任务 | 文件 |
|---|---|
| 见习医师 | `references/recipes/JianXiYiShi.json` |

如果你亲自补玩过某个任务，`transplant.py --save-recipe` 会把它保存成配方。欢迎提交 PR，让后来的玩家可以一键完成。

## 说明

- 这是非官方的玩家工具，与游戏开发商无关。修改存档存在风险，请保留好备份。
- 以 [MIT 协议](LICENSE) 开源。
- 存档格式和密钥来自开源项目 [SaveSmith](https://github.com/gundamff/SaveSmith)（MIT 协议）。游戏更新后存档打不开时，运行 `pbzsave.py update-key`，会从上游拉取新密钥。
