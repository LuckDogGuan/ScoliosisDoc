# 通用仪器测试工具

交付文件：`release/仪器测试工具.exe`。复制这一个文件到单独文件夹，插 USB，双击启动。无需 Python、Android SDK、外部 ADB、INI 或脚本；日志和报告在运行时生成。Windows 仍需要正常识别板卡的 USB 驱动。

## 使用

1. **三个按键**：刷新并选择 USB 板卡 → 开始测试 → 左、中、右各按下并松开一次。按住时变橙色，完成按下和松开才通过。支持次数、持续时间、左+右组合和保存报告。
2. **USB 摄像头**：检测摄像头连接 → 进入 USB 摄像头模式 → 预览。工具先确认传感器、板型和媒体库兼容，再安装内置官方组件；Windows 识别目标设备后实际读帧才算出图通过。
3. 停止预览会释放摄像头，可用 Windows 的摄像头查看软件选择 **ISG1321 USB Camera**。返回按键测试需断电重启板卡，再刷新设备。

多块板卡按序列号选择。UVC 通过 Windows USB 父设备关联同一板卡，不使用同名匹配或内置摄像头兜底。换板会清空上一块板的结果。

**检测含义**：传感器被内核识别、Windows 枚举 UVC、收到有效画面是三项独立结果。没有画面可能来自摄像头服务、占用或权限；不能直接认定排线断开。排线只能在断电后调整。

## 支持条件和恢复

- 当前组件支持 Pico Zero RV1106、ARM/uClibc、ISG1321，以及与已验收板卡媒体库 SHA-256 一致的固件。兼容性检查失败会显示缺项，工具不刷整机固件。
- 组件来自 [Luckfox 官方 SDK](https://github.com/LuckfoxTECH/luckfox-pico)，固定提交 `824b817f889c2cbff1d48fcdb18ab494a68f69d1`；依据 [官方 UVC 教程第 6 节](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/CSI-Camera/)。许可与组件哈希在内置 `payload` 中。
- 板端测试文件仅安装到 `/tmp/instrument-uvc-test`。不覆盖 `/opt/instrument`、已有版本包、默认启动脚本、配置或待传视频；重启恢复原 USB ADB 模式。
- 已运行的 V3 仪器会先通过本机 UDP 查询确认无录像、上传、播报、配对窗口或拍摄授权，再以 SIGTERM 停止业务。无法确认空闲或业务未退出时拒绝测试。开始按键测试同样避免触发仪器业务；测试后重启恢复仪器程序。
- 默认请求 1280×1080、30 FPS；当前实板实际接收约 58.6 FPS。界面和报告显示实测值，不保证传感器实际工作在 30 FPS。

## 开发与复现

Windows：Python 3.12、OpenCV 4.13.0、Pillow 12.2.0、PyInstaller 6.22.3，并使用已安装的 pygrabber/comtypes。运行 `python 仪器测试工具.py --check` 完成回归检查。`build.ps1` 会校验组件 SHA-256，并执行单文件、无控制台打包；`-AdbDir` 可指定构建时官方 platform-tools 目录，这个路径不是 EXE 的运行依赖。

板端源码、参考媒体库和可重复构建脚本保存在 WSL2：

```text
/home/guanjx/luckfox/Scoliosis/validation/usb-uvc-tool-20261002/
  build_uvc.py       # CMake 构建；不调用上游递归清理 Makefile
  udp_query.c        # 仅向 127.0.0.1:37020 查询状态
  official_uvc_source/
  reference-libraries/
  payload/
  BUILD.json
```

在 WSL 下位机根目录运行 `python3 tools/uvc-v1.0.0/build_uvc.py --output /home/guanjx/luckfox/uvc-rebuild`，重新编译官方程序。构建只将官方 C 文件的配置路径改到独立 `/tmp` 目录，USB 描述符复用官方函数并收窄为单路 ISG1321 MJPEG。构建材料唯一保存在 WSL `tools/uvc-v1.0.0/`；Windows 工具现有 `payload` 保留唯一运行/打包输入，构建材料校验与原 payload 校验可追溯；不再保留 image 副本。

开发验收命令：`python 仪器测试工具.py --acceptance 600 <输出.json> --switch --validation-reboot`。`--validation-reboot` 仅用于实板验收，安排超时重启恢复 USB ADB；正常 GUI 不安排定时重启。已处于 UVC 模式时省略两个末尾选项。

验收记录位于 `调试/记录/usb-uvc-tool-20261002/`。模拟回归、软件读取和实体按键、排线及物理断电验收分别记录。
