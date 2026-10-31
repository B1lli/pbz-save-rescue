# 后悔药 (pbz-regret-pill)

影之刃零（Phantom Blade Zero）存档「遗憾挽救」skill：解密 `PBZSaveGame.sav`，找出失败 / 被锁死 / 错过的支线与选错的剧情，利用游戏自带的滚动备份找到最后可挽救的时间点，重玩后把差异移植回最新存档，并协助补回错过的成就。

A skill for Phantom Blade Zero save rescue: decrypt `PBZSaveGame.sav`, locate failed / locked / missed quests and wrong story choices, find the last rescuable point in the game's rolling backups, replay there, then transplant the resulting diff into the latest save. Also helps with missed Steam achievements.

## 用法 / Usage

把整个仓库放到 Claude Code 的 skills 目录下（目录名 `pbz-regret-pill`），例如：

```bash
git clone https://github.com/B1lli/pbz-regret-pill ~/.claude/skills/pbz-regret-pill
```

完整流程见 [SKILL.md](SKILL.md)；格式说明见 `references/`。需要 Python 3（`cryptography` 或 `pycryptodome`）与 Node.js。

Oodle 解压器由 `scripts/setup_oodle.sh` 从开源项目 [SaveSmith](https://github.com/gundamff/SaveSmith) 下载并校验 SHA-256。

操作前务必备份整个存档文件夹；本工具产出一律写成新文件，不覆盖原存档。
