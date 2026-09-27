# Pico Zero 复测：外置天线、RTC、喇叭音量（2026-09-27）

前次基础测试见[实板入门记录](./Pico_Zero_实板入门与三项测试_2026-09-27.md)。本次仍用 ISG1321、USB ADB 和同一路由器；没有烧录固件。

```text
外置天线 → 2.4 GHz Wi‑Fi → 普通 TCP 稳定 → RTSP 触发失联
电脑 UTC → 板内 rtc0 → 重启保时 → 关闭 RKIPC 错误的 NTP 校时
ALSA DAC LINEOUT Volume → 可调音量 → 待用户听感确认
```

| 项目 | 实测结论 |
| --- | --- |
| 外置天线 | GPIO123 切到 `0`（官方默认外置档位），目标 Wi‑Fi 信号约 −55～−57 dBm；重启后自动接入 `ChinaNet-7HrK`，板卡获 `192.168.0.66`。 |
| Wi‑Fi 配置 | 原配置重启后会回到占位 SSID。已将有效配置写入 `/etc/wpa_supplicant.conf` 和 `/userdata/wpa_supplicant.conf`，权限 `600`；再次重启后自动接入。密码及 PSK 不写入本记录。 |
| 普通无线传输 | WSL Ubuntu 安装开源 `iperf3`。约 1 Mb/s 持续 25 秒、3.12 MB：相机程序未启动时 0 次重传，启动后 1 次重传；相机运行时约 4 Mb/s 持续 25 秒、12.4 MB、0 次重传。网关 ping 全程通。 |
| Wi‑Fi RTSP | 仅一个客户端、两个客户端、TCP、UDP、经 `socat` 改到 8555 端口，以及前次 15 fps/约 1 Mb/s 配置，均在约 5～8 秒出现板卡到网关通信失败；无线仍显示已关联。故障尚不能归因于板卡驱动或路由器某一方。USB RTSP 正常。 |
| 内置 RTC | 系统只有 `/dev/rtc0`，名称为 `rockchip-rtc ff1c0000.rtc`。从电脑设置 UTC 并写入 `rtc0` 后，重启保时成功。断电保时尚待用户回来实测。 |
| 外接 RTC | 当前无 `rtc1`；唯一暴露的 I²C 总线为 `i2c-4`，对常见地址 `0x68` 的只读探测未发现设备。这不能证明外接件故障，仍需模块型号和接线确认；若接的是内置 RTC 备用电源，也不会出现 `rtc1`。 |
| 时间偏移 | 原厂 `rkipc` 每 60 秒 NTP 校时会把系统 UTC 拨快约 8 小时。已备份 `/oem/usr/share/rkipc-mia1321-100w.ini` 到 `/userdata/rkipc-mia1321-100w.factory-ntp.ini`，并将 OEM 原厂配置和当前配置的 `[network.ntp] enable` 改为 `0`。重启及运行超过 60 秒后，系统 UTC、`rtc0`、电脑 UTC 相差约 1 秒。画面水印目前显示 UTC，医生记录应以电脑接收时间为准；最终原图建议关闭水印。 |
| 喇叭音量 | `DAC LINEOUT Volume` 范围 0–30，原值 26；临时设为 18 并读回成功，随后恢复 26。调节能力已验证；18 和 26 的听感需要用户回来确认。 |

## 复核命令

```powershell
adb -s 3253c006806f5194 shell "cat /sys/class/rtc/rtc0/name; date -u; hwclock -f /dev/rtc0 -r -u"
adb -s 3253c006806f5194 shell "wpa_cli -i wlan0 status | grep -E 'wpa_state|ip_address|ssid='; iw dev wlan0 link"
adb -s 3253c006806f5194 shell "amixer cget name='DAC LINEOUT Volume'"
# 示例：调到较低档位；当前仍为 26
adb -s 3253c006806f5194 shell "amixer cset name='DAC LINEOUT Volume' 18"
```

当前可用的电脑预览地址：`rtsp://127.0.0.1:8554/live/0`（ADB 转发 8554→554，VLC 使用 TCP、500 ms 缓存）。板上 `rkipc` 正在运行；重启后仍须手动启动。WSL 已有 `iperf3`，临时板端 `iperf3` 和 `socat` 服务已停止。

## 回来后优先做

1. 发外接 RTC 模块型号和接线/照片；断开板卡主电源一小段时间再上电，核对 `hwclock` 是否继续走时，以验证备用供电。
2. 听 18 与 26 两档的实际喇叭响度，确定提示音默认值；当前没有改永久默认值。
3. 用可管理的专用 2.4 GHz 路由器（WPA2‑PSK/AES、近距离）重复“网关 ping + 25 秒普通传输 + RTSP 预览”。若新路由器仍复现，再针对 AIC8800DC 驱动、固件和 RKIPC 排查。

官方参考：[Pico Zero Wi‑Fi/天线](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/WiFi-BT/) · [Luckfox 音频音量示例](https://wiki.luckfox.com/zh/Luckfox-Pico-Ultra/Audio/)
