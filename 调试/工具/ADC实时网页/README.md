# ADC 实时网页

双击 `启动网页.cmd`，打开 http://127.0.0.1:8766 。需要 Python 和已授权的 USB ADB 连接。

默认只读取设备 `3253c006806f5194`（Pico Zero / CAM-000123）的芯片 SARADC0、SARADC1。每次读取校验序列号和 ADC 名称，仅执行 cat，不修改引脚或板端文件。

网页每秒采样，显示两路电压、原始值、最近60秒曲线和最近成功时间。断开或超时时清空当前电压并显示错误；恢复连接后自动重试。电压 = raw × scale / 1000，单位 V。当前 Pin33/34 接线不对应这两路 ADC，页面读数不能作为电池电压。

在此目录运行 `python server.py` 可前台启动，Ctrl+C 停止。后台启动后可在任务管理器按“命令行”找到此目录 server.py 对应的 Python 进程并结束。

调试：`python -m unittest test_server.py`。

本工具属于 Windows 调试工具。下位机 C 示例仍位于 WSL2 `/home/guanjx/luckfox/Scoliosis/tools/adc-test-20261009`。
