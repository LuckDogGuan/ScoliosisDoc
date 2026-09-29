# Luckfox Pico Zero 开源库核对

> **【部分过时】** 2026-09-27 的库清单仍可用来查板上有什么。这几条已被后来的程序替换，细节和原因在 [架构说明](说明.md)：视频待传在 `/opt/instrument/capture/pending`，不再只放 `/userdata`；MP4 由 C 程序以 `video/mp4` 上传，不用 `wget --post-file` 传整文件；JSON 用了 cJSON；音量由 hello 下发。

> 核对日期：2026-09-27  
> 板子：Luckfox Pico Zero，出厂 Buildroot，ADB `3253c006806f5194`  
> 预算：内存 **256MB**，存储 **8GB**。库尽量用板上已经有的，少装新的。  
> 交互以 [软件框架](Pico_Zero_拍摄仪器软件框架设计.md) 为准。本文只定「用哪个程序、哪个库」。

按键、中键灯、主电池、专用路由器都还没买，对应的库先不引入。现在能调的是：预览、喇叭、把文件传到电脑、名单挂视频。

更早一版架构稿里写过 `libcurl`、`libmicrohttpd`、`nlohmann/json`、`spdlog`、Flutter。本仓库 git 只有一次提交，那份名单没有单独留在历史提交里。下面按那一版，对照今天这块板上实际有的文件改过。

---

## 1. 256MB 和 8GB 怎么守

两头分开看。

| 资源 | 今天板上看到的 | 软件上怎么守 |
| --- | --- | --- |
| 内存 256MB | `free` 的 MemTotal 是 185280 kB。rkipc 当时没在跑，available 大约 154MB | 编码只留 **一个** `rkipc`。自己的程序不解码、不再开一路 H.265。`ffmpeg` 和 `rkipc` 不要同时干活 |
| 存储 8GB | 根分区约 5.8GB，已用约 189MB，还空约 5.4GB。`/oem` 约 488MB，已用约 19MB。`/userdata` 约 238MB，还空约 228MB | 程序和已有库放系统分区。视频只放 `/userdata`。一段 10 秒、4000 kb/s 的片子大约 5MB |

拍完、电脑明确收下之后再删本地文件。剩余不足 16MB 就拒绝开录。未收下的不自动删。这些规则仍以软件框架为准。

日志不要写进 `/userdata`。短日志走 syslog，需要落盘时放 `/tmp` 或根分区上的小文件，并限制大小。

---

## 2. 这次定下来的库

下位机只用 C。交叉编译用 [编译环境](../基础信息/编译环境.md) 里的 `arm-rockchip830-linux-uclibcgnueabihf-gcc`。出厂系统里有 `libstdc++.so.6` 和 Python 3.11，新程序不靠它们。已有命令（`rkipc`、`wget`、`aplay`）直接调用。

| 事情 | 用什么 | 在哪 | 今天的状态 |
| --- | --- | --- | --- |
| 预览、ISP、H.265 | 板上的 `rkipc` | `/oem/usr/bin/rkipc` | 已在用。内部链着 `/oem/usr/lib/librockit.so`、`librkaiq.so` |
| 录像封装 | `librkmuxer.so` | `/oem/usr/lib/librkmuxer.so` | 库在。`rkipc.ini` 的 `[storage]` 还没按我们的流程开过 |
| 上传 | BusyBox `wget` | `/usr/bin/wget` → BusyBox 1.36.1 | 命令在。支持 `--post-file` 和 `--header`。还没拿视频试过 |
| 喇叭 | `aplay`，库是 `libasound` | `/usr/bin/aplay` | 已试听；当前临时音量 10，后续可调整 |
| Wi-Fi | `wpa_supplicant`、`wpa_cli`、`udhcpc` | 系统里 | 测试热点已关联过 |
| 旁边的小 JSON | `libcjson.so.1.7.15` | `/usr/lib/libcjson.so.1` | 库在。第一版可以先不调用 |
| 看文件好不好 | 板上 `ffprobe` 4.4.4 | `/usr/bin/ffprobe` | 只查询。不拿它编码 |
| 摆放预览 | 电脑上已有的 VLC | Windows | RTSP over TCP。正式 10 秒不走这里 |
| 电脑播放成片 | Flutter `video_player` | `D:\code\Scoliosis\ScoliosisFlutter` | Windows 安装 HEVC 视频扩展后，系统直接解 H.265 |
| 电脑收文件、读名单 | Dart 自带的 `HttpServer`，外加 `excel`、`csv` | 同上 | 不用 Python |
| 日志 | `syslog` | uClibc 里 | 直接用 |

`rkipc` 启动时要带上 `/oem/usr/lib`，否则 `librockit.so` 找不到。现有启动方式不用改，见 [设备](../基础信息/设备.md)。

---

## 3. 历史名单里这次拿掉的

| 旧稿 | 这次 | 原因 |
| --- | --- | --- |
| 自己的程序再链 RK MPI / `librockit` | 不链。继续调用已经在跑的 `rkipc` | 本仓库没有这套头文件，完整 SDK 也还没下。再开一个编码进程会和 `rkipc` 抢 ISP，也抢 256MB |
| `libcurl` | 用 BusyBox `wget --post-file` | 板上没有 `curl`，也没有 `libcurl`。`wget` 已经能 POST 文件、加 HTTP 头。局域网用 HTTP，和软件框架一致 |
| `libmicrohttpd`（板上再开 HTTP 服务） | 板上不听端口。电脑收 `POST` | 现在的动作是仪器往电脑送。发现、断线重试以后再做。少一个常驻服务，内存更稳 |
| `nlohmann/json` | 需要解析时用板上的 cJSON 1.7.15 | cJSON 已经在 `/usr/lib`。旁路文件只有 capture_id 和时间，甚至可以先用固定格式文本写出来 |
| `spdlog` | `syslog` | 旧稿自己也写了依赖要少时退回 syslog。现在就退回 |
| `cpp-httplib` | 不用 | 旧稿已排除。32 位 uClibc 上没必要再试 |
| 自己再装 x265、或为了播放改成 H.264 | 不用 | 成片就是 H.265。Windows 装 HEVC 视频扩展来播，不在仪器上转码 |
| 电脑端用 Python | 不用 | 电脑是 Flutter Windows |
| OpenCV、Qt、SQLite、MQTT、WebSocket | 不用 | 名单在电脑。仪器不跑数据库。实时消息协议软件框架已经排除 |

板上的 `ffmpeg` 列得出 `hevc_v4l2m2m` 这个编码器名字。这次没有拿它出过片。正式编码仍只走 `rkipc`。不要一边推流一边用这个编码器再压一路。

板上有 Python 3.11.6。拍摄、上传、电脑端都不用它。上传和喇叭用 `wget`、`aplay`，用完就退出。

`/oem/usr/lib/librockiva.so` 是分析库，`rkipc` 带了这个依赖。我们的功能不调用它，也不为它加模型。

---

## 4. 每个功能具体怎么用

### 4.1 预览（摆放、焦距）

继续用现在的 `rkipc` 和 [推流参数](../基础信息/推流参数.md)。电脑用 VLC 打开 RTSP，走 TCP。不从中键启动，软件框架里已经这么定了。

不新加播放库，不在板上解码这一路。

### 4.2 正式录像

编码参数以软件框架为准：1280×1080，30 fps（`60/2`），H.265，MP4，4000 kb/s，固定 10 秒。这路不走推流那一档的 10 fps / 640 kb/s。

封装用板上已有的 `librkmuxer.so`，由 `rkipc` 写出 MP4。Windows 侧装 HEVC 视频扩展来播，不另包解码器，也不改成 H.264。

`[storage] enable` 先保持 0。`free_size_del_min = 500` 的单位没核对，打开可能在只有约 228MB 的 `/userdata` 上删文件。10 秒这一段由我们的程序起停，不用它按分钟循环录。

### 4.3 上传

仪器 `POST` 到电脑，路径和头以软件框架第 8 节为准。板上用 BusyBox `wget --post-file`，不用再交叉编译 libcurl。

```sh
wget -q -S -O /tmp/upload-body.txt \
  --header "Device-ID: CAM-000123" \
  --header "Capture-ID: CAM-000123-a1b2c3d4" \
  --header "Codec: h265" \
  --header "Container: mp4" \
  --post-file /userdata/capture/pending/这一段.mp4 \
  http://192.168.0.20:8080/api/v1/capture/file
```

电脑地址用 [Wi-Fi](../基础信息/WiFi.md) 里的 `192.168.0.20`。密码不写在这里。成功看 HTTP 200。没传上的文件留在 `/userdata/capture/pending/`。

### 4.4 喇叭

继续：

```sh
aplay -q -D plughw:0,0 /userdata/sounds/某个文件.wav
```

声卡 `rv1106-acodec`，音量键 `DAC LINEOUT Volume`，当前暂设 10。不新链一套音频库。句子文案以软件框架第 5 节为准。8 条 WAV 已放到板上并逐一校验哈希；业务触发时机仍待联调。录像过程中不播。

### 4.5 Wi-Fi

继续 `wpa_supplicant` + `udhcpc`。测试热点是 `ChinaNet-7HrK`。密码只在 Wi-Fi 那一页和板端 `wpa_supplicant.conf`。

仪器不开自己的热点。专用路由器没到之前，不改这套，也不加新的配网库。

### 4.6 名单和视频怎么挂

仪器不存学生，不跑数据库。文件头和旁边的说明里只有 capture_id、时间、分辨率、时长。学生姓名不进仪器。

说明若写成 JSON，用板上的 cJSON 写那几个字段。字段就这几个时，用固定格式写一个文本也行，少一次库调用。电脑按 capture_id 挂到「这次筛查 + 当前学生」。目录结构仍是软件框架第 4 节。

### 4.7 日志

用 `syslog`。类别沿用软件框架里已经有的划分即可：拍摄、上传、存储、网络。电池未安装时，开机打一条就够。

不要为日志再放一个常驻进程。单文件超过几 MB 就停，避免和视频抢 `/userdata`。业务日志默认不放 `/userdata`。

---

## 5. 先放着、不选库

| 硬件 | 软件现在怎么处理 | 库 |
| --- | --- | --- |
| 左、中、右和中键灯 | 还没定买哪一种。板载 BOOT、RESET、`work` 灯都不做产品按键和模式灯 | 不引入 `gpio-keys`、`libevdev`。GPIO 号不写 |
| 总开关 | 串在电源上。软件看不到 | 无 |
| 主电池 | 未买。接口固定「未安装」。不读 ADC，不扫 I2C | 无电量计库 |
| RTC 纽扣电池 | 只维持时钟 | 不拿来做电量 |
| 专用路由器 | 未买。开发用测试热点 | 不换 Wi-Fi 栈 |
| 配对灯、断线重连 | 软件框架写明以后再做 | 不为此在板上加 HTTP 服务或广播库 |

按键到货之后，优先用内核输入事件，仍不把灯的电流直接灌进 GPIO。那是下一轮的事。

---

## 6. 电脑上用什么

老师那台电脑不吃 256MB 这个限制。工程是 Flutter Windows，不用 Python。

| 事情 | 库 | 说明 |
| --- | --- | --- |
| 看摆放和焦距 | 已安装的 VLC | `rtsp://192.168.0.66:554/live/0`，RTSP over TCP。正式 10 秒开始前关掉 |
| 播上传的 H.265 | `video_player` | 先给 Windows 安装 HEVC 视频扩展，用系统解码。不在仪器或电脑上转码 |
| 收 POST、写筛查目录 | Dart `HttpServer` | 端口 8080。接口见软件框架第 8 节 |
| 导入 xlsx / csv | `excel`、`csv` | 列名：学校、年级、班级、学号、姓名 |
| 记录 | `记录.csv` | 不另装数据库 |

Django、PostgreSQL、pandas 不上。第一版不上传公网。

---

## 7. 按键还没到，编码时按这个顺序

1. Flutter 打开。每台仪器开机自动连 Wi-Fi，再 `POST /api/v1/hello` 带上基础信息。老师在列表里对一台或多台点「配对」。
2. 导入 [名单模板.csv](名单模板.csv) 那种表，屏幕只突出当前一位。
3. 点「拍摄」。仪器停掉 RTSP，录 10 秒 MP4，再 `wget` 上传。
4. 收下后 Flutter 用 `video_player` 打开，并跳到下一位。喇叭播 `调试/声音/` 里对应的那句。

JPEG 周期抓拍只是旧证据。产品文件是这 10 秒的 MP4。

---

## 8. 已经定下来的容器

成品是 **MP4 里的 H.265**。裸 `.h265` 不采用。`[storage] enable` 仍然先保持 0，避免它按空闲空间删文件。

---

## 词汇

| 词 | 意思 |
| --- | --- |
| 仪器 | 这块 Pico Zero。只负责拍和传 |
| 电脑 | 老师旁边那台 Windows。名单、当前学生、收文件、看预览都在这里 |
| rkipc | 出厂固件里的摄像进程。ISP、H.265、RTSP、JPEG、MP4 都从这里走 |
| capture_id | 按下那一刻生成的编号。视频用它挂到学生，仪器里不写姓名 |
| 可见内存 | 这次 `free` 报的大约 181MB。整机预算仍按 256MB 守，编码只留 rkipc 一个 |
| userdata | 8GB 里专门放视频的那一段，大约还能用 228MB |
