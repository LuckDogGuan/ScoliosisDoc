# 设备测试：摄像头与背光预检（2026-10-15）

已完成软件实现和开发构建，未刷机、未覆盖安装、未启动或重启实板服务。完整硬件状态需要上、下位机同时更新；现有正式发布目录、版本号和 tag 保留。本目录为核对记录，不是发布包。

## 页面行为

- 进入设备测试后自动检测并持续刷新；顶部展示仪器连接和主服务响应情况。
- 摄像头分别显示传感器驱动识别、RKiPC 进程、只读状态 RPC 和画面状态。未识别、服务未启动、接口无响应、画面获取/回传失败均有检查建议。
- 背光板显示 GPIO55 或 PWM11 输出回读；异常提示检查控制引脚、驱动、供电和接线。板子没有连接回读接口，物理连接一直明确标为待人工确认，点击点亮测试确认实际灯光。
- 提供重新检测和复制诊断信息，包含设备 ID、IP、固件、原始检测字段、画面接收和错误信息；不复制图像数据。
- 检测结果超过 6 秒失效；画面超过 8 秒未更新提示上一帧。连接中断后保留故障信息并停止测试控制。旧固件缺少字段时提示更新，不虚构正常结果。

## 检测依据和边界

相机从 `/sys/class/video4linux/v4l-subdev*/name` 读取本板启动配置支持的传感器名称，从 `/proc/*/comm` 读取 RKiPC 进程，并通过现有 `camera_status` RPC 检查响应。传感器驱动已经注册，不证明排线此刻仍连接；实际成像需结合持续收到的新画面判断。此功能不执行重启、I2C 扫描或设备配置修改。

相机探测在原有诊断工作进程中运行，先回传硬件状态，再获取预览。RPC/快照等待不在按键主循环执行。背光回读只读取当前持有的 GPIO/PWM 输出，不主动点亮。保留进入测试灭灯、显示已保存亮度、操作后点亮、退出和租约失效保护。

## 验证

- Flutter 全量 142 项通过；最后的通信失败、检测过期和清理补改后，9 项诊断/亮度/时长定向回归通过。`dart analyze lib test` 无问题。
- 下位机 ARM 构建通过（`-Wall -Wextra -Werror`）；传感器/进程/RPC 夹具、GPIO/PWM 回读、真实本机 UDP 诊断租约与亮度保存、稳定性、按键采样隔离、事件扫描延迟测试通过。
- Windows Release 构建成功：`D:/code/Scoliosis/ScoliosisFlutter/build/windows/x64/runner/Release/scoliosis_flutter.exe`，需要整个 Release 目录运行。`data/app.so` 和二进制 SHA256 见 VALIDATION.json。此为未单独版本化的开发构建。
- [页面预览](preview-fixture.png) 来自匿名故障夹具的 Flutter 渲染，非实板检测截图；已检查状态卡片、按键、亮度和操作按钮布局。400/900 宽状态面板及 900×600/1280×720 对话框布局测试通过。
- `flutter analyze --no-pub` 全目录扫描碰到既有 build 夹具文件名、缺少 name 字段及 tool 未使用 import；本次最终 lib/test 分析为零问题。没有清理这些非本次文件。

## 追溯和回滚

Flutter 基点 `01db0daea6f0fd9f0bc240231e549112558d18fd`，固件基点 `be5777f5dab40cd00d6f51c124e81a74318535f1`。改动尚未提交，属于独立工作树修改，不等同于正式版本发布；回退时仅检查本次列出的文件差异，保留既有工具改动和发布目录。

Flutter 变更限于 app_controller.dart 的诊断状态、diagnostics_dialog.dart、新增 diagnostics_health_panel.dart 和 diagnostics_health_test.dart。固件实际源码唯一在 WSL，变更限于 Makefile、include/platform.h、runtime_v3.c、light_test.c、新增 diagnostics_health.c 及三份相关测试；CHANGELOG/validation 记录同步更新。

编辑前 GitNexus：开始/结束测试 HIGH，共享 AppController CRITICAL，直接调用为测试弹窗、升级工具及测试替身；pollDiagnostics 和界面刷新 LOW。固件 receive_udp/diagnostics_tick 各一个直接调用、最终进入应用主流程，LOW。最终 detect_changes：Flutter low，固件临时索引 high。已逐行核对实际 Git diff；索引把新增函数旁的既有背光函数、头文件声明也算作 touched，临时索引 AGENTS 差异不属于实际 WSL 改动。新文件还需以实际文件清单核对，不能只凭 detect_changes 断言完整覆盖。未提交或部署。

协议回复沿用 `board_to_pc` 日志，通信异常分别记 `diagnostics`、`diagnostics end`；现场排查可直接复制页面诊断信息。实板的断线/未启动服务/灯板实际点亮/恢复连接和冷启动验收仍待进行。
