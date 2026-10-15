# Wi-Fi 烧录与 CLI 验收 — 2026-10-15

已对当前仪器 **CAM-211ec7045815bf02** 完成指定正式包 **3.3.11** 的 Wi-Fi 重新安装与重启校验，交付烧录工具 **1.2.0**（GUI + CLI）。

## 当前设备与安装证据

- 本次发现地址 `192.168.101.7`，板端序列号 `211ec7045815bf02`；与 SSH 读取的仪器 ID、Pico Zero/ARMv7 型号和 wlan0 地址交叉核对。SSH 指纹与历史已验证原厂镜像指纹一致。没有沿用旧仪器的地址/序列号。
- 设备原已为 3.3.11，本次源码 CLI 使用 `--wifi --install --force` 完成同版本重新安装，15:49:54 安装成功，15:50:22 重启校验成功。没有声称由旧版本升级。
- 正式包唯一来源：`\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\releases\3.3.11\instrument-v3.3.11.tar.gz`；包 SHA256 `32ee73984cc1c5033d13a926e3329d326be7d23d3bb38d8a37cd35a58612b1df`。
- 程序 SHA256 `0bf506caa0746689e635993aae299fb8084f0fa29f23a8df3a6622f4e34cfd04`；全部安装文件、instrument_app/rkipc 进程及相机 RPC 检查通过。
- 新 boot_id `CAM-211ec7045815bf02-d5764013`，与安装前 `CAM-211ec7045815bf02-a0571992` 不同；最终 idle、Wi-Fi available、camera_fault=false，拍摄许可关闭，无拍摄、上传、诊断或声音任务。
- 配置、配对及现有 Wi-Fi 配置哈希保留；安装前业务配对为空，安装后仍为空，没有替用户创建或接管业务配对。
- 回退位于板端 `/opt/instrument/backups/bundle-20261015T074949Z-1038`，本地已导出 rollback-audit.tar，SHA256 `deb0e7546ec258cd3f2f6b629fc5a33e294df3a94fe40f4cb1a7cfca50635645`。

## 工具交付与检查

- [使用说明和 CLI 命令](../../工具/一键烧录/README.md)，[二进制版本及哈希](../../工具/一键烧录/RELEASE.md)。
- 最终 CLI EXE 对实机执行 `--wifi --check` 成功，再执行省略 IP 的 `--wifi --install --device-id ... --package ...`，自动发现设备并报告“已是 3.3.11，校验通过”，退出 0，没有再次安装。另验证发现 JSON、互斥参数退出 2、只给 IP 不给 ID 退出 2。
- 16 项回归通过：原 USB/包校验/GUI 9 项，Wi-Fi 新增 7 项，包括真实本机 SSH 3 MiB 二进制上传下载哈希、远端非零退出、来源/nonce/ID 校验、主机密钥变化在认证前拒绝、身份错误在暂存前拒绝、忙碌门禁、Wi-Fi GUI 未连接不可安装/连接后才启用。
- 安装与检查复用原安装器，不改下位机源码；Wi-Fi 模式覆盖传输层，全程无 ADB。板端状态查询仍使用既有 helper，日志中的 `host_id=usb-flash-tool` 不是传输方式，实际每项传输日志为 `transport=wifi-ssh`。
- 新功能影响分析按当前分支索引核对：gui LOW（1 个直接引用），wifi_devices LOW（1 个直接调用），wifi_exchange LOW（3 个直接调用、2 个流程），execute LOW（2 个直接调用、1 个流程）。初查默认 main 索引未识别新符号，刷新并显式选择当前分支后重做；未把 UNKNOWN 当作通过。
- 工具提交前 `detect_changes(scope=staged)` 为 HIGH：7 个文件、49 个符号、9 个流程，均在烧录工具/测试/说明范围内。已向用户报告并逐项核对；原 Installer USB 安装实现未修改，共享的安装/重启链路经过 Wi-Fi 实机验证。见 [范围扫描摘要](gitnexus-staged-summary.json)。

摘要及文件哈希见 [acceptance.json](acceptance.json)。原始 operations.jsonl、回退归档、连接缓存含现场配置，只留工具目录的本地“记录”，不提交 Git。旧 GUI 1.1.1 备份位于 `release/回退/下位机一键烧录-1.1.1-20261015-before-wifi.exe`。

## 验证边界

本轮验证 Wi-Fi 安装、重启和软件状态，未重新做 USB 实机烧录、实际拍摄、物理按键/扬声器/灯光或断电冷启动验收。首次 Wi-Fi 连接采用实时身份交叉核对与 SSH 首次使用信任，保存后拒绝密钥/序列号变化；不将其表述为厂商证书认证。
