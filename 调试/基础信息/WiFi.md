# Wi-Fi

密码和 PSK 不写在这里。改路由器或地址时只改本文件。

WIFI:T:WPA;S:ChinaNet-7HrK;P:fMmp4wRw;H:false;;

| 项 | 值 |
| --- | --- |
| 角色 | 开发测试热点。专用路由器未购买，账号密码先用这一套。仪器开机自动连接，电脑软件不输入、不显示密码 |
| SSID | `ChinaNet-7HrK` |
| 频段 | 2.4 GHz，实测频率 2462 |
| BSSID | `80:3c:20:5a:4e:38` |
| 板卡地址 | `192.168.0.66/23` |
| 网关 | `192.168.1.1` |
| 电脑 WLAN | `192.168.0.20` |
| 天线 | GPIO123 = `0`，外置天线（官方默认外置档） |
| 板端配置 | `/etc/wpa_supplicant.conf` 与 `/userdata/wpa_supplicant.conf`，权限 `600` |
| 省电 | 本次调试已执行 `iw dev wlan0 set power_save off`；重启后要再读一次，不保证保留 |
| 局域网预览 | `rtsp://192.168.0.66:554/live/0`，RTSP over TCP |

关联还在、但 ping 网关全丢时，先重新关联，等路由恢复再拉流：

```sh
wpa_cli -i wlan0 reassociate
# 若立刻出现 Network is unreachable，等几秒再查 ip route，不要马上再执行一次
ping -c 3 -W 1 192.168.1.1
```

当前这台路由器不能管理。稳定预览档以 [推流参数](推流参数.md) 为准，现在是 10 fps、640 kb/s（`60/6`）、省电关闭。384 kb/s 及以上的 30 fps 档会在大约 1 分钟或数秒后让网关 ping 失败。
