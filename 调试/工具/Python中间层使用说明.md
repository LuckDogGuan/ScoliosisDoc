# Python 调试中间层使用说明

主程序：`D:/code/Scoliosis/Luckfox/调试/工具/instrument_debug_proxy.py`。

配套自检：`test_debug_proxy.py`（本机 UDP 原包和 2 MiB HTTP 流式验证）、`test_debug_proxy_board.py`（实板端口 8081 验收，需要专用板端模拟输入，不作为现场使用入口）。正式运行继续 Flutter 直连板端。

## 启动

在 PowerShell 中运行，先启动代理，再启动 Flutter：

```powershell
Set-Location D:/code/Scoliosis/Luckfox
python 调试/工具/instrument_debug_proxy.py --port 18081 --flutter-port 8080 --log 调试/记录/instrument-proxy.jsonl --data-root D:/code/Scoliosis/ScoliosisFlutter/data
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
