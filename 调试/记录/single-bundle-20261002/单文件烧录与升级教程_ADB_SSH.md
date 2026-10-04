# Pico Zero 单文件升级包：ADB / SSH 详细教程

日期：2026-10-02。适用对象：本项目的 **Luckfox Pico Zero、RV1106、Buildroot/uClibc、ISG1321 和中/左/右三个按键接线**。这里的“烧录”是向已有 Linux 系统安装应用；系统镜像烧录另见第 10 节。

## 1. 先看结论：需要传几个文件？

**每次只需上传一个 `.tar.gz` 文件。** 包内一起带程序、20 个 WAV、`luckfox_mux_adapter.so`、启动脚本、三键初始化、示例配置、版本说明及校验清单。上传一次，解包后调用一次安装脚本。

| 对象 | 处理方式 | 原因 |
|---|---|---|
| instrument_app | 放入同一包，安装到 /opt/instrument/bin | 保持已验证的 3.3.0 程序 |
| 20 个音频 | 一起压缩，解包到 /opt/instrument/sounds | aplay 按事件名称读取 WAV；拼接为一个长音频会改变播放行为 |
| cJSON / LwBTN | 已编译进 instrument_app | 不需要另外推送这两个源码库 |
| luckfox_mux_adapter.so | 一起压缩，解包到 /opt/instrument/bin | 是 RKiPC 的 LD_PRELOAD 适配库，需要独立共享库文件 |
| libc.so.0、uClibc 加载器、RKiPC、ALSA 等系统组件 | 使用对应基础系统中已有版本 | 不混入另一套 libc，也不替换系统动态库 |
| S79buttons / button_inputs.sh | 一起压缩 | 首次安装也需要初始化实体 GPIO |
| S80instrument / RkLunch.sh | 一起压缩；替换前备份并检查 | 应用自启动及 RKiPC 注入；自定义 USB/UVC 启动需先人工合并 |
| config / Wi-Fi / state / capture / 学生数据 | 留在原位置 | 升级不覆盖配置、配对、事件、删除凭据及待传视频 |

因此，**减少的是交付文件和传输次数**。板端仍需要展开后的运行文件。把程序、音乐和任意 .so 直接二进制拼接，无法得到可运行的 ELF 文件。若以后要求板端也只有一个运行文件，需要另改资源加载和链接方式；本轮没有改业务代码。

## 2. 本次实际交付

只传下面这个包，不需要把旁边的教程和记录也推到板上：

```text
D:\code\Scoliosis\Luckfox\调试\记录\single-bundle-20261002\
  instrument-v3.3.0-20261002-results-bundle1.tar.gz
```

SHA-256（下载、复制或传输后都应一致）：

```text
d6eff1c88504d12a951c40b30adea719d9deb1dac714de9a9ee1cea996fbbdbf
```

程序本身仍是 3.3.0，`bundle1` 是部署包修订号。原始程序 SHA-256：

```text
6555ebcaaae1043acc418509e403387445c012be0abad855456d3027174b1df7
```

本轮已通过 WSL 校验、BusyBox shell 校验及故意破坏音频后的拒绝检查；**实际板端安装、重启、实体按钮和声音验收尚未执行**。本轮设备连接期间没有应用目录，随后 ADB 断开；不要把旧日志中的设备 IP 或序列号当成本次可用连接。

官方支持 ADB push/pull 和 SSH/SCP 文件传输，见 [Luckfox 文件传输](https://wiki.luckfox.com/zh/Luckfox-Pico-Zero/File-Transfer/)。

## 3. 烧录前：电脑准备与记录（两种连接共用）

打开 **Windows PowerShell**。下面的代码在 PowerShell 执行；后文标记 `sh` 的代码在板端终端执行。

### 3.1 开始记录、验证本地包

```powershell
Set-Location 'D:\code\Scoliosis\Luckfox\调试\记录\single-bundle-20261002'
$Release = 'instrument-v3.3.0-20261002-results-bundle1'
$Bundle = Join-Path (Get-Location) "$Release.tar.gz"
$Expected = 'd6eff1c88504d12a951c40b30adea719d9deb1dac714de9a9ee1cea996fbbdbf'
$Run = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogDir = Join-Path (Get-Location) "deploy-$Run"
New-Item -ItemType Directory -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir '电脑操作全过程.txt')
Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
$Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Bundle).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw '本地包校验不一致，停止。' }
"包校验通过：$Actual"
$Remote = "/tmp/scoliosis-$Run"
"板端解包后路径：$Remote/$Release"
```

保留 PowerShell 窗口和这些变量。后面的步骤使用同一窗口。原生命令报错或返回非零时，先排错，不跳过继续执行。

### 3.2 先停业务

在上位机退出设备诊断，停止拍摄并等待录像收尾、待传上传结束，关闭上位机。首次安装的空板没有这些业务。

此处必须人工确认；安装脚本的 `--idle-confirmed` 参数就是对这项检查的确认。它不能自行判断电脑是否仍有业务需求，也不应靠强杀掩盖录制或上传中的问题。

## 4. 方法 A：USB / ADB（推荐第一次操作使用）

只需接 USB 数据线，不要求先连 Wi-Fi。

### 4.1 找板卡，核对身份

```powershell
adb devices -l
$Serial = '替换为列表中目标板的实际序列号'
adb -s $Serial shell 'uname -m; cat /proc/device-tree/model; cat /etc/os-release; df -k /tmp /opt'
if ($LASTEXITCODE -ne 0) { throw '无法读取目标板，停止。' }
```

应看到 `armv7l`、`Luckfox Pico Zero` 和 Buildroot。USB product 显示 Nexus_4 不代表真是手机；以板端型号与序列号核对。多板连接时始终保留 `-s $Serial`。没有 `device`、显示 `offline` 或设备消失时先恢复连接。

### 4.2 保存升级前证据，再传一个文件

```powershell
adb -s $Serial shell 'date -u; uname -a; cat /proc/device-tree/serial-number; df -k / /tmp /opt; ip -4 addr show; ps; if [ -f /opt/instrument/bin/instrument_app ]; then /opt/instrument/bin/instrument_app --version; sha256sum /opt/instrument/bin/instrument_app; else echo APP_NOT_INSTALLED; fi' |
    Out-File -Encoding utf8 (Join-Path $LogDir '板端-升级前.txt')
if ($LASTEXITCODE -ne 0) { throw '升级前记录失败，停止。' }

adb -s $Serial shell "mkdir '$Remote'"
if ($LASTEXITCODE -ne 0) { throw '创建本次临时目录失败，停止。' }
adb -s $Serial push "$Bundle" "$Remote/$Release.tar.gz"
if ($LASTEXITCODE -ne 0) { throw '上传失败，停止。' }

$RemoteHash = adb -s $Serial shell "sha256sum '$Remote/$Release.tar.gz'"
if ($LASTEXITCODE -ne 0) { throw '板端校验命令失败，停止。' }
$RemoteHash
if (($RemoteHash -join ' ') -notmatch $Expected) { throw '板端包 SHA256 不一致，停止。' }

adb -s $Serial shell "tar -xzf '$Remote/$Release.tar.gz' -C '$Remote' && sh '$Remote/$Release/deploy/install_bundle.sh' --check"
if ($LASTEXITCODE -ne 0) { throw '解包或内部文件校验失败，停止。' }
```

看到所有 `OK` 和 `CHECK_OK` 后继续。此时只上传、解包、校验，没有安装或重启。

```powershell
"下一步在板端设置 PKG=$Remote/$Release"
adb -s $Serial shell
```

进入板端后继续第 6 节。记住刚才显示的 PKG 路径。

## 5. 方法 B：Wi-Fi / SSH + SCP

A 和 B **选一个**，不用把两套都做一遍。SSH 要求板卡已连网络、电脑和板在同一可达网段，且 SSH 服务正常。

### 5.1 确认真实 IP 和主机身份

先用 ADB 的 `ip -4 addr show`、路由器 DHCP 列表，或已有发现工具取得 IP。`192.168.101.3` 只是此前地址，DHCP 会改变；不要盲用。若需要项目已有的发现工具，运行：

```powershell
Set-Location 'D:\code\Scoliosis\Luckfox'
python '调试\工具\Python中间层\discover_ssh.py' --bind 192.168.101.2 --bind 192.168.0.20 --ssh
```

两个 bind 地址应改为电脑实际网卡地址。该工具用于发现/登录，不是安装器。返回本教程第 3 节的包目录后再传输。

```powershell
$BoardIp = '替换为实际板卡IP'
ssh "root@$BoardIp" 'uname -m; cat /proc/device-tree/model; cat /etc/os-release; df -k /tmp /opt'
if ($LASTEXITCODE -ne 0) { throw 'SSH 未登录成功，停止。' }
```

密码在交互提示中输入，不写进命令、教程、日志或脚本。首次连接核对主机密钥；如果出现密钥变化提示，先确认是否换板/重装，不关闭校验来绕过。

### 5.2 留前记录、一次传包、校验

继续用第 3 节初始化的变量；当前目录恢复为包目录。

```powershell
Set-Location 'D:\code\Scoliosis\Luckfox\调试\记录\single-bundle-20261002'
ssh "root@$BoardIp" 'date -u; uname -a; cat /proc/device-tree/serial-number; df -k / /tmp /opt; ip -4 addr show; ps; if [ -f /opt/instrument/bin/instrument_app ]; then /opt/instrument/bin/instrument_app --version; sha256sum /opt/instrument/bin/instrument_app; else echo APP_NOT_INSTALLED; fi' |
    Out-File -Encoding utf8 (Join-Path $LogDir '板端-升级前.txt')
if ($LASTEXITCODE -ne 0) { throw '升级前记录失败，停止。' }

ssh "root@$BoardIp" "mkdir '$Remote'"
if ($LASTEXITCODE -ne 0) { throw '创建临时目录失败，停止。' }
scp -O "./$Release.tar.gz" "root@${BoardIp}:$Remote/"
if ($LASTEXITCODE -ne 0) { throw 'SCP 上传失败，停止。' }

$RemoteHash = ssh "root@$BoardIp" "sha256sum '$Remote/$Release.tar.gz'"
if ($LASTEXITCODE -ne 0) { throw '板端校验命令失败，停止。' }
$RemoteHash
if (($RemoteHash -join ' ') -notmatch $Expected) { throw '板端包 SHA256 不一致，停止。' }

ssh "root@$BoardIp" "tar -xzf '$Remote/$Release.tar.gz' -C '$Remote' && sh '$Remote/$Release/deploy/install_bundle.sh' --check"
if ($LASTEXITCODE -ne 0) { throw '解包或内部文件校验失败，停止。' }

"下一步在板端设置 PKG=$Remote/$Release"
ssh "root@$BoardIp"
```

`scp -O` 使用传统 SCP 协议，以兼容缺少 SFTP 子系统的板端；`-O` 是大写字母 O。包从当前目录传输，也避免 Windows 盘符冒号被解释为远端路径。

进入板端后继续第 6 节。

## 6. 板端安装：前记录、配置、停服务、备份、安装

### 6.1 设置当前包路径，建立持久前记录

**以下代码在板端 sh 执行，不在 PowerShell 执行。** 将 PKG 的时间部分改成第 4 或 5 节实际显示的值。

```sh
PKG=/tmp/scoliosis-替换为本次Run/instrument-v3.3.0-20261002-results-bundle1
test -f "$PKG/SHA256SUMS" && echo PKG_OK
```

必须先看到 PKG_OK。再执行：

```sh
RUN=$(date -u +%Y%m%dT%H%M%SZ)-$$
PRE=/userdata/deploy-records/$RUN
mkdir -p "$PRE"
chmod 700 "$PRE"
{
    date -u
    uname -a
    df -k / /opt /tmp
    ps
    if [ -f /opt/instrument/bin/instrument_app ]; then
        /opt/instrument/bin/instrument_app --version
        sha256sum /opt/instrument/bin/instrument_app
    else
        echo APP_NOT_INSTALLED
    fi
} > "$PRE/before.txt"
cp /RkLunch.sh "$PRE/RkLunch.before.sh"
if [ -f /userdata/rkipc.ini ]; then cp /userdata/rkipc.ini "$PRE/rkipc.before.ini"; fi
if [ -f /opt/instrument/config.json ]; then
    cp /opt/instrument/config.json "$PRE/config-before.json"
    chmod 600 "$PRE/config-before.json"
fi
echo "升级前持久记录：$PRE"
sync
```

板端 RTC 未校时可能日期不准，结合电脑 $Run 和全过程日志识别；这里追加 PID 避免同一次启动中目录重名。配置备份只自己留存，不发送给别人。

### 6.2 已有应用：保留配置。首次安装：先人工初始化

先判断：

```sh
test -f /opt/instrument/config.json && echo CONFIG_EXISTS
```

看到 CONFIG_EXISTS 就跳过下面的初始化段。

**仅在首次安装、确定 config.json 不存在时**：

```sh
mkdir -p /opt/instrument
if [ ! -e /opt/instrument/config.json ]; then
    cp "$PKG/config.example.json" /opt/instrument/config.json
    chmod 600 /opt/instrument/config.json
fi
vi /opt/instrument/config.json
```

vi 按 i 进入编辑，Esc 后输入 `:wq` 保存退出。至少核对：

- `device_id`：为这台设备分配唯一 ID；只有原 CAM-000123 才保留 CAM-000123，其他板不要复制同一身份。
- `wifi_ssid`：填写实际使用的 2.4 GHz SSID。示例值是旧测试网络，不自动替你改成当前网络。
- `pc_base_url`：填上位机实际地址和监听端口；不能用 127.0.0.1，也不要照搬旧电脑 IP。
- `audio.volume`：范围 0–30，初次可设 10。
- `capture`：与真实 RKiPC 摄像头配置匹配；本项目使用 1280×1080、H.265、MP4。

**config.json 中的 SSID 不会配置无线密码或自动建立 Wi-Fi。** 新板需先按现场网络完成 wpa_supplicant 配置和联网；见项目 [Wi-Fi 记录](../../基础信息/WiFi.md)。不要把已存在的 Wi-Fi 配置覆盖成示例。

首次安装还需核对 `/userdata/rkipc.ini` 的摄像头型号、编码器和 `storage.mount_path=/`，应用等待的是 `/video0`。本包不覆盖相机 ini；出厂默认参数不能直接当成已验证的业务参数。相机 ini 的修改要在停止 RKiPC 后进行，并保留刚才的备份。

### 6.3 平稳停服务，不强杀正在收尾的业务

确保第 3.2 节的业务停止后，执行：

```sh
if pidof instrument_app >/dev/null; then killall -TERM instrument_app; fi
sleep 3
pidof instrument_app
```

最后一条应没有 PID；有 PID 就停止安装、查业务日志，不执行 kill -9 硬闯。

然后停止 RKiPC：

```sh
if pidof rkipc >/dev/null; then killall -TERM rkipc; fi
sleep 3
pidof rkipc
pidof aplay
```

都应没有 PID。若停止超时先定位，不升级。若本来没运行，pidof 非零表示没有进程，不是升级失败。

### 6.4 核对启动脚本，特别是自定义 USB/UVC

```sh
diff -u /RkLunch.sh "$PKG/deploy/RkLunch.sh"
```

无差异可以直接安装。有差异时先检查：本包加入本项目 init 目录执行、相机 JPEG 配置及 scoped LD_PRELOAD，且保留此前本项目的原厂启动逻辑。**当前系统如有 USB/UVC、网卡或其他启动定制，直接替换会丢掉这些定制。** 此时先合并/重做适配包，不使用后面的替换参数强行覆盖。

如果确认差异只是本项目已核对的启动改造，并接受用包内脚本替换，才使用第二条安装命令。

### 6.5 执行安装（二选一）

启动脚本一致：

```sh
sh "$PKG/deploy/install_bundle.sh" --install --idle-confirmed
echo "安装退出码=$?"
```

已核对并接受启动脚本替换：

```sh
sh "$PKG/deploy/install_bundle.sh" --install --idle-confirmed --replace-startup
echo "安装退出码=$?"
```

脚本会打印类似：

```text
RECORD=/opt/instrument/backups/bundle-20261002T120000Z-1234
```

**抄下这个路径**，下面用 RECORD 表示，必须填本次实际路径：

```sh
RECORD=/opt/instrument/backups/bundle-替换为刚才实际值
cat "$RECORD/result.txt"
tail -n 30 "$RECORD/install.log"
```

必须同时看到 `exit_code=0` 和 `INSTALL_OK`。若未打印 RECORD，说明前置检查尚未通过，查看终端报错；不要取历史备份冒充本次安装记录。

安装脚本自动完成：

1. 检查包内文件 SHA-256、板型、uClibc、现场 config、程序版本、服务已停和 writing 目录为空。
2. 保存前版本、进程、磁盘、配置证据、旧文件哈希和旧文件恢复 tar。
3. 对新文件逐个临时复制、校验和改名替换，保留安装映射。
4. 核对所有目标哈希及 config 未被改写，保存后记录和退出码。
5. **不自动启动服务、不自动重启**；让你先看结果，失败时业务保持停止，方便回滚。

它不复制 state、pairing、capture/pending、Wi-Fi 或相机 ini；旧配置备份只作证据，回滚不拿它覆盖当前身份。失败中途可能已有部分文件替换，必须按记录回滚；多文件升级不是整包断电原子事务。安装期间保持稳定供电。

### 6.6 安装成功后再重启

在日志确认成功后：

```sh
sync
reboot
```

会断开 ADB/SSH，这是正常的。回到电脑待设备正常启动后重新列出 ADB 设备或重新确认 DHCP 地址。不要因几秒内连接不上而重复安装。

## 7. 烧录后：版本、文件、运行与人工验收记录

### 7.1 ADB 获取重启后证据

回到原 PowerShell 窗口，重新确认 $Serial。这里的 $Record 替换为第 6.5 节记录路径：

```powershell
adb devices -l
$Record = '/opt/instrument/backups/bundle-替换为实际值'
adb -s $Serial shell "date -u; /opt/instrument/bin/instrument_app --version; sha256sum /opt/instrument/bin/instrument_app /opt/instrument/bin/luckfox_mux_adapter.so; ps; df -k /opt; cat /tmp/button-input-start.log; sha256sum -c '$Record/after-SHA256SUMS'" |
    Out-File -Encoding utf8 (Join-Path $LogDir '板端-重启后.txt')
if ($LASTEXITCODE -ne 0) { throw '重启后检查存在失败，查看日志。' }

adb -s $Serial pull "$Record" "$LogDir"
if ($LASTEXITCODE -ne 0) { throw '安装记录导出失败。' }
adb -s $Serial shell 'logread | tail -n 120; dmesg | tail -n 80' |
    Out-File -Encoding utf8 (Join-Path $LogDir '板端-运行日志.txt')
Stop-Transcript
```

初次启动 after-SHA256SUMS 检查的是安装目标，业务 state/version 由应用另行生成；要同时核对真实进程。配置和 rollback-files.tar 可能含现场资料，日志目录自己保留。

### 7.2 SSH 获取重启后证据

同样把 $Record 替换为实际路径，并使用重启后的真实 $BoardIp：

```powershell
$Record = '/opt/instrument/backups/bundle-替换为实际值'
ssh "root@$BoardIp" "date -u; /opt/instrument/bin/instrument_app --version; sha256sum /opt/instrument/bin/instrument_app /opt/instrument/bin/luckfox_mux_adapter.so; ps; df -k /opt; cat /tmp/button-input-start.log; sha256sum -c '$Record/after-SHA256SUMS'" |
    Out-File -Encoding utf8 (Join-Path $LogDir '板端-重启后.txt')
if ($LASTEXITCODE -ne 0) { throw '重启后检查存在失败，查看日志。' }

scp -O -r "root@${BoardIp}:$Record" "$LogDir"
if ($LASTEXITCODE -ne 0) { throw '安装记录导出失败。' }
ssh "root@$BoardIp" 'logread | tail -n 120; dmesg | tail -n 80' |
    Out-File -Encoding utf8 (Join-Path $LogDir '板端-运行日志.txt')
Stop-Transcript
```

这里下载的是记录/回滚目录，不是再次上传多个程序。若需电脑同时保存第 6.1 节相机和启动配置前备份，把当时 PRE 路径也用 adb pull 或 scp -O -r 拉回。

### 7.3 如何判定成功

| 项目 | 应看到 / 应完成 |
|---|---|
| 文件安装 | result.txt 为 exit_code=0；install.log 有 INSTALL_OK |
| 文件一致 | after-SHA256SUMS 全部 OK |
| 程序版本 | --version 为 3.3.0；程序哈希为第 2 节值 |
| 持久启动 | 重启后 ps 中有 instrument_app 和 rkipc |
| GPIO | button-input-start.log 无失败；实体键逐个按下释放后电平正确 |
| 库注入 | RKiPC 日志无加载错误；录像通路可工作 |
| 网络/配对 | 能发现正确设备，新板按正常流程配对；不串到另一台 |
| 音频 | 上位机试听、配对及拍摄提示实际可听见，没有持续音频 busy |
| 录像/上传 | 使用测试学生录一段，电脑收到视频、时长正常、能播放并登记 |
| 数据保留 | 原待传、配对、学生关联和删除凭据符合预期，不被旧备份覆盖 |
| 冷启动 | 安全停业务后断电上电，仍能启动、发现和拍摄 |

把下面模板保存为电脑本次日志目录中的 `验收记录.md`：

```markdown
# 单文件部署验收
- 电脑时间：
- 操作者：
- 板型 / 板卡序列号 / device_id：
- ADB 序列号或 SSH IP：
- 安装包文件名 / SHA256：
- 升级前版本 / 程序 SHA256：
- 本次板端 RECORD 和 PRE 路径：
- 升级后版本 / 程序 SHA256：
- 安装 / 重启 / 哈希检查结果：
- 实体按键：
- 声音试听：
- 测试录像 capture_id / 时长 / 上传 / 播放：
- 旧待传、学生关联、配对和删除凭据保留：
- 断电重启：
- 异常、处理方式及未完成项：
- 是否回滚 / 回滚后版本：
```

没有实际做的项目填写“未验证”，不要自动写通过。若拍摄失败先看相机/内核日志，不凭下载或进程存在判定硬件验收完成。

## 8. 回滚：只恢复这次替换的程序文件，保留业务数据

### 8.1 已有应用升级后的回滚

先停止上位机业务，再按第 6.3 节停止 instrument_app、rkipc。在板端填本次 RECORD：

```sh
RECORD=/opt/instrument/backups/bundle-替换为实际值
test -f "$RECORD/rollback-files.tar" && echo BACKUP_EXISTS
tar -tf "$RECORD/rollback-files.tar"
cat "$RECORD/existing-files.txt"
cat "$RECORD/new-files.txt"
```

确认这个 tar 由本次安装脚本生成，内容只有安装映射中原先存在的程序/声音/启动文件，**没有 config、state、配对、Wi-Fi 或视频**，再恢复：

```sh
tar -xf "$RECORD/rollback-files.tar" -C /
sha256sum -c "$RECORD/before-SHA256SUMS"
sync
```

全部 OK 后，记录回滚结果。若 RkLunch 曾在首次重启时改过相机 JPEG 参数，需要另外检查第 6.1 节相机配置前备份；先停 RKiPC，再按实际需要仅恢复那个 ini。不要恢复旧 config/pairing 覆盖新的电脑归属。

`new-files.txt` 中列出的文件没有旧版本，tar 不会删掉它们；应逐项人工判断。特别是新加的自启动脚本可能仍启动新组件。需要撤销该文件时，逐个改名停用，例如仅对本次新增的 S80instrument：

```sh
mv /oem/usr/etc/init.d/S80instrument /opt/instrument/backups/S80instrument.disabled-本次唯一编号
```

停用文件放在 init 目录外，避免仍匹配 `S??*`。不要递归删除目录，不删除待传视频。完成必要的新文件停用后才重启：

```sh
sync
reboot
```

按第 7 节再保存回滚后的版本和人工结果。

### 8.2 首次安装的撤销

新板没有旧 instrument_app，不能声称“回滚到旧应用”。先停止业务和两个进程，恢复本次保存的旧 /RkLunch.sh，逐个把本次新增的 S79buttons、S80instrument 移到备份目录外的明确停用位置。保留 /opt/instrument 中配置、运行数据和安装记录，重启后核对旧系统启动行为。

回滚不会恢复用户以前主动删除的视频，也不会自动兼容旧版本不认识的新删除凭据；带有新业务数据的设备不要直接用更老应用联网重传。

## 9. 以后怎样生成一个新的包（开发者 / WSL）

固件所有写入和构建继续在 Linux 项目中做。Windows PowerShell：

```powershell
wsl -d Luckfox-Ubuntu-22.04
```

进入 WSL 后：

```bash
cd /home/guanjx/luckfox/Scoliosis
git status --short
# 若业务程序有变更：先运行相应检查，并用 package_image.sh 生成新的不可覆盖版本目录。
# 已有发布目录可直接包装，本命令不会重新编译应用：
./scripts/package_bundle.sh v3.3.0-20261002-results v3.3.0-20261002-results-bundle2
python3 tests/test_bundle.py bundles/v3.3.0-20261002-results-bundle2/instrument-v3.3.0-20261002-results-bundle2.tar.gz
cat bundles/v3.3.0-20261002-results-bundle2/SHA256SUMS
```

第二个参数是新部署包目录名；上面的 bundle2 仅演示将来新包，本轮没生成它。输出目录已存在就拒绝覆盖，换一个新编号。业务版本变化时使用相应实际发布目录，不把旧发布目录改名冒充新程序。

打包脚本：`scripts/package_bundle.sh`。安装脚本：`deploy/install_bundle.sh`。自检：`tests/test_bundle.py`。这三项及 GPIO 文件保存在 WSL 源码；本轮工作区保留待审阅变更，没有自动 Git 提交或推送。

## 10. 如果你说的“烧录文件”是整机 update.img

这也是可行的：从对应 Pico Zero 系统 SDK 的 rootfs 集成应用、声音、适配库、init 和正确相机默认配置，再按官方 SDK 打包出一个 `update.img`。适合量产新板或恢复系统。

它需要对应的完整 SDK、板型/分区/相机配置和实机验收。**本次生成的是应用部署包，不是可交给 SocToolKit 的 update.img；改扩展名也不能变成系统镜像。**

整机流程是：先备份现有数据 → 取得和本板匹配、已校验的镜像 → Windows SocToolKit 选择 RV1106 → 按住 BOOT 接 USB，确认 MaskRom/Loader → Firmware 选择 update.img → Upgrade → 明确成功后重启并重新验收。系统重刷可能影响应用数据和定制配置，不能沿用“应用升级保留全部数据”的假设。[官方 eMMC 镜像烧录教程](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Getting-Started/eMMC-Models/)

ADB/SSH 在这里可用于事前备份和运行系统管理；MaskRom 烧录本身使用 Rockchip 烧录工具，不是 adb push。本轮没有重新打包或重刷系统。

## 11. 常见卡点

| 提示/问题 | 处理 |
|---|---|
| ADB 列表为空或序列号变化 | 重新确认数据线/供电/USB模式，按实际新序列号连接；不沿用旧 -s |
| --check 出现 FAILED | 停止；核对电脑和板端外层 SHA256，重新传可信原包 |
| Missing local config.json | 仅首次安装创建并人工编辑；已有板先找正确配置路径 |
| Still running | 当前服务未停，不用强杀跳过；先处理拍摄、收尾和上传 |
| writing 非空 | 检查未收尾录像，保留文件，不为安装清空目录 |
| RkLunch.sh differs | diff 核对；自定义 UVC/网络脚本先合并，非自定义差异经确认才加 --replace-startup |
| Insufficient disk space | 不安装；查看 df，人工选择明确的可清理单文件，保留业务数据 |
| SCP 报 SFTP 错误 | 用文中的 scp -O；不需要给板端新装服务 |
| 安装成功但重启无应用 | 查看 S79/S80 权限、RkLunch init 调用、config、程序加载错误和系统日志 |
| 声音不响 | 看 aplay/amixer、音频占用及实际喇叭；哈希一致不能证明可听 |
| 有 rkipc 但录像失败 | 查 rkipc.ini、/video0、mux 日志及内核 MIPI 错误，再定位，不重复刷系统 |
| 中断或断电 | 保存 install.log / result.txt；核对目标哈希，按本次 rollback-files.tar 恢复后再启动 |
