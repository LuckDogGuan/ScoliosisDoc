# Luckfox Pico Zero 拍摄仪器软件框架设计

> 目标平台：Luckfox Pico Zero（RV1106G3）  
> 目标功能：1080P / 30fps / H.265 / 每轮约 5 秒拍摄 / Wi‑Fi 上传到电脑端  
> 操作方式：3 个实体按键 + 专用 AP/路由器 + 电脑有线接入同一局域网  
> 设计原则：**稳定优先、尽量复用成熟开源组件、方便调试、避免误操作、后续方便硬件重画板。**

---

## 1. 为什么选择这套软件结构

Pico Zero 本身已经具备本项目需要的核心硬件：RV1106G3、256MB DDR3L、8GB eMMC、4-lane MIPI CSI、板载 2.4GHz Wi‑Fi 6，并提供官方 Buildroot 和 SDK。

本项目不建议从零自己写摄像头驱动、H.265 编码器、Wi‑Fi 协议或 GPIO 轮询。优先复用 Linux 和 Luckfox / Rockchip 已经提供的能力：

- 摄像头、ISP、H.265：使用 Luckfox SDK / Rockchip RK MPI 现成接口。
- Wi‑Fi：使用 `wpa_supplicant + udhcpc`。
- 按键：使用 Linux `gpio-keys`，按键事件统一进入 `/dev/input/eventX`。
- HTTP 控制：使用 `libmicrohttpd`。
- H.265 文件上传：使用 `libcurl`。
- JSON：使用 `nlohmann/json`。
- 日志：优先 `spdlog`；如果希望依赖最少，可以退回 libc `syslog()`。
- 服务自动启动：使用 Buildroot / BusyBox 的 init 脚本；量产版增加 watchdog / respawn。

这样做的原因很简单：**最难、最容易出问题的底层部分尽量不自己写，自己的 C++ 代码只负责业务状态机。**

---

# 2. 整体系统结构

```text
                         专用 AP / 路由器
                     ┌─────────────────┐
                     │  固定 SSID/密码 │
                     │   DHCP 分配 IP  │
                     └───────┬─────────┘
                             │
                 Wi‑Fi       │       网线
                             │
          ┌──────────────────┴──────────────────┐
          │                                     │
          ▼                                     ▼
┌──────────────────┐                   ┌──────────────────┐
│   Pico Zero 仪器  │                   │     Windows PC   │
│                  │                   │                  │
│  Camera          │                   │  Flutter 上位机  │
│      ↓           │                   │       ↓          │
│  H.265 硬编码     │                   │  接收 H.265      │
│      ↓           │                   │       ↓          │
│  eMMC 临时保存    │ ─── Wi‑Fi ───▶   │  FFmpeg 抽帧     │
│      ↓           │                   │       ↓          │
│  上传队列         │ ◀── 控制/确认 ── │  图片/数据保存   │
└──────────────────┘                   └──────────────────┘
```

### 为什么电脑建议用网线接 AP

- 避免 Windows USB Wi‑Fi 热点和驱动兼容性问题。
- PC 与路由器连接稳定，设备只需要处理自己这一侧的 Wi‑Fi。
- 多台仪器可以同时连接同一个 AP。
- 后续调试时可以直接在电脑抓包、Ping、HTTP 调试。

> 路由器需要关闭 `AP Isolation / Client Isolation`，否则无线仪器可能无法访问电脑。

---

# 3. Pico Zero 设备端软件分层

建议只运行一个核心业务进程：`instrument_app`。

```text
instrument_app
│
├── AppController             # 总状态机
│
├── ButtonManager             # 三按键、组合键、长按识别
│
├── CameraManager             # Camera / ISP 生命周期
│
├── EncoderManager            # H.265 编码
│
├── CaptureManager            # 一轮 5 秒拍摄流程
│
├── WifiManager               # Wi‑Fi连接/断开/配对状态
│
├── DiscoveryService          # 局域网设备发现
│
├── ControlServer             # HTTP 控制服务
│
├── UploadManager             # H.265 上传 / 重试 / ACK
│
├── StorageManager            # eMMC文件和待上传队列
│
├── ConfigManager             # 配置文件
│
└── Logger                    # 日志
```

业务模块与硬件接口分开以后，将来从 Pico Zero 换成 RV1106 自研板，主要修改 `CameraManager / GPIO配置 / WiFi配置`，上层状态机基本不用重写。

---

# 4. 三个按键的定义

暂定：

```text
[ 左键 L ]   [ 中键 M ]   [ 右键 R ]
```

## 4.1 按键功能

| 操作 | 时间 | 功能 |
|---|---:|---|
| 左 + 右 | 同时按住 1 秒 | 准备并启动一轮拍摄 |
| 中 + 左 | 同时按住 3 秒 | 进入 Wi‑Fi 配对模式 |
| 中 + 右 | 同时按住 3 秒 | 主动断开 Wi‑Fi |
| 单独按任意一个键 | - | 第一版不执行功能 |

### 为什么不让单键直接拍摄

拍摄属于核心操作，使用 `左 + 右` 两键组合可以明显减少误触。

1 秒长按又能过滤掉碰撞、搬运、手指快速划过造成的误触，同时又不会让用户感觉等待过久。

Wi‑Fi 配对和断网属于低频、影响系统连接的操作，因此使用 `中键 + 左/右` 并要求持续 3 秒，避免用户误操作。

---

# 5. 按键识别规则

## 5.1 不推荐用户态轮询 GPIO

不建议 C++ 每 10ms 去读取三个 GPIO。

建议硬件同事把三个按键配置进 Linux Device Tree 的 `gpio-keys`：

```text
GPIO
 ↓
gpio-keys 内核驱动
 ↓
/dev/input/eventX
 ↓
ButtonManager
 ↓
组合键状态机
```

这样 Linux 内核处理 GPIO 中断和基础消抖，应用程序只处理逻辑，稳定性比自己轮询高，也方便通过 `evtest` 直接调试。

## 5.2 推荐参数

```text
软件/内核消抖：      20~30 ms
组合键允许时间差：    <= 150 ms
L + R 长按：          1000 ms
M + L 长按：          3000 ms
M + R 长按：          3000 ms
```

例如用户先按左键，100ms 后按右键，仍然视为同时按下。

如果两个键中任何一个在时间达到之前松开，则本次组合操作取消。

---

# 6. 推荐的按键硬件要求

按键型号现在不用急着确定，先告诉硬件同事满足这些条件即可：

- 普通瞬时按键（Momentary）。
- 常开 NO（Normally Open）。
- 按下接 GND，GPIO 使用上拉，形成 Active-Low。
- 推荐外置约 10kΩ 上拉，提高抗干扰能力。
- 软件/内核消抖为主；是否增加小 RC 由硬件工程师决定。
- 如果按键通过长线连接到面板，需要考虑 ESD 和干扰。
- 不要占用摄像头、Wi‑Fi、系统启动、调试 UART 等关键复用脚。

### 强烈建议增加一个状态指示

如果硬件成本允许，建议至少增加：

- 1 个 RGB LED，或
- 1 个普通双色 LED，或
- 1 个蜂鸣器。

因为“按住 1 秒 / 3 秒”的操作如果完全没有反馈，用户不知道系统是否已经识别。

例如：

```text
正常待机       LED 常绿
准备拍摄       蓝灯闪一下
拍摄中         蓝灯常亮
上传中         蓝灯慢闪
配对模式       蓝灯快速闪
Wi‑Fi断开      黄灯
错误           红灯
```

这里只是软件状态定义，最终颜色可根据硬件实际调整。

---

# 7. 拍摄状态机

按你的需求，我建议 `左 + 右 1秒` 后不要在手还压着按键时立刻记录第一帧。

推荐流程：

```text
IDLE
 │
 │ L + R 持续 1 秒
 ▼
PREPARE
 │
 │ 初始化/唤醒 Camera
 │ 检查 eMMC 空间
 │ 检查编码器
 │ 给用户反馈
 │
 │ 两键释放后等待约 300~500ms
 ▼
CAPTURE
 │
 │ 1080P / 30fps
 │ H.265
 │ 连续 5 秒
 ▼
FINALIZE
 │
 │ 完成文件
 │ .tmp → .h265 原子重命名
 ▼
UPLOAD_QUEUE
 │
 ├── Wi‑Fi/PC在线 → 上传
 │
 └── 不在线 → 保留本地

上传成功 + PC ACK
 │
 ▼
DELETE / ARCHIVE
 │
 ▼
IDLE
```

### 为什么按键释放后再等约 300~500ms

用户按实体按键时可能会让仪器产生轻微晃动。

让用户松手后再延迟一小段时间开始拍摄，可以减少按键动作对画面的影响。具体延迟以后通过实机测试调整，不必写死为 500ms。

---

# 8. 摄像头和 H.265：不要从零写

Pico Zero 官方 SDK 已经包含 Rockchip Multimedia / RK MPI 相关组件，并且官方 RKIPC 示例已经有 H.265 编码逻辑。

建议从官方示例中抽出最小链路：

```text
Sensor
  ↓
VI / ISP
  ↓
RK_MPI_VENC
  ↓
H.265 Stream
  ↓
文件
```

核心原则：

- 不要自己写 H.265 编码器。
- 不要使用 CPU 软件编码。
- 直接调用 RV1106 的硬件编码单元。
- 第一阶段先跑通官方 Camera / RKIPC demo，再把代码封装进 `CameraManager` 和 `EncoderManager`。

建议第一版编码参数：

```text
分辨率：1920 × 1080
帧率：30 fps
编码：H.265 / HEVC
时长：5 秒
码率：先从 3~5 Mbps 测试
GOP：30 左右起步测试
```

最终码率需要根据实际拍摄内容和接收端图片质量确定。

---

# 9. Wi‑Fi 的设计：区分“联网”和“配对”

这里建议不要把两个概念混在一起。

## 9.1 Wi‑Fi 联网

仪器连接专用 AP / 路由器：

```text
Pico Zero
   │
   │ wpa_supplicant
   ▼
专用 AP
   │
   │ DHCP
   ▼
获取局域网 IP
```

使用 Pico Zero 官方已经支持的：

```text
wpa_supplicant
udhcpc
```

不要自己写 Wi‑Fi 连接协议。

专用 AP 的 SSID / 密码建议在生产或安装阶段写入：

```text
/etc/wpa_supplicant.conf
```

## 9.2 “配对模式”建议定义成应用层配对

因为电脑通过网线、仪器通过 Wi‑Fi，本来就在同一个专用局域网内，因此第一版没有必要让仪器临时再开一个热点。

推荐把：

```text
中键 + 左键 3 秒
```

定义为：

> **允许这台仪器在未来 60 秒内被上位机发现并绑定。**

流程：

```text
M + L 3秒
   ↓
Wi‑Fi如果关闭 → 重新启用
   ↓
连接已配置的专用 AP
   ↓
进入 PAIRING 状态 60 秒
   ↓
允许响应电脑的设备发现请求
   ↓
电脑显示：发现新仪器 CAM-000123
   ↓
用户点击“配对”
   ↓
PC POST /api/v1/pair
   ↓
仪器保存 PC-ID / 配对信息
   ↓
PAIRING → IDLE
```

### 为什么推荐这样，而不是仪器自己开热点

- 不需要在 STA / AP 模式之间反复切换。
- 不需要第一版引入 hostapd / dnsmasq。
- PC 本来就在同一个路由器下面。
- 多台仪器也能同时使用。
- 调试更简单。
- Wi‑Fi 工作状态更少，问题更容易定位。

如果将来设备需要在“没有专用路由器”的环境首次配置 SSID/密码，再增加临时 AP 配网模式即可，不建议第一版就增加复杂度。

---

# 10. “中 + 右 3 秒”断开 Wi‑Fi

推荐语义：

```text
M + R 持续 3秒
       ↓
设置 wifi_enabled = false
       ↓
停止新的上传任务
       ↓
等待当前文件写盘完成
       ↓
wpa_cli disconnect / 停止连接
       ↓
WIFI_OFF
```

### 建议不要删除 SSID / 密码

“断开 Wi‑Fi”与“清除 Wi‑Fi 配置”应该是两个不同动作。

中 + 右只断开，并保留网络配置，避免用户误操作后必须返厂重新写 Wi‑Fi 信息。

当再次执行：

```text
M + L 3秒
```

系统可以重新打开 Wi‑Fi、连接专用 AP 并进入配对模式。

如果以后确实需要“恢复出厂 / 清空 Wi‑Fi”，建议放在电脑端管理界面，或者再定义一个更长时间（例如 10 秒）的明确恢复操作，但第一版不增加。

---

# 11. 网络通信建议

第一版只保留：

```text
UDP + HTTP
```

暂时不加入 MQTT、WebSocket、mDNS。

原因：需求目前比较明确，协议越少，设备越容易稳定和调试。

## 11.1 UDP：设备发现

电脑点击“搜索设备”：

```text
PC → UDP Broadcast → DISCOVER_INSTRUMENT
```

处于允许发现状态的仪器回复：

```json
{
  "device_id": "CAM-000123",
  "model": "PICOZERO-CAM",
  "ip": "192.168.50.21",
  "state": "idle",
  "pairing": true,
  "version": "1.0.0"
}
```

不建议设备每秒主动广播。

这样平时几乎没有发现流量，省电也更容易抓包调试。

> AIC8800DC 的局域网广播行为要在实机阶段验证。如果广播受驱动/路由器设置影响，可保留“路由器 DHCP 列表扫描 / 指定网段探测”作为上位机 fallback。

## 11.2 HTTP：控制

例如：

```text
GET  /api/v1/status
POST /api/v1/capture
POST /api/v1/pair
POST /api/v1/wifi/disconnect
GET  /api/v1/storage
```

返回统一 JSON：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

## 11.3 HTTP：上传 H.265

拍摄完成后仪器主动上传到电脑：

```text
POST http://PC_IP:PORT/api/v1/upload
```

建议 Header / metadata 包含：

```text
Device-ID
Capture-ID
Timestamp
Width
Height
FPS
Codec
Duration
File-Size
SHA256（可选，量产建议）
```

电脑完整保存后返回 ACK：

```json
{
  "code": 0,
  "capture_id": "CAM000123-20260927-00125",
  "received": true
}
```

只有收到明确 ACK 后，仪器才允许删除本地待上传文件。

---

# 12. 推荐的开源 / 官方组件

| 模块 | 推荐组件 | 用途 | 为什么 |
|---|---|---|---|
| 系统 | Luckfox Pico SDK / Buildroot | Linux系统 | 官方适配 Pico Zero |
| Camera / ISP / H.265 | Rockchip RK MPI / RKIPC 示例 | 摄像、硬编码 | 不重复造底层轮子 |
| Wi‑Fi | wpa_supplicant | STA连接 | Linux成熟标准组件 |
| DHCP | BusyBox `udhcpc` | 获取IP | Buildroot常用、轻量 |
| 按键 | Linux `gpio-keys` | GPIO按键事件 | 内核中断/消抖，稳定 |
| 按键用户态 | evdev / libevdev | 读取按键 | Linux标准输入体系 |
| HTTP Server | GNU libmicrohttpd | 接收PC控制 | 小型、成熟的 HTTP/1.1 Server |
| HTTP Client | libcurl | 上传视频 | 非常成熟，重试/超时/trace方便 |
| JSON | nlohmann/json | 控制消息 | C++接口简单、MIT |
| 日志 | spdlog | 文件/控制台日志 | 易读、支持滚动日志、MIT |
| PC 视频处理 | FFmpeg | H.265解码/抽帧 | 行业标准开源工具 |

## 为什么第一版不推荐 cpp-httplib

Pico Zero 的 Cortex-A7 是 32 位 ARM。

当前 cpp-httplib 上游明确说明 32 位平台不受支持，仅做基本编译检查，并提示可能存在 32 位整数截断等问题。

因此本项目不优先采用它作为量产设备网络核心。

---

# 13. 上传队列：断网也不能丢数据

本地目录建议：

```text
/data/capture/
├── pending/
├── uploading/
├── failed/
└── logs/
```

一次拍摄：

```text
CAM000123_20260927_160501.tmp
              ↓
拍摄完整结束
              ↓
CAM000123_20260927_160501.h265
```

同时创建一个小 metadata：

```text
CAM000123_20260927_160501.json
```

如果上传失败：

```text
保留本地
 ↓
5秒后重试
 ↓
15秒
 ↓
60秒
 ↓
5分钟
```

不要 100ms / 1秒无限快速重试，否则断网时只会耗电和刷日志。

设备重启后，`StorageManager` 扫描 `pending/`，自动恢复未完成上传任务。

这样即使应用崩溃或设备突然重启，也不会依赖一块复杂数据库才能找回待上传数据。

---

# 14. 存储安全策略

建议：

```text
剩余 > 1GB        正常
剩余 512MB~1GB    警告上位机
剩余 < 512MB       禁止开始新的拍摄
```

第一版不要自动删除“尚未上传成功”的视频。

只删除：

```text
PC已经明确 ACK 的文件
```

这样数据安全优先。

后续如果确实存在长期断网需求，再定义“最旧未上传文件淘汰策略”。

---

# 15. 省电策略

功耗的大头不是 HTTP/UDP，而是：

```text
Camera Sensor
ISP
H.265 Encoder
Wi‑Fi RF
CPU
```

所以主要控制硬件模块生命周期。

## IDLE

```text
Camera      OFF / Standby
ISP         OFF
VENC        OFF
CPU         正常 idle / DVFS
Wi‑Fi       根据模式决定
```

## PREPARE / CAPTURE

```text
Camera ON
ISP ON
VENC ON
```

## 拍摄完成

```text
立即关闭 Camera / ISP / VENC
只保留文件上传任务
```

## 网络建议提供两个配置模式

```text
network_mode = always_on
```

开发阶段推荐：Wi‑Fi一直连着 AP，上位机随时可以搜索和控制。

```text
network_mode = upload_only
```

未来如果设备靠电池、极端关注功耗：拍摄/上传时才联网，上传完成断开。

第一版建议 `always_on`，因为更方便调试。

Wi‑Fi Power Save 可以后续在 AIC8800DC 实机验证通过后打开，不要在软件未稳定前同时优化太多变量。

---

# 16. 应用总状态机

```text
                     ┌────────────┐
                     │    BOOT    │
                     └─────┬──────┘
                           ▼
                     ┌────────────┐
             ┌──────▶│    IDLE    │◀──────────────┐
             │       └────┬───┬───┘               │
             │            │   │                   │
             │   L+R 1s   │   │ M+L 3s           │
             │            │   │                   │
             │            ▼   ▼                   │
             │      ┌────────┐ ┌─────────────┐    │
             │      │PREPARE │ │   PAIRING   │────┘
             │      └───┬────┘ │   60 sec    │
             │          ▼      └─────────────┘
             │      ┌────────┐
             │      │CAPTURE │  5 秒 H.265
             │      └───┬────┘
             │          ▼
             │      ┌────────┐
             │      │FINALIZE│
             │      └───┬────┘
             │          ▼
             │      ┌────────┐
             │      │UPLOAD  │
             │      └───┬────┘
             │          │ ACK / 排队
             └──────────┘

IDLE -- M+R 3s --> WIFI_OFF
WIFI_OFF -- M+L 3s --> WiFi ON --> PAIRING
```

### 状态优先级

建议组合键只在 `IDLE / WIFI_OFF` 识别。

拍摄过程中不要让新的配对或断网操作立刻破坏当前文件。

如果拍摄时检测到 `M + R`，第一版可以忽略并记录日志；后续如果确实需要，可以设计成“本轮拍摄结束后断网”。

---

# 17. 推荐线程模型

不要每个功能都创建很多线程。

256MB RAM 下保持结构简单：

```text
主线程
 └── AppController / 状态机

Button线程
 └── 阻塞读取 /dev/input/eventX

Camera/VENC线程
 └── 拍摄期间存在

Network线程
 └── HTTP Server / Discovery

Upload线程
 └── 有文件时工作
```

大部分线程平时阻塞等待，不要做 `while(true) + usleep(10ms)` 的高频轮询。

---

# 18. 配置文件建议

```json
{
  "device_id": "CAM-000123",
  "device_name": "Instrument-01",
  "wifi_enabled": true,
  "wifi_ssid": "Instrument_AP",
  "network_mode": "always_on",
  "capture": {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "duration_ms": 5000,
    "codec": "h265",
    "bitrate_kbps": 4000
  },
  "pair": {
    "paired": false,
    "pc_id": ""
  }
}
```

Wi‑Fi 密码不要直接写进业务 JSON，继续交给 `wpa_supplicant.conf` 管理。

---

# 19. 日志设计

建议日志格式：

```text
2026-09-27 16:10:31.251 [INFO]  [BUTTON] L+R long press accepted
2026-09-27 16:10:31.752 [INFO]  [CAMERA] sensor ready
2026-09-27 16:10:31.811 [INFO]  [VENC] H265 1920x1080 30fps started
2026-09-27 16:10:36.823 [INFO]  [CAPTURE] complete, 2.61 MB
2026-09-27 16:10:37.100 [INFO]  [UPLOAD] start capture_id=...
2026-09-27 16:10:37.920 [INFO]  [UPLOAD] ACK received
```

日志至少分：

```text
BUTTON
CAMERA
VENC
WIFI
DISCOVERY
HTTP
UPLOAD
STORAGE
SYSTEM
```

现场出现问题时可以很快判断是：按键没触发、Camera失败、编码失败、Wi‑Fi掉线还是上传失败。

量产版对日志做滚动，例如只保留 10~30MB，防止日志写满 eMMC。

---

# 20. PC 上位机第一版建议

第一版不必引入 Rust，也不必一开始做 C++ DLL。

推荐：

```text
Flutter Windows
│
├── UDP 设备搜索
├── HTTP 控制
├── HTTP 文件接收服务
├── 设备列表
├── 拍摄记录
└── 调用 FFmpeg.exe
       ↓
     H.265 解码
       ↓
     抽帧 / 裁剪
```

Flutter 负责 UI 和普通网络业务；FFmpeg 负责视频，不自己写 H.265 解码。

如果以后增加 OpenCV、复杂算法或高性能批处理，再增加 C++ DLL，通过 Dart FFI 调用。

这样第一阶段开发量最小。

---

# 21. 第一阶段建议开发顺序

不要一上来全部一起开发。

## Phase 1：硬件基础

1. Pico Zero 官方 Buildroot 启动。
2. UART 调试稳定。
3. Wi‑Fi 能稳定连接专用 AP。
4. 三个 GPIO 按键可以在 Linux input 事件中看到。

## Phase 2：视频

1. 跑通官方 Camera 示例。
2. 跑通官方 H.265 示例。
3. 保存 1080P30 / 5 秒 `.h265`。
4. PC 用 FFmpeg 验证视频和抽帧质量。

## Phase 3：业务程序

1. ButtonManager。
2. 状态机。
3. 文件队列。
4. Wi‑Fi Manager。

## Phase 4：网络

1. UDP 搜索。
2. HTTP status。
3. HTTP pair。
4. H.265 上传。
5. ACK 后删除。

## Phase 5：异常测试

必须测试：

- 拍摄途中拔电。
- 上传途中拔电。
- AP 突然断电。
- PC突然关闭。
- eMMC接近满。
- Wi‑Fi信号弱。
- 快速反复按键。
- 三键同时乱按。
- 连续拍摄 500 轮。
- 运行 24~72 小时稳定性。

---

# 22. 项目目录建议

```text
instrument-firmware/
│
├── app/
│   ├── main.cpp
│   ├── AppController.cpp
│   └── AppController.h
│
├── input/
│   ├── ButtonManager.cpp
│   └── ButtonManager.h
│
├── media/
│   ├── CameraManager.cpp
│   ├── EncoderManager.cpp
│   └── CaptureManager.cpp
│
├── network/
│   ├── WifiManager.cpp
│   ├── DiscoveryService.cpp
│   ├── ControlServer.cpp
│   └── UploadManager.cpp
│
├── storage/
│   ├── StorageManager.cpp
│   └── UploadQueue.cpp
│
├── config/
│   └── ConfigManager.cpp
│
├── common/
│   ├── Logger.cpp
│   ├── ErrorCode.h
│   └── Utils.cpp
│
├── third_party/
│   └── README.md
│
├── tests/
│
├── CMakeLists.txt
└── README.md
```

---

# 23. 当前方案最终结论

第一版推荐固定为：

```text
硬件：Luckfox Pico Zero / RV1106G3
系统：官方 Buildroot
开发：C++17（若官方交叉工具链限制则降到 C++14/11）

Camera / H265：Luckfox / Rockchip RK MPI
按键：Linux gpio-keys + evdev
Wi‑Fi：wpa_supplicant + udhcpc
发现：UDP Broadcast
控制服务：libmicrohttpd
上传：libcurl
JSON：nlohmann/json
日志：spdlog（或 syslog）
PC：Flutter + FFmpeg
```

核心原则只有四条：

1. **底层驱动不重复造轮子。**
2. **按键、拍摄、Wi‑Fi全部进入明确状态机，不写成散乱回调。**
3. **视频先落 eMMC，上传成功收到 ACK 后再删除，断网不丢数据。**
4. **第一版只使用 UDP + HTTP，把协议数量压到最低。**

---

# 24. 主要参考项目 / 文档

- Luckfox Pico Zero 官方资料  
  https://wiki.luckfox.com/Luckfox-Pico-Zero/

- Luckfox Pico Zero Wi‑Fi / Bluetooth  
  https://wiki.luckfox.com/Luckfox-Pico-Zero/WiFi-BT/

- Luckfox Pico SDK  
  https://github.com/LuckfoxTECH/luckfox-pico

- Luckfox RK MPI Examples  
  https://github.com/LuckfoxTECH/luckfox_pico_rkmpi_example

- libcurl  
  https://github.com/curl/curl

- GNU libmicrohttpd  
  https://www.gnu.org/software/libmicrohttpd/

- nlohmann/json  
  https://github.com/nlohmann/json

- spdlog  
  https://github.com/gabime/spdlog

- FFmpeg  
  https://ffmpeg.org/

---

## 需要硬件同事下一步确认的内容

1. 三个按键最终使用的 Pico Zero / RV1106 GPIO。
2. 是否增加 LED / 蜂鸣器作为长按和状态反馈。
3. Camera Sensor 最终型号及 MIPI 接口定义。
4. Camera 是否有独立 Power Enable / Reset GPIO，方便待机省电。
5. 专用 AP 的 SSID / 密码是否固定在出厂配置。
6. 自研板上 Wi‑Fi 天线形式及天线净空。

以上 6 项确认后，软件层可以直接进入接口冻结和编码阶段。
