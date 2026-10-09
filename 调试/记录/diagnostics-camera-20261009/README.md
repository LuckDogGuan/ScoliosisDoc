# 摄像头等待与按键默认状态 — 2026-10-09

用户要求只用1号显示器。不开第二个筛查程序，不操作2号显示器。实体按键此前已确认完好，本轮只核对状态显示。

目标CAM-41eda5f2c5b00de1，SSH密钥与序列号核验通过；初始Wi-Fi在线、idle、无当前拍摄／上传／诊断租约、未配对。相机服务原PID437，instrument_app PID162，IPC套接字存在。

## 红色信号

刚才真实测试日志连续diagnostics_camera=jpeg_timeout、diagnostics_frame=failed；UDP诊断续期成功。直接用现有socat转发执行同一rk_take_photo接口，返回0但等待3秒没有新JPEG，断言失败；/video0仅有一份10月7日的0字节旧文件。RTSP探针也未取得有效数据。不是单纯HTTP上传、Flutter绘图或相机服务不存在。

相机配置enable_jpeg=1，输出目录存在且空间充分。只对空闲目标发送TERM重启相机：8秒未退出时拒绝重复启动，后续确认原进程已退出。首次手动启动少了设备环境的动态库路径，记录librockit.so缺失；补齐/oem/usr/lib路径后启动相机PID1427，instrument_app PID162未变。

## 恢复证据与边界

重启相机前后rkipc.ini SHA256均为39c6ee7ed47f78568ae5585cd3f5a1f7e84a29979c310306b7a6654fe2bb07ab。未改摄像头配置、固件或配对文件。相同抓拍接口重新运行得到130511字节JPEG，RTSP探针成功取帧，见snapshot-probe.json、camera-restart.json。现有SDK定义rk_take_photo会请求一次JPEG，但返回值不独立证明图像已生成，见[Luckfox官方实现](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/app/rkipc/rkipc/src/rv1106_ipc/video/video.c)。

3.3.5→3.3.7的luckfox_camera.c、runtime_v3.c和RkLunch.sh无差异；Flutter2446f62→5852c50的diagnostics_dialog.dart无差异。因此已确认本次是板端出图服务运行失效并经重启恢复，导致失效的底层触发因素尚未确定；不宣称已解决所有冷启动／长时间运行场景。

## Flutter3.3.5

代码956dc97：按键未收到状态时显示松开，收到按下位时正常显示按下，保留内部未知值和断线／租约状态，未更改板端按键控制或拍摄联锁。摄像头等待8个1秒轮询周期后给出未收到画面的明确提示。默认状态失败测试先复现，再修正通过；3项诊断界面回归、静态检查通过。完整包见flutter-release.json。

尚待在用户放到1号显示器的唯一主窗口中重新合法配对，确认设备测试显示连续预览；不以RTSP截图替代完整GUI验收。探针JPEG保留在板端，未删除既有文件或创建学生采集记录。
