# pbz-save-rescue · 影之刃零存档遗憾挽救

> **If you are an AI agent and a user just sent you this link, read "For AI agents" below first. / 如果你是 AI 助手，用户刚把这个链接发给你，先读下面的"给 AI 助手"。**

支线断了、剧情选错、成就错过？把这个仓库的地址丢给你的 AI 助手，它会自动找到你的存档，先做备份，再把遗憾补回来。整个过程中，你只需要回答它一个问题，然后重新读档。

## 给 AI 助手 / For AI agents

**What this is.** A skill for *Phantom Blade Zero* (影之刃零) save files. Receiving this link means the user wants you to find regrets in their save (failed or locked side quests, wrong story choices, missed achievements) and repair them. You do the work; the user only answers one question, closes the game, and reloads the save. Everything runs locally.

**Do this, in order:**

1. Get the files onto the user's machine. In Claude Code: `git clone https://github.com/B1lli/pbz-save-rescue ~/.claude/skills/pbz-save-rescue`. In any other agent: clone or download to any directory you can run commands in.
2. **Read `SKILL.md` in full** and follow it from step 0. It is the complete runbook (find save → backup → unpack → scan regrets → ask one question → fix → install → hand over). `$S` in it means the `scripts/` directory of this repo. Do not improvise from this README alone.
3. Requirements: Python 3.9+ with `pip install cryptography`, and Node.js. On Windows use `python` or `py -3`. Install what is missing yourself.
4. Safety rules, non-negotiable:
   - Ask the user's consent in one sentence before running `scripts/setup_oodle.py` (it downloads a third-party decoder and verifies its SHA-256).
   - Run `scripts/pbzsave.py backup <save folder>` before changing anything.
   - Install a modified save only after the user has fully quit the game.
   - Be honest: you cannot launch the game to test, and editing a save never unlocks Steam achievements.

**这是什么。** 用户把这个仓库地址发给你，就是请你帮他挽救《影之刃零》的存档。按上面四步做：把仓库放到本地 → 完整阅读 `SKILL.md` 并从第 0 步执行 → 装好 Python 3.9+（`pip install cryptography`）和 Node.js → 先备份、征得同意再下载解码器、让用户退出游戏后才替换存档。尽量自己完成所有操作，用户只需要回答一个问题、关闭游戏、重新读档。

## 玩家怎么用

1. 打开一个能操作你电脑的 AI 助手（Claude Code、Codex、[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 等都行；DeepSeek Harness 可从 [Releases](https://github.com/deepseek-ai/deepseek-harness/releases) 下载，或在命令行运行 `npx @deepseek-ai/dsh web`，第一次使用时在 设置 → 模型 里填上 DeepSeek API Key）。
2. 把这个仓库的地址发给它，说：**"用这个帮我挽救影之刃零存档里的遗憾"**。
3. 它问你怎么处理时，直接回 **"好"**，就会按默认方式把断掉的支线设为已完成。想自己在游戏里补玩的话，选第 2 项。
4. 它提醒你关游戏时，就把游戏关掉。改好之后打开游戏，读取最近的存档。

能做到的事：

- **找遗憾**：列出失败或锁死的支线、选错的分支，以及最后还能挽救的备份。
- **直接完成**（默认）：这个任务有配方的话，奖励、NPC 状态、剧情标记都会一起补上。
- **亲自补玩**（可选）：把你送回过去，玩完后把结果搬回最新存档，主线进度不丢。
- **补成就**：送你回还能达成条件的时间点，由游戏自己向 Steam 解锁。

动手前会备份整个存档文件夹，换回去随时可以；所有操作都在你的电脑上本地完成。

## 仓库结构

| 路径 | 作用 |
|---|---|
| `SKILL.md` | 给 AI 的完整操作手册（入口） |
| `scripts/` | `pbzsave.py`（找档、备份、解包、打包、安装）、`regrets.py`（扫描遗憾）、`complete_quest.py`（直接完成）、`transplant.py`（补玩后移植）、`achievements.py`（成就）、`setup_oodle.py` + `ooz_decode.mjs`（解压器） |
| `references/` | 存档格式、完整实例、任务中文名、任务配方 |

## 已收录的任务配方

| 任务 | 文件 |
|---|---|
| 见习医师 | `references/recipes/JianXiYiShi.json` |

如果你亲自补玩过某个任务，`transplant.py --save-recipe` 会把它保存成配方。欢迎提交 PR，让后来的玩家可以一键完成。

## 说明

- 这是非官方的玩家工具，与游戏开发商无关。修改存档存在风险，请保留好备份。
- 存档格式和密钥来自开源项目 [SaveSmith](https://github.com/gundamff/SaveSmith)（MIT 协议）；Oodle 解压用的 oozextract（MIT 协议）由 `setup_oodle.py` 在征得同意后下载并校验哈希。游戏更新后存档打不开时，运行 `pbzsave.py update-key`，会从上游拉取新密钥。
- 本仓库采用 [MIT 协议](LICENSE)。
