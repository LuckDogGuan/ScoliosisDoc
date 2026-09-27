# Pico Zero 体表图像采集：路线与环境实测

更新：2026-09-25。目标是学校儿童站立背部的手持拍摄原图、实时预览、按键保存及经专用路由器传到 Windows 电脑。当前只负责获取清晰、可追溯的图片；图像分割、AI 判读和“度数”计算不在本阶段。

## 1. 先分清两件事

| 问题 | 已核对的结论 |
| --- | --- |
| Codex 能否操作 WSL2？ | 能。当前 Windows 原生 Codex 任务已直接调用 wsl.exe，在独立 Ubuntu 22.04 中安装依赖并交叉编译。Codex 桌面版切换“代理运行在 WSL”是另一种模式，本次未切换。 |
| 固件包是否能直接使用？ | 本地 Luckfox_Pico_Zero_eMMC_260604.zip 内有预编译 update.img、boot.img、rootfs.img 等；update.img 可按官方 Windows 烧录流程使用，但须解压、连接实板烧录，尚未实机验证。它不是 SDK 源码。 |
| 做应用是否必须编完整 SDK？ | 官方把 Buildroot 应用交叉编译与全量镜像编译分开。先用现成镜像和单独的 uClibc 交叉工具链；按键、传图可先走用户态。摄像头抓拍若缺所需接口、驱动或 ISP 配置，再取得 SDK 并考虑编镜像。 |

## 2. 环境实测

按步骤复核见：[WSL2 交叉编译环境实测记录](WSL2_交叉编译环境实测记录.md)。这里保留结论与下一步判断。

- 新建 WSL2 发行版：Luckfox-Ubuntu-22.04，来自本地 Ubuntu2204-WSL.zip；安装在 D:\WSL\Luckfox-Ubuntu-22.04\instance，默认用户 guanjx。原有 Ubuntu 24.04 未改动。
- Ubuntu 22.04 x86_64 启动成功；官方 SDK 文档所列 apt 依赖安装成功，gcc 11.4、make 4.3 可运行。
- 从官方交叉编译页下载独立 Buildroot/uClibc 工具链；交叉 gcc 8.3 成功编译 hello.c。产物为 ELF32 ARM EABI5，动态解释器 /lib/ld-uClibc.so.0；本地固件 rootfs.img 是 ext4，确有该解释器链接。
- 这证明“主机能为该类 Buildroot 固件生成程序”，不证明板端已运行，也不证明摄像头抓拍 API 已可用。板子到手后需核对实际固件版本和运行库。
- 本地 Buildroot 离线依赖包 dl.tar.bz2 的 SHA256 与随附校验文件一致；只有将来编全量 SDK 时才需要使用。

可从 Windows 进入该环境：

    wsl.exe -d Luckfox-Ubuntu-22.04
    # WSL 内测试文件：/home/guanjx/hello.c、/home/guanjx/hello-pico-zero
    # 工具链：/home/guanjx/arm-rockchip830-linux-uclibcgnueabihf/bin/

完整 SDK 镜像编译的官方目标是 Ubuntu 22.04 x86_64，Zero eMMC 配置为 BoardConfig-EMMC-Buildroot-RV1106_Luckfox_Pico_Zero-IPC.mk。**尚未下载完整 SDK，也尚未编译完整镜像**；目前无需为此占用大量磁盘和时间。项目内的 VMware 压缩包是否已包含可工作的 SDK，未启动虚拟机核实，不把文件名当验证结果。

## 3. 开发与调试路径

电脑侧工具、到板烧录步骤、传输命令及失败定位见：[烧录、传输与调试闭环](Pico_Zero_烧录传输调试闭环.md)。

    Codex Windows 任务
       ├─ wsl.exe → Ubuntu 22.04 → 编辑/交叉编译板端程序
       └─ Windows → SocToolKit 烧录、COM 串口、电脑接收与预览
    Pico Zero ── 2.4 GHz Wi-Fi ── 专用路由器 ── 网线 ── Windows 电脑
                  RTSP 预览；按键后传输独立拍摄的照片

- 目前 Codex 已能从 Windows 控制 WSL2。若今后长期在 Linux 文件系统内维护 SDK，可在 Codex 桌面设置中把代理环境切换为 WSL2，再从 WSL 的 /home 打开项目；“终端选择 WSL”与“代理运行在 WSL”不是同一设置。
- Windows 上烧录、串口和照片接收不需要把 USB 或入站服务转发进 WSL。串口按官方引脚图接 USB-TTL，用已安装的 PuTTY 或 pySerial 通过 Windows COM（115200）记录日志；当前没有专用串口 MCP，也不必先装一个。一个 COM 口同一时间只给一个程序使用。
- 调试顺序：无法启动看串口日志；系统能启动而 Wi-Fi 未通时用 USB ADB；Wi-Fi 通后用 SSH、RTSP 和照片上传；烧录问题回到 Windows SocToolKit。
- WSL 已切换 mirrored 网络，localhost 代理警告消失；Ubuntu 软件源、apt、GitHub Git 实测通过。Gitee Git 的凭据问题单独处理，见[网络修复与调试经验](WSL2_网络修复与调试经验.md)。
- 专用路由器与互联网分开考虑：板卡和电脑在同一局域网，电脑最好网线接路由器；路由器关闭客户端隔离、给板卡固定 DHCP 租约。电脑可另用 Wi-Fi 访问 Codex；专用局域网断互联网时，板端拍摄与传图仍应可工作。电脑接收服务只开放所需端口，不关闭整机防火墙。

## 4. 板卡到手后的验收顺序

    固件烧录/串口启动
      → IMX415 或 ISG1321 的对应镜像与预览
      → 独立高质量 JPEG 照片
      → GPIO 按键一次一拍
      → Wi-Fi 上传、电脑确认、断线重传
      → 手持画质与拍摄记录验收

1. 先确认当前固件对应 Pico Zero eMMC 和摄像头；官方列有 IMX415 彩色与 ISG1321 单色，并给 RTSP 预览方法。两款摄像头不假定能热插拔切换。先以 IMX415 做彩色主方案，再对照 ISG1321 的运动清晰度。
2. RTSP 只供构图预览。保存图片应走真实拍照/JPEG 路径，不截取预览视频帧；实测分辨率、曝光、白平衡、对焦/景深、边缘畸变和暗光噪声。摄像头标称像素不等于板端已输出的照片像素。
3. 核对可用 GPIO、上拉和按键消抖；优先检查板上的 luckfox-config 运行时配置。先用非患者样本测试，单次按键只产生一张照片。
4. 照片保留原图、时间、设备号、唯一编号和拍摄记录。板端保留待传队列，电脑确认收到后再清除；验收断线不丢图、重传不重复入库。手持拍摄统一距离、镜头高度、照明、站姿与背景，及时提示重拍。
5. 先做 Windows 浏览器端“实时预览 + 原图/拍摄记录查看”。此阶段不做模型、分割或医学角度输出。后续真实儿童图像由使用单位管理授权、访问控制和本地保存。

## 5. 3D 与辐射

普通 RGB 拍照、被动双目/多视角光学 3D 不产生 X 光那种电离辐射；主动红外结构光也不属于电离辐射，但具体设备仍须核对儿童使用的光学/激光眼安全。现有两款不同传感器并不会自动构成已标定的 3D 系统。当前目标是清晰背部照片，先不增加 3D 硬件和标定工作；光学体表形态也不能直接等同于脊柱 X 光 Cobb 角。

## 资料

- 官方：[Pico Zero](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero)、[交叉编译](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Cross-Compile/)、[完整 SDK 编译](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/SDK/SDK-Image-Compilation/)、[eMMC 烧录](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Getting-Started/eMMC-Models/)、[摄像头](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/CSI-Camera/)、[GPIO 配置](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Peripherals/Luckfox-config/)、[登录与串口](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Login/)。
- 环境：[Codex Windows/WSL](https://learn.chatgpt.com/docs/windows/windows-app)、[微软 WSL 网络](https://learn.microsoft.com/en-us/windows/wsl/networking)、[微软 WSL USB](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)、[pySerial](https://pyserial.readthedocs.io/en/latest/tools.html)。
- 3D 边界：[WHO 辐射概览](https://www.who.int/health-topics/radiation)、[3D 体表扫描研究](https://pubmed.ncbi.nlm.nih.gov/27927552/)。
