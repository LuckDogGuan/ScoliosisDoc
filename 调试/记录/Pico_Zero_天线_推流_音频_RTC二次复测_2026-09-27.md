# Pico Zero 二次实测（2026-09-27）

设备：ISG1321、外置 Wi-Fi 天线、Waveshare RTC-Battery-C、喇叭；板卡经 USB ADB 接电脑，2.4 GHz 接 `ChinaNet-7HrK`。没有烧录新固件。患者数据未参与测试。

```text
ISG1321 → 板上 RKIPC → RTSP ┬→ USB ADB 转发 → 电脑：可持续读取
                           └→ 当前路由器 Wi-Fi → 数秒后停帧、网关不通
RTC-Battery-C → 板上 rtc0（尚待完全断电保时确认）
```

## 结果和判断

| 项目 | 本次证据 | 结论 |
| --- | --- | --- |
| 天线 A/B/A | 同位置、同 AP，GPIO123=`1` 板载天线约 −63～−65 dBm；GPIO123=`0` 外置天线约 −51～−52 dBm，差约 12～14 dB。两种模式在无推流时都能 ping 实际网关 `192.168.1.1`。 | 外置天线明显改善接收信号；**没有修复 RTSP 断流**。先前误测了 `192.168.0.1`，该地址不是网关，已纠正。最终恢复默认外置天线路径。GPIO 定义见[官方 Wi-Fi 文档](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/WiFi-BT/)。 |
| USB 预览 | 1280×1080 H.265 原配置下，FFmpeg 经 ADB 转发连续读取 60 秒、3377 帧，正常结束；VLC 地址 `rtsp://127.0.0.1:8554/live/0`。 | 当前可靠的开发预览路径。60 秒通过不等于已经证明无限时长不断流。 |
| Wi-Fi 预览 | 外置天线、1280×1080、配置约 2 Mb/s 时，直接 RTSP 约 4 秒后停帧；网关 ping 同时失败，Wi-Fi 仍显示关联。板载天线也复现。此前普通 TCP `iperf3` 约 4 Mb/s 连续 25 秒、零重传。 | 故障位于无线 RTSP 场景，不能单独归因于天线、信号强度或带宽；下一次用可管理的专用路由器对照。 |
| 画质参数 | `/userdata/rkipc.ini` 已设视频 1280×1080、`max_rate=2048` kb/s、输入/输出/ISP `30 fps`、照片 `jpeg_qfactor=90`。重启后参数保留，编码器日志显示目标 30 fps、约 2 Mb/s，FFprobe 流头报告 30 fps；但逐包时间戳 299 包跨度约 5.17 秒，实际包率仍接近 58 fps。 | 码率调节已生效；**真实输出帧率尚未降到 30 fps**，不能只看配置或流头。JPEG 目前未开启拍照，质量 90 尚未做实拍对照。 |
| 开机流程 | 备份 `/RkLunch.sh` 后，停用原厂开机 `speaker_test.wav` 自检，把不存在的 `camera_test` 换成现有 `rkipc` 自启动，并将配置复制改为“仅配置不存在时”。重启后 `rkipc` 自动运行、USB RTSP 可打开、音量读回 30；用户确认开机不再播放测试音。 | USB 预览和音量不必每次手动初始化。编辑配置前需先停 `rkipc`，否则程序退出时可能覆写修改。 |
| 声音 | `DAC LINEOUT Volume` 的 0/5/10/15/20/25/30 档已逐档播放。用户选择默认 30。电脑系统中文语音生成两句 WAV，板上 `aplay` 播放成功，用户确认清楚。 | 可以定制语音内容、语速和音量；网络连接/断开自动触发尚未接入，以免当前断流造成重复播报。 |
| RTC-Battery-C | [Waveshare 官方资料](https://www.waveshare.com/rtc-battery.htm)标明 C 型为 3 V、180 mAh、不可充电的 CR2032 备用电池；[Pico Zero 官方页](https://www.luckfox.com/Luckfox-Pico-Zero)列有 RTC 电池接口。板上只有 `rockchip-rtc` 的 `/dev/rtc0`，重启保时正常。 | 这不是第二个 RTC 芯片，不会出现 `rtc1`；完全断开 USB 主电源后的保时结果待核对。 |

## 当前用法

```powershell
adb forward tcp:8554 tcp:554
# VLC 用 TCP，打开 rtsp://127.0.0.1:8554/live/0
adb shell "amixer cget name='DAC LINEOUT Volume'"
adb shell "date -u; hwclock -f /dev/rtc0 -r -u"
```

声音文件：电脑端 `wifi_connected.wav`、`wifi_disconnected.wav`；板上 `/userdata/sounds/` 同名文件。板上手动试听：`aplay -q -D plughw:0,0 /userdata/sounds/wifi_connected.wav`。

启动脚本的原始备份在板上 `/userdata/RkLunch.sh.before_audio_change`，电脑端为 `RkLunch.sh.before_audio_change`；当前脚本的电脑端副本为 `RkLunch.sh.final`。完整回滚：`adb shell 'cp /userdata/RkLunch.sh.before_audio_change /RkLunch.sh && chmod 755 /RkLunch.sh && reboot'`。这会恢复原厂开机自检音、配置覆盖和手动启动摄像头的行为。

下一项决定性验证：在**不同的专用 2.4 GHz 路由器**上重复“网关 ping + 25 秒普通 TCP + RTSP”，并比较断流时的 AP 日志；当前路由器尚不能管理。拍照链路须单独验证原生 JPEG 与清晰度，不能用 RTSP 截帧代替。

当天下午的后续见[推流 30 帧定位](./Pico_Zero_推流30帧定位_2026-09-27.md)：配置里的 30 fps 当时并没有真正降帧；编码器改为 60/2 后 USB 约 31 fps，Wi-Fi 断流仍在。
