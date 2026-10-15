# 下位机一键烧录

1.2.0（2026-10-15）：新增 Wi-Fi 模式、设备发现/身份绑定及独立 CLI EXE；USB 安装流程继续共用。

## Wi-Fi 使用

双击 `release/下位机一键烧录.exe` → 选择 **Wi-Fi 烧录** → **配对连接** → 选择压缩包 → **开始烧录**。电脑与仪器须在同一局域网。首次发现新仪器时打开仪器的物理配对模式；已在工具中连接过，或当前上位机工作空间中已配对的仪器，可以直接发现，无需反复打开配对窗口。多台设备弹窗选择，不能随意选第一台。

“配对连接”保存的是本工具的烧录连接身份，不创建拍摄许可、不接管或改写业务配对。安装仍会拒绝尚未关闭的物理配对窗口、提示音、拍摄、上传或诊断；等待窗口/声音结束后再开始。只连接不要求仪器空闲。

Wi-Fi 使用仪器现有 SSH 服务，默认使用[官方原厂 Buildroot 登录](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/Login/)；修改过设备密码时在界面输入，CLI 使用 `--password-stdin`。密码仅驻留内存，不写连接文件或操作记录。首次连接以实时 UDP 设备身份与 SSH 读取的设备 ID、序列号及 wlan0 地址交叉核对，并保存首次主机密钥；此为首次使用信任，不是厂商证书认证。之后密钥或序列号变化立即停止，不自动更新信任。`wifi-devices.json` 只保留设备 ID、序列号、地址和主机密钥指纹；两种 EXE 在同一 release 目录中共享此文件。

## 命令行

无需 Python：使用 `release/下位机烧录CLI.exe`；GUI EXE 用于窗口操作。源码也支持相同参数：`python flash_tool.py`。

在此工具目录的 PowerShell 中：

```powershell
$cli = Join-Path $PWD 'release/下位机烧录CLI.exe'
$package = '\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\releases\3.3.11\instrument-v3.3.11.tar.gz'

# 发现设备，输出 JSON；不安装、不改配对
& $cli --wifi --discover

# 当前仪器：保存连接身份，不安装
& $cli --wifi --connect --device-id CAM-211ec7045815bf02 --address 192.168.101.7

# 只核对包、设备身份和空闲门禁
& $cli --wifi --check --device-id CAM-211ec7045815bf02 --package $package

# 实际安装；同版本且文件正确时只校验，不重复写入
& $cli --wifi --install --device-id CAM-211ec7045815bf02 --package $package
if ($LASTEXITCODE -ne 0) { throw '烧录未完成，请查看 REPORT 记录目录' }
```

省略 `--address` 自动重新发现当前地址；指定地址必须同时给出 `--device-id`，不按 IP 单独决定目标。省略 ID 时仅允许发现唯一仪器。可加 `--serial` 进一步核对序列号。`--force` 仅在确需同版本重新安装时与 `--install` 一起使用。`--check`、`--install`、`--connect`、`--discover` 互斥；未提供包时 CLI 沿用自动选择最新正式包的旧行为，指定版本更新请明确 `--package`。

地址 `192.168.101.7` 为本次实测值，DHCP 改变后重新发现。返回 0 表示操作成功，运行失败返回 1，参数错误返回 2。安装、检查与连接输出 `REPORT=...`，Wi-Fi 日志包含 `transport=wifi-ssh`，不会调用 ADB。Wi-Fi 中断或重启后连接未恢复会停止并保留安装/回退记录，不自动重复安装；恢复网络后先执行 `--check`。

开发验证：`python -m unittest test_flash_tool test_wifi_flash -v`。`build.ps1` 同时生成 GUI 与 CLI，运行电脑无需 Python/Paramiko，构建环境需已安装 PyInstaller、Paramiko。

## USB 使用

双击 `release/下位机一键烧录.exe` → **选择压缩包** → 查看包内版本 → 插好 USB → **开始烧录**。

选中 `instrument-v*.tar.gz` 后读取包内 VERSION 并显示，不用文件名推断版本。文件对话框默认打开本机 WSL 正式发布目录；也可以选其他位置的完整应用烧录包。版本与包内文件校验通过后才能开始；一台设备自动选中，多台弹窗选择。按所选包完成空闲检查、备份、安装、重启和文件校验。已有相同版本且文件校验通过时直接完成，不重复写入。

压缩包旁存在 SHA256SUMS 时，同时核对所选包的外层校验；单独的压缩包使用包内逐文件校验。校验用于检出损坏，不提供发布者签名认证；请使用本项目正式发布包。旧历史归档缺少应用安装器时不能直接烧录。

本工具安装应用包；系统仍沿用原厂 Buildroot。支持 Luckfox Pico Zero 首次安装和已有应用更新。新板按正式包示例配置初始化，仪器 ID 自动为 `CAM-<序列号>`；已有配置保留。EXE 内含 ADB 与状态检测组件，无需安装 Python；Windows USB 驱动及本机 `Luckfox-Ubuntu-22.04` WSL 正式包目录仍是前提。正式包不复制到 Windows 发布目录。

成功与失败日志、回退审计保存在 EXE 旁 `记录/<时间-序列号>/`，板端保存在 `/opt/instrument/backups/bundle-*`。记录可能包含现场网络配置，只留本地，不提交 Git。记录错误时保留原始失败出口；不会通过重复安装掩盖失败。

源码：`flash_tool.py`；构建：`./build.ps1`。状态查询组件直接复用仪器测试工具 `payload/udp_query`，SHA256 固定；源文件唯一位于 WSL `tools/uvc-v1.0.0/udp_query.c`，不另写板端逻辑。

1.1.1（2026-10-13）修复3.3.9兼容：传输校验保留压缩包整体SHA256；设备文件校验与包内安装器一致，语音只安装和核对WAV，不把语音JSON清单误当已安装文件。重启后允许启动提示音在15秒内结束；安装前仍严格拒绝音频忙碌，拍摄/上传/诊断等门禁没有放宽。

调试命令：`python flash_tool.py --check --package <压缩包路径>`（仅核对，上传临时检测组件，不停止服务或安装）；`--install --package <压缩包路径>`（实际安装）；`--install --force`（实板验证，同版本也安装）。多台时用 `--serial <序列号>` 明确指定，GUI由选择弹窗处理。命令行未提供 --package 时仍自动选择最新版本；GUI必须选包。

未知定制启动脚本、业务忙碌、文件校验失败或设备身份不匹配都会停止。已核对历史启动脚本允许更新到正式包；配置、配对、现有视频保留，相机仅允许正式版诊断 JPEG 设置差异。

检测不到摄像头时仍可完成板端应用安装，但结果明确提示“未检测到摄像头”；不宣称相机服务或实际帧验收通过。首次安装生成的配置在记录中标记为新建，回退归档与已有设备更新的含义不同。
