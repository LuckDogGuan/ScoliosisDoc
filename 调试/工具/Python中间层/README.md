# Python 调试中间层使用说明

## 3.3.1 灯光调试

新增入口 `light_test.py`，通过已记录密钥的 SSH 调用同一板端 `--light-test`，核对序列号、设备ID和空闲状态。
接线、五种模式、30秒限时、GPIO32核验与回退见 [中键灯与背光说明](../../软件架构/中键灯与背光_3.3.1_说明.md)。
下位机完整交付包唯一放在 WSL `/home/guanjx/luckfox/Scoliosis/releases/<版本>/`；Windows 通过 `\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\releases` 访问，不再保存副本。

## 目录与只读 IP / SSH 检查

本目录集中存放中间层、两个原有验证脚本以及 `discover_ssh.py`。原 `调试/工具/instrument_debug_proxy.py` 是兼容入口，已有启动命令仍有效。目录迁移只调整相对路径，没有修改转发协议。

在项目根目录执行以下命令，通过中间层 `/debug/udp` 转发 `hello_query`，从已配对设备的实时回复取得 IP，再交互输入 SSH 密码验证登录：

```powershell
python 调试/工具/Python中间层/discover_ssh.py --bind 192.168.101.2 --bind 192.168.0.20 --ssh
```

`--bind` 是电脑当前 IPv4，可重复指定；请按实际网卡调整。省略 `--ssh` 只发现 IP。`--target` 可指定广播地址或候选地址。已配对设备 ID 默认来自 Flutter `data/设备.json`，可用 `--data-root` 指定数据目录；未配对设备不在此工具的发现范围内。

发现用临时本机 HTTP 服务复用现有 Bridge，不启动正式代理，不改变配对、上传目标或拍摄状态。校验回复源端口、版本、设备、电脑身份、序号、nonce、操作和成功状态。没有匹配回复或 SSH 认证失败时退出码为 1。

IP 发现只用 Python 标准库；可选 SSH 使用本机已有 Paramiko（本次 5.0.0），没有新增安装。无人值守时可用 `--password-stdin` 从标准输入提供密码，避免放入命令行参数或文件。交互使用不要加这个选项。

每次运行在 `调试/记录/SSH登录/<年月日-时分秒>/` 保存 `proxy.jsonl`、`discovery.json` 和（执行 SSH 时）`ssh.json`，包括请求回复、命令、输出和错误，密码不记录。`known_hosts` 保存在父目录：首次连接信任实时发现的地址并记录指纹，后续拒绝不一致的主机密钥。

官方登录资料：[Luckfox Pico Zero 登录](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/Login/)。Buildroot 默认账号为 root，默认口令见官方页面；实际 IP 必须现场发现。2026-10-02 的真实成功登录过程见 `调试/记录/SSH登录/20261002-154155/登录过程.md`。

本机中间层回归检查：

```powershell
python 调试/工具/Python中间层/test_debug_proxy.py
```

`test_debug_proxy_board.py` 是原实板拍摄回归，可能触发拍摄与配对操作，本次没有运行。

主程序：`D:/code/Scoliosis/Luckfox/调试/工具/Python中间层/instrument_debug_proxy.py`。

配套自检：`test_debug_proxy.py`（本机 UDP 原包和 2 MiB HTTP 流式验证）、`test_debug_proxy_board.py`（实板端口 8081 验收，需要专用板端模拟输入，不作为现场使用入口）。正式运行继续 Flutter 直连板端。

## 启动

在 PowerShell 中运行，先启动代理，再启动 Flutter：

```powershell
Set-Location D:/code/Scoliosis/Luckfox
python 调试/工具/Python中间层/instrument_debug_proxy.py --port 18081 --flutter-port 8080 --log 调试/记录/instrument-proxy.jsonl --data-root D:/code/Scoliosis/ScoliosisFlutter/data
```

另开一个 PowerShell 窗口：

```powershell
Set-Location D:/code/Scoliosis/ScoliosisFlutter
$env:INSTRUMENT_DEBUG_PROXY='http://127.0.0.1:18081'
flutter run -d windows
```

代理默认用 18081 接收调试转发，转到 Flutter 8080；电脑和代理必须在同一台机器。保留设备、启动、许可、视频、事件和授权原 ID，以及原始来源端点；UDP 原字节转发、Flutter 校验仍生效；视频按 64 KiB 分块，日志仅记视频大小与哈希。日志 `D:/code/Scoliosis/Luckfox/调试/记录/instrument-proxy.jsonl` 每份 4 MiB，保留两份旧日志。

## 结束调试

代理窗口按 Ctrl+C，读取保存的电脑身份和配对事务恢复仪器直连 8080，日志出现 `restore_direct` 且 `ok=true` 表示成功。随后停止调试 Flutter，清除变量并重新启动正式应用：

```powershell
Remove-Item Env:INSTRUMENT_DEBUG_PROXY -ErrorAction SilentlyContinue
```

异常退出时重新正常启动并退出代理，或关闭该变量后重新启动 Flutter 恢复连接。保留日志用于排查，普通界面不显示调试细节。Release 程序也读取启动环境变量；`flutter run` 为可直接复用的调试命令。

## 后续修改与记录

Python 代码在 Windows 中维护；下位机只在 WSL2 `Luckfox-Ubuntu-22.04:/home/guanjx/luckfox/Scoliosis` 内编辑和构建。代码、版本包和回退关系见 `调试/记录/上下位机版本与进度_2026-10-01.md`，逐项功能验收见 `调试/软件架构/拍摄配对调试改造_实施与验收_2026-10-01.md`。

