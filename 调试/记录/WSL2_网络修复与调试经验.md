# WSL2 网络修复与调试经验（2026-09-25）

## 结论

Windows 使用 `127.0.0.1:7897` 代理；原 WSL NAT 无法映射这个 localhost，启动时报警。现已在 `C:\Users\31186\.wslconfig` 设置 `[wsl2] networkingMode=mirrored` 并执行 `wsl --shutdown`。Luckfox Ubuntu 22.04 启动警告消失，代理变量已自动注入；Ubuntu 24.04 也可访问软件源。此设置对所有 WSL 发行版生效。[微软 WSL 网络说明](https://learn.microsoft.com/en-us/windows/wsl/networking) · [配置说明](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)

```text
Windows 本机代理 → WSL mirrored → Ubuntu 的 curl / apt / GitHub
                                   └→ Gitee Git：另查仓库鉴权
```

## 实测与边界

| 检查 | 结果 |
| --- | --- |
| Luckfox Ubuntu 启动 | 无 localhost/NAT 警告 |
| Ubuntu 软件源 | `curl` 返回 200；`apt-get update` 成功 |
| GitHub 官方 Luckfox 仓库 | `git ls-remote` 成功 |
| Gitee | 网页返回 200；Git 接口匿名请求返回 401。Windows Git 使用已有凭据管理器可查询；WSL Git 无凭据时失败。 |

曾按 [Git Credential Manager 的 WSL 指南](https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/wsl.md) 尝试共享 Windows 凭据，但此发行版的 Windows 程序互通复测出现 `Exec format error`，故已撤回该 Git 设置。当前拉源码优先用 WSL 中的官方 GitHub 仓库；必须使用 Gitee 时先用 Windows Git。板卡专用路由器通信尚未接实板验证。

## 下次排查顺序

1. `wsl.exe -d Luckfox-Ubuntu-22.04 -- curl -I https://archive.ubuntu.com`：先看 HTTPS；失败时确认 Windows 代理仍在运行。
2. `wsl.exe -d Luckfox-Ubuntu-22.04 -u root -- apt-get update`：再看软件源。
3. `wsl.exe -d Luckfox-Ubuntu-22.04 -- git ls-remote https://github.com/LuckfoxTECH/luckfox-pico.git HEAD`：最后看 Git。Gitee 返回 401 应单查凭据，不算 DNS 故障。

经验：分别验证 DNS、HTTPS、包管理器、Git；Windows PowerShell 调 Linux 含 `$` 的脚本时，要防止 PowerShell 提前展开变量，否则会制造假错误。
