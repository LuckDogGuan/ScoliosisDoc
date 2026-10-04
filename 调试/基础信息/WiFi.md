# Wi-Fi

2026-09-30 新默认：华为专用路由器 `MinMax-test`。2026-10-04 按用户要求补充网络密码，供后续联网与 SSH 升级使用。

| 项 | 值 |
| --- | --- |
| SSID | `MinMax-test` |
| Wi-Fi 密码 | `12345678` |
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

Wi-Fi 的“账号”就是上面的网络名称（SSID），无需额外用户名。此密码用于无线联网，SSH 登录使用独立的系统账号与密码。

2026-10-04 的升级实验目标为序列号 `41eda5f2c5b00de1`，DHCP 地址 `192.168.101.4`；另一台序列号 `3253c006806f5194` 的地址为 `192.168.101.3`。升级前必须核对序列号和设备 ID，不能仅凭地址选择设备。详细过程见 [独立 SSH 升级验收](../记录/adb-ssh-update-20261004/部署与独立SSH升级验收.md)。上表中的频段、信号和旧测试结果属于 2026-09-30 记录。

双向 ping、25 轮设备发现、8 MiB Wi-Fi 二进制往返、三轮原生录像上传已通过。重启默认接入结果及详细边界见 [本次记录](../记录/华为路由器与三键测试_2026-09-30.md)。

录像找不到文件时核对 RKIPC `storage.mount_path=/`，与应用的 `/video0` 一致；旧 `/userdata/video0` 录像保留。默认路由器不意味着更改现有预览帧率和码率。
