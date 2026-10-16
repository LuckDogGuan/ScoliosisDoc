# 方案 A 接入记录（2026-10-16）

用户选定方案 A；每 2 帧取 1 帧不变。DLL、模型、实时预览及下位机不变。

原始表 angle_samples 保留原始值、null 及原因；美化表保存推断标记、处理版本，元数据保存原始 SHA256、参数、生成时间。原 PTS 线性补齐，首尾最近值，±180ms 三角加权平滑；无有效参考则留空，明确数值超出 ±10° 不显示。

显示、峰值、筛查分区、筛选和 Excel 取同一份美化值；识别成功率不包含推断点。旧记录无需原视频；重启不重复平滑。取消/删除保护覆盖双份结果，附加表保持 user_version=4，旧版可继续读取原始数据。

## 已验证

- 完整 Flutter 串行回归 166 项通过；实际五条回放及测试目录隔离检查通过。
- dart analyze lib test tool/ruler_option_a_review_test.dart 无问题；Windows Release 构建成功。
- 最近五条 485 点，原有效 446，推断 39，补齐后 485；最大 A 参考差 1.95e-14°。
- 控制器、数据库缓存和 Excel 曲线的 485 个值逐点一致。PNG 是实际 Flutter 控件截图。
- 通过只读在线备份和隔离副本验证；原始数据逐点未变。既有 sidebar 测试曾创建空辅助表，已撤回测试新增空表并改用临时目录。
- 未覆盖运行中的 3.3.20 程序。WPS 人工及新安装包交互验收尚未执行。推断数据没有新人工真值标注，平滑不能证明识别精度提升。

实现提交 726baba；测试隔离修复及打包基线 d696b78。
正式安装包及 ZIP 唯一在 Flutter 的 releases/windows-3.3.21-d696b78；本目录只存证据。
备份：D:/code/Scoliosis/ScoliosisFlutter/build/option-a-validation/source-backup.sqlite3。
复现命令见 Flutter docs/ruler-option-a.md；数据指纹和逐点结果见 results.json / beautified.json。
