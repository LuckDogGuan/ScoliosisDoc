# Wi-Fi

2026-09-30 新默认：华为专用路由器 `MinMax-test`。密码只保存在板端 Wi-Fi 配置，不写进记录和界面。

| 项 | 值 |
| --- | --- |
| SSID | `MinMax-test` |
| 路由器管理地址／网关 | `192.168.101.1` |
| 频段 | 2.4 GHz，2437 MHz，信道 6 |
| BSSID | `c2:f3:70:e1:f0:75` |
| 板卡地址 | DHCP 实测 `192.168.101.3/24`，不要当作永久静态地址 |
| 电脑 | 网线 `192.168.101.2/24`；本次无需切换电脑原 Wi-Fi |
| 实测信号 | 约 -22 dBm，路由器就在仪器旁 |
| 加密 | WPA2-PSK / CCMP |
| 默认网络 | 新网络 priority=100；旧网络保留但 disabled=1 |
| 板端配置 | 运行 `/data/wpa_supplicant.conf`，`/data` 实为 `/userdata`；同步 `/etc/wpa_supplicant.conf`，权限 600 |
| 旧配置备份 | `/userdata/wpa_supplicant.conf.before-minmax-20260930`、`/etc/wpa_supplicant.conf.before-minmax-20260930` |
| 应用配置备份 | `/opt/instrument/config.json.before-minmax-20260930` |
| 预览 | `rtsp://192.168.101.3:554/live/0`，RTSP over TCP |

双向 ping、25 轮设备发现、8 MiB Wi-Fi 二进制往返、三轮原生录像上传已通过。重启默认接入结果及详细边界见 [本次记录](../记录/华为路由器与三键测试_2026-09-30.md)。

录像找不到文件时核对 RKIPC `storage.mount_path=/`，与应用的 `/video0` 一致；旧 `/userdata/video0` 录像保留。默认路由器不意味着更改现有预览帧率和码率。
