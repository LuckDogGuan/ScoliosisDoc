# 全部现存视频验证（2026-10-16）

源工作区：D:/code/Scoliosis/ScoliosisFlutter/build/ui-review-workspace。
本次编号按现存文件排序，不沿用上一份最近五条报告编号。共 10 个现存 MP4，全部重新解码、每 2 帧取 1 帧，再运行已交付 3.3.21 的第四轮原生 DLL、方案 A、SQLite 双份保存与标准导出。另有 10 条数据库录像的原文件已经缺失，已单列，未冒充重测。

## 结论

- 当前固定构图的 V05–V08 可以运行并产生曲线，原始有效 655/684（95.76%），各段为 90.9%–98.9%；推断 29 点。
- V01–V04 的旧构图全部拒读，原因“亮度或画面发生变化”；V09–V10 全部拒读，原因“超出右侧标定范围”。这 6 段没有生成假角度或假 0°，状态为 failed。
- 10 段共采样 1413 点，4 段完成、6 段拒读；全流程合计 94.801 秒，单段 5.214–13.577 秒，包含哈希校验、FFprobe、PNG 抽帧、DLL 模型加载/计算、原始及美化结果保存，不包含界面重绘。不是纯算法耗时基准。
- 补齐的最长连续缺失为 V08 的 10 点，邻接有效时点跨度 0.766 秒。补齐仅是假设，画面平滑不证明这些点是真值。
- 旧构图/另一设备的这些录像不能直接使用当前固定模型。拒读符合当前模型保护条件，但没有人工标注清单，不能把它统计为“无效视频识别准确率 100%”。
- 已查看全部视频在 10%/50%/90% 时刻的画面；未逐帧人工角度标注，因此本次仅确认执行、拒读、插补和导出一致性，不作角度误差合格声明。

## 已完成检查

实际 AnalysisQueue/AngleAnalyzer/SignedReader 调用，DLL 和 model.bin 清单校验，每段输入哈希前后不变；原始/美化数量与 PTS 对齐，双份落盘与直接方案 A 计算一致；全部拒读无推断。标准 Excel 包含 10 段记录，4 张有效曲线，684 个数值与保存的美化结果逐点一致；拒读视频保留失败记录，不绘制假曲线。

测试通过：flutter test --no-pub --concurrency=1 tool/ruler_all_video_validation_test.dart。
静态检查：dart analyze tool/ruler_all_video_validation_test.dart 无问题。
测试工具提交：2e800c720f76e589cb62c59f5ea021dd6f323c95。正式业务算法未修改，没有重建安装包或替换运行程序，也没有改写源工作区结果。

## 查看文件

- 全部视频测试报告.html：全部 10 段详情、原始/美化曲线、原视频入口与画面抽查。
- 全部曲线总览.png：10 段总览，整段拒读保持空白。
- 全部视频_美化结果.xlsx：复用正式导出，美化结果。
- 全部视频_汇总.csv / 全部视频_美化逐点.csv：UTF-8 BOM，便于 WPS 查看。
- results.json：原始值、失败原因、美化值、推断标记和耗时。
- inventory.json：源路径/哈希、视频信息、原文件缺失清单。
- source-verification.json：源数据和视频未变的校验；pipeline.log 为本次实际运行日志。

测试数据库及视频副本仅在 results.json 的 validation_workspace 指向目录。只读在线源数据库备份位于 D:/code/Scoliosis/ScoliosisFlutter/build/all-videos-source-backup-20261016.sqlite3，不进入 Git。未使用的全尺寸抽查帧由本目录 .gitignore 排除；条带图及视频海报作为审阅证据保留。

复现：保留 inventory.json 对应的原文件，先在 Flutter 根目录运行上述测试，再在 Luckfox 根目录运行：

```powershell
python 调试/工具/ruler_all_video_report.py --output 调试/记录/ruler-all-videos-20261016
```

绘图工具只读取实际保存的结果，不重新实现补齐算法；美化连线按当前上位机有界三次控制点绘制。源数据库原始读数与已有状态逐点未变，10 个原文件 SHA256 全部复核通过。
