# Pico Zero：烧录、传输与调试闭环

更新：2026-09-25。板卡尚未到手；下面“已备好”只代表电脑侧检查通过，不代表实板烧录或摄像头已通过。

## 原理与分工

    Windows：官方 SocToolKit 烧录 → USB 串口/ADB → SSH/SCP → VLC 预览
                       ↑                    ↑
    WSL2 Ubuntu 22.04：交叉编译 ARM 程序 ────┘
    Pico Zero：2.4 GHz Wi-Fi → 专用路由器 → Windows 接收电脑

固件 update.img 是完整系统镜像；交叉编译生成的 ARM 程序是后续放到系统中运行的文件。开发中的文件传输首选 USB ADB 或局域网 SSH/SCP；实际拍摄图片传到医生电脑是另一条业务链路，板到手后再验证。FTP 会增加板端服务与配置，当前不需要。

第一个可核对的闭环是“烧录 → 预览 → 板上产生一张现场照片 → ADB/SCP 拉到电脑 → 核对时间、尺寸和文件内容”。按键自动拍摄、自动传图与断线重传需等独立照片路径验证后再集成，现有官方预览教程尚未证明这三项已经具备。

## 电脑侧已完成

| 项目 | 实测状态 |
| --- | --- |
| 待烧录文件 | 已从本地官方 ZIP 解出 flash_ready/Luckfox_Pico_Zero_eMMC_260604/update.img；ZIP 完整性测试通过，镜像头为 RKFW；SHA256 为 8F227CFC0676C6201F55AF5E5AC6626A35F4BA2F4D8911402A9867DCF38C8B58。它是否为两款摄像头所需镜像仍待实板确认。 |
| 烧录程序 | flash_ready/SocToolKit_V2.2/SocToolKit.exe 已解压；驱动安装器也在 flash_ready/DriverAssitant_v5.13。本轮未运行驱动安装器或执行烧录，因为没有板卡可枚举。 |
| 登录/传输 | Windows ADB 37.0.0、OpenSSH 的 ssh/scp/sftp 已有；adb devices 当前为空。交叉编译测试文件已放到 flash_ready/hello-pico-zero。 |
| 串口 | 开源 PuTTY 0.85 与 pySerial 3.5 已安装；pySerial 枚举结果为 no ports found，需到板后接 USB-TTL。当前无需串口 MCP，Codex 能直接运行现成工具并读取保存的日志。 |
| 预览与编辑 | VLC 3.0.23 位于 D:\SoftWare\VLC；Windows VS Code 1.108 已有 WSL 扩展，新 Ubuntu 22.04 的 VS Code Server 已初始化。 |

## 板到手后按此顺序操作

1. **核对硬件与镜像**：确认板型是 Pico Zero eMMC、使用数据线；摄像头排线按[官方摄像头教程](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/CSI-Camera/)方向插入。该教程要求对应镜像并重启一次以切换 RKIPC 配置，不能先认定本地 260604 镜像同时支持 IMX415 与 ISG1321。
2. **烧录**：Windows 打开 flash_ready/SocToolKit_V2.2/SocToolKit.exe（官方建议管理员运行），选 RV1106；按住板上 BOOT 接 USB，确认工具显示 MaskRom 或 Loader；选 Firmware → 上面的 update.img → Upgrade，等待明确成功提示，再重启。若工具看不到设备，先换数据线/USB 口、检查设备管理器，再按需使用已解压的官方驱动安装器。不要把“选中镜像”当成“烧录成功”。[官方 eMMC 烧录](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Getting-Started/eMMC-Models/)
3. **先留启动日志**：按[官方 Pico Zero 串口引脚图](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Login/)连接 USB-TTL 的 TX、RX、GND，核对电平，不连接未知电源脚。用设备管理器或下列命令找 COM 号；PuTTY 选 Serial、COM 号、115200，并在 Logging 选 All session output 保存启动日志。只有一个程序占用 COM 口。

       py -m serial.tools.list_ports -v
       py -m serial.tools.miniterm COMx 115200

4. **USB 验证应用**：系统启动后先用 Windows ADB；确认只有目标板，再上传预编译测试程序，看到 luckfox-cross-compile-ok 才算验证“编译 → 板端运行”。若 ADB 不可用，先看串口日志。

       adb devices -l
       adb push D:\code\Scoliosis\Luckfox\flash_ready\hello-pico-zero /root/
       adb shell chmod +x /root/hello-pico-zero
       adb shell /root/hello-pico-zero

5. **局域网验证**：板卡连专用路由器的 2.4 GHz Wi-Fi，电脑用网线接同一路由器；从路由器 DHCP 页面或板端 ifconfig 查实际 IP，再用 Windows ssh root@板卡IP 登录。Buildroot 默认账号据官方为 root/luckfox，到板后核对并更改默认密码。手动传程序可用 SCP；SFTP 若板端支持，也可用官方提到的开源 electerm 或 Windows sftp。现代 OpenSSH 的 SCP 若报 SFTP 子系统错误，可试 scp -O。优先从 flash_ready 目录执行，避免 Windows 盘符被误判为远端路径。[官方文件传输](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/File-Transfer/)

       cd D:\code\Scoliosis\Luckfox\flash_ready
       scp -O .\hello-pico-zero root@板卡IP:/root/

6. **摄像头与照片分开验收**：VLC 打开 rtsp://板卡IP/live/0，确认只是实时预览。官方示例的 /userdata/ 出现 image.bmp；若实板也有，可用 adb pull /userdata/image.bmp . 拉到电脑，核对拍摄时间、尺寸及是否为现场新图。然后单独验证合格照片的保存路径、实际分辨率及曝光。按键、照片上传、断网重传要在此之后联调。RTSP 可用或存在示例 BMP，均不证明按键抓拍已可用。[官方摄像头预览](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/CSI-Camera/)

## 故障定位与验收记录

| 卡点 | 先查哪里 | 当前 |
| --- | --- | --- |
| SocToolKit 不识别 | 数据线、BOOT、设备管理器、驱动 | 待板 |
| 烧录成功但不启动 | PuTTY 串口启动日志，镜像型号 | 待板 |
| ARM 程序无法运行 | 串口/ADB 错误、板端架构与运行库 | 待板 |
| Wi-Fi/SSH 不通 | 板端 wlan0、路由器 DHCP、隔离设置、Windows 防火墙目标端口 | 待板 |
| 预览通而照片不合格 | 摄像头对应镜像、ISP/JPEG 路径、实际画质 | 待板 |
| 照片丢失/重复 | 板端待传队列、电脑确认、断线重传记录 | 待板 |

## WSL2 的界面与网络

- **访问方式**：推荐 Windows 上的 VS Code 图形界面连接 WSL2，不必安装完整 Ubuntu 桌面。本机 WSL 扩展和 22.04 远程服务已验证。Windows PowerShell 可执行：

       code --remote wsl+Luckfox-Ubuntu-22.04 /home/guanjx/

  或先执行 wsl.exe -d Luckfox-Ubuntu-22.04，再在 Linux 目录执行 code .；VS Code 左下角应显示 WSL 发行版。WSLg 的 Wayland socket 已存在，可运行单个 Linux GUI 应用，但微软说明它不是完整 Linux 桌面。[VS Code 官方 WSL 用法](https://code.visualstudio.com/docs/remote/wsl) · [微软 WSLg](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)
- **系统管理**：当前默认用户 guanjx 用于日常编译，未设置 sudo 密码；需要安装系统包时，从 Windows 执行 wsl.exe -d Luckfox-Ubuntu-22.04 -u root -- apt-get install 包名。不要以 root 编译完整 SDK。
- **网络**：已将全局 WSL 设置为 mirrored，原 localhost 代理警告消失；软件源、apt、GitHub Git 复测通过。Gitee Git 的凭据问题与网络连通性分开查，见[网络修复与调试经验](WSL2_网络修复与调试经验.md)。板卡到 Windows 的专用路由器传图不经过 WSL，因此不依赖 WSL 入站网络。[微软 WSL 网络](https://learn.microsoft.com/en-us/windows/wsl/networking)
- **双网卡**：专用路由器只承担板卡到 Windows 的局域网通信。若电脑以 Wi-Fi 上网、网线接无互联网的专用路由器，先检查 Windows 默认路由；如网线连接抢走互联网路由，再给专用网卡设置同网段静态 IP 且不填默认网关。板卡与电脑仍需同网段、路由器关闭客户端隔离。
