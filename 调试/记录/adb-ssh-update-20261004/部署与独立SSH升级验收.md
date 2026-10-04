# ADB 安装与独立网络 SSH 更新验收

日期：2026-10-04，Asia/Shanghai。板端 RTC 仍显示 2021，所有过程以电脑 JSONL 中的北京时间为准。

## 后续使用的 Wi-Fi 配置

按用户要求在文档中保存：

| 配置项 | 值 |
| --- | --- |
| 网络名称（SSID／Wi-Fi 账号） | `MinMax-test` |
| Wi-Fi 密码 | `12345678` |
| 加密方式 | WPA2-PSK / CCMP |
| 网关 | `192.168.101.1` |

无需额外 Wi-Fi 用户名。以上密码用于无线联网，SSH 登录使用独立的系统账号与密码。下位机部署默认模板使用同一组 Wi-Fi 配置；升级时保留已有有效网络配置。常用网络资料也已同步到 [Wi-Fi 基础文档](../../基础信息/WiFi.md)。

## 结论与目标设备

**ADB 首次安装、独立路由器 SSH 更新、重启后 Wi-Fi 恢复、应用自启动、默认音量 20 均已实机验证。**

| 对象 | 序列号 | 当前应用身份 | 本次地址 | 操作范围 |
| --- | --- | --- | --- | --- |
| 用户确认的实验目标 | 41eda5f2c5b00de1 | CAM-41eda5f2c5b00de1 | 192.168.101.4 | ADB 安装、Wi-Fi 初始化、SSH 更新与重启 |
| 路由器另一台设备 | 3253c006806f5194 | 未在本次改写或初始化 | 192.168.101.3 | 仅只读序列号核对，更新器拒绝，未传包或写入 |

目标由用户明确确认。DHCP 地址可能变化，**不能只按 IP 升级**。独立更新器在写入之前检查主机密钥、设备序列号和 config 中的 device_id，任一不符即停止。已用另一台 .3 实测拒绝，Python 优化模式下身份检查也仍有效。

`ssh_network_update.py` 是本次目标专用验证入口。后续换板必须重新审核并明确修改身份锁；不得直接去掉校验。它还查询匹配 nonce 的现场 UDP 状态，只有未配对、idle、无拍摄许可、无当前录像和上传的实验设备才能继续。

## 实际执行

1. ADB 使用显式 `-s 41eda5f2c5b00de1` 核对 Pico Zero / ARMv7 / Buildroot，以及空应用目录，保存前记录。
2. 通过 ADB 推送旧 3.3.0 bundle1；外层哈希、包内清单、安装器、目标文件校验均通过。设备唯一 ID 根据序列号生成，没有复制另一台 CAM-000123。
3. ADB 重启后通过 SSH 核对 3.3.0、程序哈希和应用 PID。早期 SSH 使用 ADB USB 转发，这一步仅作准备，不作为独立更新结论。
4. 按用户要求，将 WSL 下位机默认配置改为 MinMax-test、默认音量 20、电脑服务地址 192.168.101.2:8080；在 `deploy/wpa_supplicant.default.conf` 保存用户指定的实验网络配置，编入单文件部署包。记录和操作日志不打印网络口令。
5. 指定目标通过 ADB 完成首次联网准备，取得 DHCP 地址 192.168.101.4。随后停止电脑 ADB 服务，直接连接该地址 TCP 22，通过 SSH stdin 传一个部署包，校验、平稳停止服务、安装并重启。更新程序没有任何 ADB 调用。
6. 第一个网络修订包安装通过，但重启后网络恢复成 Your SSID；保存失败证据，检查启动配置。随后修正安装器对出厂 `/etc/wpa_supplicant.conf` 的初始化，产生不可覆盖的新 bundle2，重新独立 SSH 安装、重启和验收。
7. 最终 16:35:43，独立 SSH 返回 `LAN_SSH_REBOOT_VERIFY_PASS`，版本 3.3.0、程序 SHA256 一致、应用 PID 174、配置与 ALSA `DAC LINEOUT Volume` 均为 20，电脑无 ADB 进程。随后网络保持 available，`gateway=1 wifi=1 failures=0`。
8. 播放 `volume_test.wav` 返回 AUDIO_EXIT=0，音量读回仍为 20。实际可听音量由现场确认。

## 最终部署包

**以后使用本目录的 `instrument-v3.3.0-20261004-minmax-volume20-bundle2.tar.gz`。** 旧包和中间修订只保留作追溯，不能拿首次失败的 bundle1 作为重启联网已验收版本。

```text
bundle SHA256: b4cf975d1c3a4076f42ae366c578d4f14727e7ea82d20ee3fda8b22740e94b71
instrument_app SHA256: 6555ebcaaae1043acc418509e403387445c012be0abad855456d3027174b1df7
```

应用二进制仍为 3.3.0，本次修改是默认配置与部署包修订，没有冒充新的业务程序版本。音量默认写在 WSL `config.example.json`；已有设备配置升级时保持原样，本目标已显式设为 20。

WSL 源码与原始包：`Luckfox-Ubuntu-22.04:/home/guanjx/luckfox/Scoliosis`，最终归档在 `image/v3.3.0-20261004-minmax-volume20/` 与 `bundles/v3.3.0-20261004-minmax-volume20-bundle2/`。随后按用户要求提交到 Git：`19bba16`，版本标签 `instrument-v3.3.0-20261004-minmax-volume20`；未推送远端，其他未完成工作保留。见 [Git 更新与待办核对记录](Git更新与待办核对记录.md)。

## 修复与默认网络策略

- 这块板的 tar 不支持 `-z` / 自动 gzip 解压，必须先 `gzip -dc 包.tar.gz > payload.tar`，再 `tar -xf payload.tar`；没有改系统工具或安装新依赖。
- 该系统启动会从 `/etc/wpa_supplicant.conf` 恢复运行网络。仅写 `/userdata` 不能保证重启恢复；最终 `/etc` 与 `/userdata` 的 SHA256 相同，重启联网成功。
- 安装器在网络配置不存在或仅有一个出厂 Your SSID 条目时才初始化默认网络。已有真实网络保留；出厂 `/etc` 配置优先从真实 `/userdata` 配置复制，避免覆盖现场网络。改写前均进入安装映射与回滚 tar。
- `/opt/instrument/defaults/wpa_supplicant.conf` 保留部署模板；Wi-Fi 配置权限为 600。
- 新板仍需初始化独立设备 ID 和 config.json，不能把示例 CAM-000123 复制给多块设备。示例的音量 20 和默认网络已经落实到源码与最终包。

## 证据与回退

- `adb-install-20261004-162128.jsonl`：第一次 ADB 实板成功安装。
- `ssh-update-20261004-162213.jsonl`：早期 USB 转发 SSH 重装记录。
- `lan-ssh-20261004-163130.jsonl`：首个网络修订的独立 SSH 安装成功，随后重启联网失败，不能单独当最终验收。
- `lan-ssh-20261004-163453.jsonl`：最终 bundle2 独立网络 SSH 安装与配置保留校验。
- `lan-ssh-20261004-163542.jsonl`：重启后版本、哈希、PID、音量验收。
- `10-adb-independent-final.txt`：最终更新和重启验收时电脑 ADB 进程不存在。
- `11-wrong-device-refused.txt`、`14-wrong-device-final-guard.txt`：另一台设备的身份拒绝证据。
- `12-final-runtime.txt`：重启后网络、声音播放退出码、音量以及相机进程边界。
- `13-live-hello.json`：目标设备实时状态，idle、gate=false、无配对和拍摄/上传，volume=20、wifi=available。
- `board-backups-final.tar`：独立 SSH 导出的板端安装备份，包含首次安装、两次网络修订的记录和文件回退材料。早期 ADB pull 因 Windows 中文路径失败，此 tar 是完整补取版本。

最终板端安装记录：`/opt/instrument/backups/bundle-20210105T122231Z-1528/`，result.txt 为 exit_code=0，install.log 包含 INSTALL_OK，after-SHA256SUMS 全部 OK。回退按原教程逐项恢复代码与启动文件；保留当前配置、配对、视频和学生关联，不批量删除。

## 验证入口

PowerShell，在项目根目录交互输入 SSH 密码（默认口令见官方文档；不要写入日志）：

```powershell
# 密码通过标准输入提供，脚本无 ADB 依赖。
Read-Host -MaskInput 'SSH密码' | python 调试/记录/adb-ssh-update-20261004/ssh_network_update.py --address 192.168.101.4 --verify-only
```

去掉 `--verify-only` 会执行实际更新、停止服务与重启，必须先停止上位机业务，并核对身份。IP 变化时先重新发现，不能直接换成另一台的地址。

## 验证范围

ARM/uClibc 编译、配置校验、shell 语法、包内完整清单、安全归档、损坏音频拒绝、安装 idle 确认门禁、本次 ADB / 独立 SSH 实板部署和重启均通过。

GitNexus 对默认配置文件的影响为 LOW、0 个直接调用和流程；新安装/打包脚本不在旧固件索引中，风险返回 UNKNOWN，已按真实源文件与包测试核对，不能把旧索引当这些脚本的验证证据。

相机内核报告 remote terminal sensor failed，RKiPC 当前未运行，因此本轮**不代表录像、预览和上传的全功能验收**。没有为这个独立 SSH 更新实验重刷系统或修改另一个设备。
