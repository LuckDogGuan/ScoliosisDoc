# 三仓库发布与清理核对 — 2026-10-07

## 所有权与 Git 层级

- 下位机源码、构建和正式发布包唯一在 WSL `/home/guanjx/luckfox/Scoliosis`；当前整理提交 `b6e6c66`。
- Windows Luckfox 只管理调试工具、说明和证据。工具、验收记录、发布整理分别提交，明确暂存文件。
- Flutter 独立管理应用；Excel 兼容性修复提交 `e531ca1`。三个仓库均无远端，本次未推送。
- 正式固件目录只保留包及元数据。既有 tag 未移动，既有压缩包 SHA256 未改变。

## 正式固件与 tag

| 版本 | 源码提交/基点 | tag | tag 指向 | 包 SHA256 |
|---|---|---|---|---|
| 3.1.0 | `82e16b4` (source_base_commit) | `instrument-v3.1.0-20261001` | `6170d07` | `b11e3318617f9de9f1e83f8db46e5b9c5936b862e8470893fa85ec0ddef20922` |
| 3.2.0 | `d2a18f9` (source_base_commit) | `instrument-v3.2.0-20261002` | `3a3ac12` | `a3a73d6bbe5631687309108cf808921af5a1ac2acebc14a0612bde81c7962649` |
| 3.2.1 | `3a3ac12` (source_base_commit) | `instrument-v3.2.1-20261002-records` | `cf03f38` | `55288f5309f31c287a65313767a7570e37c795e49b1e2b9efe5764e60d003f5f` |
| 3.2.2 | `3a3ac12` (source_base_commit) | `instrument-v3.2.2-20261002-records` | `cf03f38` | `d279130290ad1d0a03375872f4b44a8583c74314bd7cab9328bbf0a1803e5072` |
| 3.3.0 | `b3ec43e` (source_base_commit) | `instrument-v3.3.0-20261004-minmax-volume20` | `19bba16` | `b4cf975d1c3a4076f42ae366c578d4f14727e7ea82d20ee3fda8b22740e94b71` |
| 3.3.1 | `1f45fd2` (source_commit) | `instrument-v3.3.1` | `1f45fd2` | `8780eeec1541db89924eef45b03b3c019bf3672f9c8fda481ed9832c275ddc8b` |
| 3.3.2 | `690329b` (source_commit) | `instrument-v3.3.2` | `690329b` | `a01b07ee21bf42d2db22cac987652e07310188190ab58d6b4e4046cf0bd2fd82` |
| 3.3.3 | `935ca06` (source_commit) | `instrument-v3.3.3` | `4542e1b` | `ff7caea750bbb134bd5d897ac26aba0164606842ef8cbb1434e4376122eec947` |
| 3.3.4 | `ae9e194` (source_commit) | `instrument-v3.3.4` | `f56e632` | `a19337728116c1f9da408feb2ed04d9e7ec3757c150e8330b63b8f6f7eb38462` |

3.3.3/3.3.4 的 tag 指归档提交，BUILD 指源码提交，两者不是同一个概念。
旧版 source_base_commit 只记录基点，不宣称包含当时所有未提交内容。
3.2.1/3.2.2 原 tag 缺失，本次补建到归档提交 cf03f38，注释明确补建日期与历史来源。
3.1.0/3.2.0/3.2.1/3.2.2 原只有 payload，本次原样封存并逐文件比对；未重新编译。
所有 9 个版本的外层/包内校验、完整解包比对通过，详情见 firmware-releases.json。

## 回退及历史审计资料

- 改造前基线：WSL `releases/baseline-20261001`，保留旧二进制、启动脚本及原源码归档，未证明可逐字节重编译旧二进制。
- 两份包含独有内容的旧源码镜像：WSL `releases/baseline-source-audit-20261001`，标签 `instrument-baseline-source-audit-20261001`，187 个非缓存文件逐字节封存；嵌套旧 Git 有缺失对象错误，已保留原审计数据，不宣称旧仓库完整。
- 另外三份源码索引副本均可从 WSL 可达 Git blob 恢复；本轮最新快照的 28 个 src/include 文件与 ae9e194 逐 SHA256 相同。
- UVC 构建源码唯一在 WSL `tools/uvc-v1.0.0`；Windows 测试工具的必要 payload 与正式 EXE保留。外部 SDK、板端库和交叉编译器未删除。

## Windows 本地交付与清理

- Flutter 当前交付：[启动程序](../../../../ScoliosisFlutter/releases/windows-c2d2b60-20261007/Release/scoliosis_flutter.exe)，必须连同整个 Release 使用。
- 两份 Release 的 app.so 不同，逐文件核验后分别保留；来源未确认的旧变体及原 7z 保留，不当作重复删除。
- Excel 修复已测试但本次未重建 EXE；当前交付按原验收记录来源为 c2d2b60。
- 已清理 Windows 下位机包/源码副本、Flutter build/.dart_tool 和测试工具 .build/字节码。明确统计释放 2,486,842,697 字节（另有首次源码镜像清理未计入容量），逐项见 cleanup.json。
- Flutter data、integration-data、rollback 以及真实照片/视频、实板日志保留。有差异的 .uvc-build-input 保留。

## 验证边界

工具源码自检 7 组、Flutter 14 项定向测试及静态分析通过；发布流程 6 项检查通过（校验与解包一致、校验后清理、重复 finalize 只读、非法标签及重复版本拒绝）。
提交前执行 GitNexus detect_changes；Shell 发布脚本 impact 无符号识别，结果 UNKNOWN，另查调用与实际打包流程。二进制/归档及删除路径额外用 Git diff 和逐文件哈希核对。
本次只做本地归档和 Git 整理，不操作实板，不新增硬件验收结论。

三个恢复/审计目录均在 WSL releases，标签分别为 `instrument-baseline-20261001`、`instrument-baseline-local-20261001`、`instrument-baseline-source-audit-20261001`；原本地 baseline 两个 tar 也已原字节封存并归位。

GitNexus 的中文路径差异须关闭本次进程 core.quotepath 转义再调用 detect_changes；工具拆分提交显示 CRITICAL（69 符号/30 流程），记录其范围并通过自检，不宣称替代实板验收。Shell/二进制/归档不具备完整符号覆盖，额外以实际 Git staged 路径和哈希检查。
