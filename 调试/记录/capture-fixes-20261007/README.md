# 2026-10-07 短视频、背光亮度、调试画质与东八区

目标实板：序列号 `41eda5f2c5b00de1`，应用ID `CAM-41eda5f2c5b00de1`。已安装并启动3.3.4；安装完成并恢复服务时配置、配对SHA-256相同。随后17:32:10电脑端发来unpair，仪器确认解绑；最终配对文件随该业务操作改变，配置哈希仍相同。当前未配对，使用新版Flutter需重新配对。另一个设备未操作。现场已核对空闲、许可关闭、无写入/上传/音频/设备测试后执行。

## 交付

- Flutter源码提交`2193f06`，小屏布局补丁`c2d2b60`；静态分析与Release验证均通过。
- Flutter：`D:/code/Scoliosis/ScoliosisFlutter/releases/windows-c2d2b60-20261007/Release/scoliosis_flutter.exe`，需关闭旧程序后从这个Release目录启动，DLL/data目录必须保留在旁边。
- 完整固件包：`\\wsl.localhost/Luckfox-Ubuntu-22.04/home/guanjx/luckfox/Scoliosis/releases/3.3.4/instrument-v3.3.4.tar.gz`。
- 固件源码：WSL2 `Luckfox-Ubuntu-22.04:/home/guanjx/luckfox/Scoliosis`；源码提交`ae9e194`，包BUILD.txt锁定该提交。
- 包SHA-256：`a19337728116c1f9da408feb2ed04d9e7ec3757c150e8330b63b8f6f7eb38462`。

## 已实现与验证

1. 不足3000ms标为short并重拍；设备begin_upload和Flutter授权端同时阻止上传，保留仪器中的短视频。旧固件2–3秒success完成事件在新Flutter中归类short后正常确认，待传清单也归类short。已经上传的历史文件不自动删除。
2. Flutter“设备→设备测试”加入0–100滑杆，松手发送并以设备成功回复更新；不支持该能力的旧固件禁用。保存到`/opt/instrument/state/backlight.json`，拍摄沿用保存亮度；测试开始关闭、结束/租约超时关闭。真实GPIO55硬件PWM11_M1（ff490030，1kHz）25/50/75/100占空比分别250000/500000/750000/1000000ns，0关闭；实板退出与超时均读回0。最终保存亮度100，实体输出关闭。见`brightness-board.json`。
3. JPEG质量70→95，缓冲/上下位机传输上限4MiB，保留传感器原始1280×1080；预览区域加大并使用高质量缩放。实际JPEG342726字节，完整1280×1080解码，见`diagnostic-quality95.jpg`。近距离抓拍仍有虚焦和强反光，不能用压缩改善宣称已解决光学问题；用户已确认镜头能旋转调焦，将自行调焦后复测。
4. 系统`/etc/TZ=CST-8`，相机进程`TZ=CST-8`，应用自行设置同一时区。抓拍OSD实际显示`2026-10-07 17:32:02`；诊断录像开始记录`+0800`。系统时钟、RTC、Unix毫秒继续UTC，未把epoch加8小时；Flutter北京时间显示与跨日、已有+08:00输入测试通过。见`timezone-camera-after.txt`、`camera-board.json`。

## 验证证据与边界

- 固件真实completed/begin_upload主机测试覆盖1999/2000/2999/3000ms；真实UDP协调器覆盖亮度范围、诊断token、租约、结束/到期、持久化；GPIO手势、五种灯态、配对窗口、上传、回执和删除回归通过。ARM构建、完整包防篡改/安装空闲检查通过。
- Flutter真实HTTP/UDP授权回归、短视频历史清单、新旧完成事件、三秒阈值、UTC+8、失败亮度回复测试通过；既有续拍/删除/历史筛选/名单流程回归通过。静态分析无问题，Windows Release构建通过。
- 实际相机controlled录像2501ms与3201ms，均1280×1080、完整解码，分别73/93帧，媒体时长2.5167/3.2333秒；诊断录像只保存在专用备份根，未进入业务待传目录，也未替用户创建学生关联。见`video-decode.json`。
- 实际按钮操作→学生归属→短视频重拍→长视频上传的整条业务链尚待用户按键复测；主机回归与相机诊断录像不能代替这一步。
- 未查到G24D-5733控制端可靠规格；主板PWM输出已验证，模块实际亮度变化、闪烁、镜头调焦、断电再开均需现场验收。

## 安装、服务与回退

安装前`/RkLunch.sh`哈希与3.3.3源码一致，已审阅差异，仅增加东八区和JPEG质量/缓冲设置。安装器记录：`/opt/instrument/backups/bundle-20261007T092809Z-2260`，`result.txt=exit_code=0`，内有原文件`rollback-files.tar`、新增路径`new-files.txt`、安装前后校验。`/etc/TZ`纳入安装路径记录。

相机原配置与额外诊断：`/opt/instrument/backups/capture-fixes-20261007-1791365275`，原配置`rkipc.before.ini`，修改后`rkipc.after.ini`，配置/配对原校验`business.before.sha256`。当前业务配置、配对、Wi-Fi、历史视频保留。

首次ADB短会话后台启动未保持进程；已改为`nohup`并等待启动后再断开ADB命令。最终业务父进程3316、相机3105正常运行；短暂同名子进程是正常上传/维护worker，不能据此当成多个业务主进程。最终以`after.json`及实际父PID为准。

需要回退时先核对设备身份、许可关闭及空闲，停止instrument_app/rkipc；从上述安装记录恢复明确旧路径，新增/etc/TZ原先不存在，可先移到本轮备份目录，再从`rollback-files.tar`恢复。相机配置恢复`rkipc.before.ini`。重新启动相机时保留`LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so`，回退后核对版本、配置/配对校验与相机。不要删除capture/state或待传录像，不要对其他设备套用本轮路径。

解绑证据：`unpair-final.json`，17:32:10，source_endpoint=192.168.101.2:51099，sequence=3095，ok=true。本轮部署/亮度/相机验收脚本没有发送unpair，不自动覆盖或恢复该配对状态。

现场复测：关闭旧程序，打开新版Flutter→重新配对目标仪器→设备→设备测试，检查0/25/50/75/100的实体亮度，旋转镜头并对准正常工作距离文字，结束测试检查熄灭；随后拍约2秒应提示重拍且不上传，拍约4秒应正常上传；核对画面/记录时间。完成这些人工项目后再做断电重启验收。


2026-10-07 归档整理：正式固件包唯一放 WSL；源码快照核对后移除，提交及 SHA256 对应关系见 `../release-organization-20261007/README.md`。以上实板验收边界不因整理而改变。
