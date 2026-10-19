# 3.3.10 交付历史附件 · 2026-10-13

2026-10-19 将现有未跟踪的交付附件归入 Git，原位置和字节保留；本次未重新构建、安装或操作设备。

| 文件 / 目录 | 历史用途 |
| --- | --- |
| `source-validation.json` | 当时源码及打包检查的汇总；具体命令、数量与结果以原记录为准 |
| `flash-install.json` | 当时记录的 3.3.10 / 烧录工具 1.1.1 安装结果、设备及包证据 |
| `first-build-not-accepted.json` | 未被接受的初次构建，保留失败边界 |
| `speech-*.json`、`icon-validation.json` | 语音、焦点和图标核对 |
| `tests/`、`installer-validation/` | 构建、安装器、显示及失败场景日志 |
| `git/` | 当时各仓库 impact、detect_changes 与审计材料 |
| `database-backup-index.json`、`cleanup.json` | 本地备份索引与清理记录 |
| `ARCHIVE-SHA256.json` | 本次归档的原始文件 SHA256 |

`backups/` 和既有 `.gitignore` 中排除的截图继续只留本地；其原始索引保持有效。这里的历史 `git/*.json` 不替代本次提交前重新运行的 GitNexus 检查。
