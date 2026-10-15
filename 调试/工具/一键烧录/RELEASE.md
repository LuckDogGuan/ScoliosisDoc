# 一键烧录工具 1.2.0 — 2026-10-15

新增 Wi-Fi 烧录和独立命令行，复用原有安装器、备份、校验和 USB 模式。

- GUI：[下位机一键烧录.exe](release/下位机一键烧录.exe)，23206476 字节；SHA256 `4809937be9194ddb83776a8dab244598565d8ec473c78523e72bb85f2d2640fa`。
- CLI：[下位机烧录CLI.exe](release/下位机烧录CLI.exe)，23210131 字节；SHA256 `590eba3538b2321dc776c5f86c628d7e7942d7bfcf1adf62c08f6dac47279a6c`。
- 旧版回退：`release/回退/下位机一键烧录-1.1.1-20261015-before-wifi.exe`，SHA256 `342a5628fade9aefd0f47cd17fd109f465b064953d9b6243ee4d92e0bb52f80c`。

使用和 CLI 命令见 [README](README.md)。构建环境 Python 3.12.10、PyInstaller 6.22.3、Paramiko 5.0.0；运行电脑无需 Python。

16 项回归通过，包括原 9 项 USB/选包保护、真实 SSH 3 MiB 流式上传下载及哈希、身份/密钥/nonce/来源校验、忙碌拒绝和 Wi-Fi GUI 连接门禁。最终 CLI EXE 的发现、检查、同版本安装校验及参数错误退出码通过。

当前唯一在线仪器 CAM-211ec7045815bf02（Wi-Fi 192.168.101.7）原为 3.3.11，本轮通过源码 CLI --wifi --install --force 重新安装指定正式 3.3.11 包，保存回退后重启。版本、安装文件 SHA256、服务、相机 RPC、配置/配对/Wi-Fi 保留及新 boot_id 均通过；最终打包 CLI 再执行 --install，同版本只校验通过，没有重复安装。

完整安装路径全程使用 Wi-Fi/SSH，未调用 ADB；重启后的状态查询复用板端 udp_query，因此包内日志 host_id 仍可显示 usb-flash-tool，日志 transport=wifi-ssh 才是本次传输方式。

实测记录见 `调试/记录/wifi-flash-20261015/`。原始现场日志、回退归档、设备连接缓存仅保留本地。未重复 USB 实机烧录、物理拍摄/按键/声音/灯光或断电冷启动验收。首次 SSH 身份绑定采用首次使用信任，后续密钥变化会拒绝连接。
