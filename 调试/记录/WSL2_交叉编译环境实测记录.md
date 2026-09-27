# Pico Zero：WSL2 交叉编译环境实测记录

日期：2026-09-25。目的：验证 Codex 能控制 WSL2，并验证是否能为本地 Pico Zero Buildroot 固件编译应用。板卡尚未到手。

## 为什么这样做

    本地预编译固件 update.img ──烧录──> 板卡
    Codex ──wsl.exe──> Ubuntu 22.04 ──交叉编译──> ARM 应用 ──传到板卡
                                      ↑
                         与固件的架构、运行库匹配

这两条线互不替代。现阶段做按键、取图、传图，先用官方预编译镜像和独立交叉工具链；只有现成固件缺摄像头驱动、ISP 能力或必要配置时，才需要完整 SDK 镜像编译。[官方交叉编译](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Cross-Compile/) · [完整 SDK](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/SDK/SDK-Image-Compilation/)

## 实际过程与证据

| 步骤 | 做了什么 | 结果说明 |
| --- | --- | --- |
| 1. 选系统 | 原有 WSL2 是 Ubuntu 24.04；从本地 Ubuntu2204-WSL.zip 取 x64.appx 内的 install.tar.gz，导入独立 Luckfox-Ubuntu-22.04。 | 启动后确认 Ubuntu 22.04、x86_64、普通用户 guanjx；符合官方完整 SDK 的主机版本要求。 |
| 2. 装依赖 | apt update 成功；按官方 SDK 页的依赖清单安装。 | gcc 11.4、make 4.3 可用，官方清单中的包检查通过。 |
| 3. 取工具链 | 从官方交叉编译页下载并解压 arm-rockchip830-linux-uclibcgnueabihf.tar.gz。 | 交叉 gcc 8.3 可运行；这是生成板端 ARM 程序的编译器，主机 gcc 不能直接替代。 |
| 4. 编译测试 | 用交叉 gcc 编译 hello.c 为 hello-pico-zero；用 file、readelf 检查。 | 得到 ELF32 ARM EABI5，可执行文件请求 /lib/ld-uClibc.so.0。 |
| 5. 对照固件 | 查本地 Luckfox_Pico_Zero_eMMC_260604.zip 的 rootfs.img。 | 镜像为 ext4，确有 /lib/ld-uClibc.so.0 链接；与测试程序请求的解释器名称一致。 |

复核编译（先在 Windows PowerShell 进入 WSL，后续在 Ubuntu 内执行）：

    wsl.exe -d Luckfox-Ubuntu-22.04
    cd ~
    cat hello.c
    ./arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-gcc -Wall -Wextra -O2 hello.c -o hello-pico-zero
    file hello-pico-zero
    readelf -l hello-pico-zero

WSL 内保留 /home/guanjx/hello.c、hello-pico-zero 和独立交叉工具链。发行版安装在 D:\WSL\Luckfox-Ubuntu-22.04\instance；原有 Ubuntu 24.04 未修改。导入时的核心命令：

    wsl.exe --import Luckfox-Ubuntu-22.04 D:\WSL\Luckfox-Ubuntu-22.04\instance D:\WSL\Luckfox-Ubuntu-22.04\install.tar.gz --version 2

## 网络与未验证项

- WSL 网络已改为 mirrored，原 localhost 代理警告消失；软件源、apt、GitHub 复测成功。Gitee Git 仍有独立的凭据问题。过程与复核命令见[网络修复与调试经验](WSL2_网络修复与调试经验.md)。
- 已证明主机能生成目标架构程序，**未证明板端能运行**。板到后先烧录对应摄像头固件，通过串口/ADB/SSH 登录，再把 hello-pico-zero 传到板端执行。
- **未下载或编译完整 SDK**，也未启动本地 VMware 包。摄像头的独立高质量照片、按键、Wi-Fi 传图仍需实板验收；RTSP 能预览不等于照片抓拍已可用。
- 安装时解出的 x64.appx、install.tar.gz、rootfs.img 三份临时副本仍在 D:\WSL\Luckfox-Ubuntu-22.04，约 1.56 GB。尝试删除首个副本时被自动策略以“blocked by policy”拒绝，未继续删除；这些副本不影响已导入的 WSL 发行版。

## 到板后的判断

| 实测结果 | 下一步 |
| --- | --- |
| hello-pico-zero 能在板上运行 | 保持“现成固件 + 用户态交叉编译”路线。 |
| 文件已传到板上却无法运行 | 核对板上架构、固件版本、动态加载器及缺失库，再决定是否更换工具链。 |
| RTSP 可预览，却无法保存合格的独立照片 | 核对该摄像头对应镜像与 ISP/JPEG 接口；现成固件无法满足时再引入完整 SDK。 |
