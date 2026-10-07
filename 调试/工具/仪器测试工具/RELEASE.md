# 仪器测试工具正式交付

唯一 EXE：`release/仪器测试工具.exe`（74272444 字节）。
SHA256：`35afe9afd0979821463b06f1e5cd680103bc41a66dd4142c0a3d9f6ccf334b51`。
源码自检 `python 仪器测试工具.py --check` 已通过 7 组；既有实板/打包证据见 `../../记录/usb-uvc-tool-20261002`，本次未重新构建 EXE 或操作设备。
必要 runtime payload 保留，构建源码唯一在 WSL `tools/uvc-v1.0.0`，README 中固定 SDK/工具链依赖继续有效。
