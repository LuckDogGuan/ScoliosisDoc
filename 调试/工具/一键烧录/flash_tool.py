"""One-click application installation; official packages stay in WSL."""
from __future__ import annotations

import argparse
import configparser
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid

RELEASES = Path(r"\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\releases")
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
HOME = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
UDP_HASH = "6f653c5f0f064c169d4b640e5284674f450a67b7181e6f8e300c8ed7607d35ca"
# Reviewed 3.3.0 and 3.3.3 startup scripts; unknown custom startup is refused.
REVIEWED_STARTUPS = {"a27c9f86c1388d8327f117a5c50dc50e197291c79b4e6f1c6936f681feb77d56",
                     "aa436305bfa8fd5c68b72e38d7f5e4b4422ec8a1b5443a418046f1757493fc57",
                     "bfbacb8a988ad6ea3e65646652d28e29b35ecb091b0dbf313f9fd8ead006a946"}
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def command(args, timeout=60):
    result = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or
                           result.stdout.decode(errors="replace").strip() or "设备操作失败")
    return result.stdout.decode(errors="replace").replace("\r", "").replace("\x00", "").strip()


def adb_path():
    candidates = [ASSETS / "adb/adb.exe", Path(r"D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe")]
    return str(next((p for p in candidates if p.is_file()), Path("adb.exe")))


def usb_devices():
    text = command([adb_path(), "devices", "-l"], 15)
    ps = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    physical = command([str(ps), "-NoProfile", "-Command",
                        "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\VID_*' } | "
                        "ForEach-Object { ($_.InstanceId -split '\\\\')[-1] }"], 25)
    serials = {s.lower() for s in physical.splitlines()}
    return [(p[0], p[1]) for line in text.splitlines()
            if len(p := line.split()) >= 2 and p[0].lower() in serials]


def choose_serial(devices, selected=None):
    if not devices:
        raise RuntimeError("没有连接设备，请接好 USB 和驱动后重试")
    if selected is None and len(devices) != 1:
        raise RuntimeError("连接了多台设备，请选择本次烧录的设备")
    serial = selected or devices[0][0]
    if (serial, "device") not in devices or not re.fullmatch(r"[A-Za-z0-9_-]+", serial):
        raise RuntimeError("设备未授权或已离线，请检查 USB 连接")
    return serial


def latest_package(releases=RELEASES):
    if not releases.is_dir():
        raise RuntimeError("正式包目录不可用，请启动 Luckfox-Ubuntu-22.04 后重试")
    versions = [p for p in releases.iterdir() if p.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+", p.name)]
    if not versions:
        raise RuntimeError("没有找到正式烧录包")
    folder = max(versions, key=lambda p: tuple(map(int, p.name.split("."))))
    result = read_package(folder / f"instrument-v{folder.name}.tar.gz")
    if result["version"] != folder.name:
        raise RuntimeError("目录版本与包内版本不一致")
    return result


def read_package(path):
    package = Path(path)
    package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
    outer = package.parent / "SHA256SUMS"
    if outer.is_file():
        checks = dict((name.lstrip("*"), value) for line in outer.read_text(encoding="utf-8").splitlines()
                      if line.strip() for value, name in [line.split(maxsplit=1)])
        if checks.get(package.name) != package_hash:
            raise RuntimeError("所选压缩包的外层校验失败")
    with tarfile.open(package) as archive:
        roots = {PurePosixPath(item.name).parts[0] for item in archive.getmembers() if PurePosixPath(item.name).parts}
        if len(roots) != 1:
            raise RuntimeError("请选择完整的仪器应用烧录包")
        prefix = roots.pop()
        for item in archive.getmembers():
            parts = PurePosixPath(item.name).parts
            if not parts or parts[0] != prefix or ".." in parts or item.name.startswith("/") or not (item.isfile() or item.isdir()):
                raise RuntimeError("正式包包含不安全路径")
        if not re.fullmatch(r"instrument-v[A-Za-z0-9_.-]+", prefix):
            raise RuntimeError("请选择仪器应用烧录包")
        version = archive.extractfile(prefix + "/VERSION").read().decode().strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise RuntimeError("包内版本无效")
        for line in archive.extractfile(prefix + "/SHA256SUMS").read().decode().splitlines():
            expected, name = line.split(maxsplit=1)
            content = archive.extractfile(prefix + "/" + name.removeprefix("./"))
            if not re.fullmatch(r"[0-9a-f]{64}", expected) or content is None or hashlib.sha256(content.read()).hexdigest() != expected:
                raise RuntimeError("压缩包内文件校验失败：" + name)
        if not archive.getmember(prefix + "/deploy/install_bundle.sh").isfile():
            raise RuntimeError("此历史包不含安装器，不能直接烧录")
        app_hash = hashlib.sha256(archive.extractfile(prefix + "/instrument_app").read()).hexdigest()
        startup_hash = hashlib.sha256(archive.extractfile(prefix + "/deploy/RkLunch.sh").read()).hexdigest()
        config = json.loads(archive.extractfile(prefix + "/config.example.json").read())
        mapping = {"instrument_app": "/opt/instrument/bin/instrument_app", "luckfox_mux_adapter.so": "/opt/instrument/bin/luckfox_mux_adapter.so",
                   "deploy/RkLunch.sh": "/RkLunch.sh", "deploy/S80instrument": "/oem/usr/etc/init.d/S80instrument",
                   "VERSION": "/opt/instrument/installed-version", "BUILD.txt": "/opt/instrument/installed-build.txt",
                   "deploy/TZ": "/etc/TZ", "deploy/wpa_supplicant.default.conf": "/opt/instrument/defaults/wpa_supplicant.conf"}
        installed_hashes = {}
        for line in archive.extractfile(prefix + "/SHA256SUMS").read().decode().splitlines():
            digest, name = line.split(maxsplit=1)
            name = name.removeprefix("./")
            destination = mapping.get(name, "/opt/instrument/" + name if name.startswith("sounds/") and name.endswith(".wav") else None)
            if destination:
                installed_hashes[destination] = digest
    return dict(path=package, version=version, prefix=prefix, sha256=package_hash,
                app_hash=app_hash, startup_hash=startup_hash, config=config, installed_hashes=installed_hashes)


def validate_idle(state):
    needed = ("phase", "gate_enabled", "capture_id", "uploading_capture_id", "audio_busy", "diagnostics_active")
    if not all(k in state for k in needed):
        raise RuntimeError("无法核实仪器状态，停止烧录")
    if state["phase"] not in ("idle", "paired") or any(state[k] for k in needed[1:]) or state.get("pair_window_remaining_ms", 0):
        raise RuntimeError("仪器正在使用，请结束拍摄、上传或设备测试后重试")


def ini_values(text):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read_string(text)
    return {s: dict(parser[s]) for s in parser.sections()}


class Installer:
    def __init__(self, serial, notify=lambda message: None):
        self.serial, self.notify = serial, notify
        self.report = HOME / "记录" / (time.strftime("%Y%m%d-%H%M%S") + "-" + serial + "-" + uuid.uuid4().hex[:6])
        self.report.mkdir(parents=True)
        self.remote = "/tmp/instrument-flash-" + uuid.uuid4().hex[:12]
        self.staging = Path(tempfile.mkdtemp(prefix="instrument-flash-"))
        if not str(self.staging).isascii():
            raise RuntimeError("临时目录包含中文，请使用英文 Windows 用户目录")
        self.device_id = ""
        self.stopped = False

    def record(self, **data):
        with (self.report / "operations.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), **data), ensure_ascii=False) + "\n")

    def adb(self, *args, timeout=60):
        try:
            text = command([adb_path(), "-s", self.serial, *args], timeout)
            self.record(args=args, output=text)
            return text
        except Exception as error:
            self.record(args=args, error=str(error))
            raise

    def shell(self, script, timeout=60):
        # Old board ADB reports success even when a remote command failed.
        wrapped = "sh -c " + shlex.quote(script) + "; flash_code=$?; printf '\\n__FLASH_EXIT__=%s\\n' \"$flash_code\""
        text = self.adb("shell", wrapped, timeout=timeout)
        body, marker, code = text.rpartition("__FLASH_EXIT__=")
        if not marker or code != "0":
            raise RuntimeError(body or text or "板端命令失败")
        return body.strip()

    def push(self, path, name):
        # Legacy Windows ADB needs ASCII local paths; never mirror a formal package permanently.
        staged = self.staging / name
        shutil.copyfile(path, staged)
        self.adb("push", str(staged), self.remote + "/" + name)

    def hello(self):
        packet = dict(version=3, op="hello_query", host_id="usb-flash-tool", device_id=self.device_id,
                      sequence=0, nonce=uuid.uuid4().hex)
        state = json.loads(self.shell(self.remote + "/udp_query " + shlex.quote(json.dumps(packet, separators=(",", ":")))))
        if not state.get("ok") or state.get("op") != "hello_reply" or any(state.get(k) != packet[k] for k in ("version", "host_id", "device_id", "sequence", "nonce")):
            raise RuntimeError("设备状态身份不匹配")
        return state

    def idle(self, wait_startup_audio=False):
        deadline = time.monotonic() + 15
        while True:
            state = self.hello()
            if not wait_startup_audio or not state.get("audio_busy"):
                validate_idle(state)
                break
            # Only post-reboot prompts may finish; every business guard still applies.
            validate_idle(dict(state, audio_busy=False))
            if time.monotonic() >= deadline:
                raise RuntimeError("启动播报15秒内未结束，停止校验；请查看记录")
            time.sleep(0.25)
        if json.loads(self.shell("if [ -f /opt/instrument/state/active-v3.json ]; then cat /opt/instrument/state/active-v3.json; else echo '{}'; fi")) or self.shell("ls -A /opt/instrument/capture/writing"):
            raise RuntimeError("存在未结束的拍摄文件，停止烧录")
        return state

    def preflight(self, package):
        self.notify("检查设备和烧录包…")
        if self.shell("cat /proc/device-tree/serial-number") != self.serial:
            raise RuntimeError("设备序列号不一致")
        if self.shell("cat /proc/device-tree/model") != "Luckfox Pico Zero" or self.shell("uname -m") != "armv7l":
            raise RuntimeError("当前工具仅支持 Luckfox Pico Zero")
        config_text = self.shell("if [ -f /opt/instrument/config.json ]; then cat /opt/instrument/config.json; fi")
        self.fresh = not config_text
        if self.fresh:
            if self.shell("if [ -d /opt/instrument ]; then echo PARTIAL; fi; pidof instrument_app rkipc camera_test aplay rk_mpi_ao_test || true"):
                raise RuntimeError("已有不完整安装或运行任务，请先检查记录")
            config = dict(package["config"], device_id="CAM-" + self.serial)
        else:
            config = json.loads(config_text)
        self.device_id = config.get("device_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,95}", self.device_id):
            raise RuntimeError("仪器身份配置无效")
        startup = self.shell("sha256sum /RkLunch.sh").split()[0]
        if startup != package["startup_hash"] and startup not in REVIEWED_STARTUPS:
            raise RuntimeError("设备有未知启动配置，停止烧录；请先核对启动脚本")
        helper = ASSETS / "payload/udp_query"
        if hashlib.sha256(helper.read_bytes()).hexdigest() != UDP_HASH:
            raise RuntimeError("内置检测组件校验失败")
        self.shell("mkdir " + self.remote)
        self.push(helper, "udp_query")
        self.shell("chmod 755 " + self.remote + "/udp_query")
        self.initial_config = config
        self.before = None if self.fresh else self.idle()
        self.preserved = self.shell("set -e; for f in /opt/instrument/config.json "
            "/opt/instrument/state/pair-v3.json /etc/wpa_supplicant.conf /userdata/wpa_supplicant.conf; do "
            "if [ -f \"$f\" ]; then if ! grep -q 'ssid=\"Your SSID\"' \"$f\"; then sha256sum \"$f\"; fi; fi; done")
        self.camera = ini_values(self.shell("if [ -f /userdata/rkipc.ini ]; then cat /userdata/rkipc.ini; fi"))
        self.has_camera = bool(self.shell("for f in /sys/class/video4linux/v4l-subdev*/name; do cat \"$f\"; done | grep -Ei 'mia1321|mis0400|isg1321' || true"))
        self.record(preflight="PASS", serial=self.serial, device_id=self.device_id, package=str(package["path"]), version=package["version"])

    def check_preserved(self):
        for line in self.preserved.splitlines():
            digest, path = line.split(maxsplit=1)
            if self.shell("sha256sum " + shlex.quote(path)).split()[0] != digest:
                raise RuntimeError("现场配置或配对信息改变：" + path)

    def verify(self, package, wait_startup_audio=False):
        if self.shell("cat /proc/device-tree/serial-number") != self.serial or self.shell("/opt/instrument/bin/instrument_app --version") != package["version"]:
            raise RuntimeError("重启后的设备或版本不一致")
        if self.shell("sha256sum /opt/instrument/bin/instrument_app").split()[0] != package["app_hash"]:
            raise RuntimeError("程序文件校验失败")
        for path, digest in package["installed_hashes"].items():
            if self.shell("sha256sum " + shlex.quote(path)).split()[0] != digest:
                raise RuntimeError("安装文件校验失败：" + path)
        self.shell("pidof instrument_app")
        if self.has_camera:
            self.shell("set -e; pidof rkipc; test -S /var/tmp/rkipc")
        self.check_preserved()
        state = self.idle(wait_startup_audio=wait_startup_audio)
        actual = ini_values(self.shell("if [ -f /userdata/rkipc.ini ]; then cat /userdata/rkipc.ini; fi"))
        allowed = {("video.source", "enable_jpeg"): "1", ("video.jpeg", "enable_cycle_snapshot"): "0",
                   ("video.jpeg", "jpeg_qfactor"): "95", ("video.jpeg", "jpeg_buffer_size"): "4194304"}
        for section in (self.camera.keys() | actual.keys()) if self.camera else []:
            for key in self.camera.get(section, {}).keys() | actual.get(section, {}).keys():
                old, new = self.camera.get(section, {}).get(key), actual.get(section, {}).get(key)
                if old != new and new != allowed.get((section, key)):
                    raise RuntimeError("相机参数出现预期外变化：" + section + "/" + key)
        self.record(verification="PASS", state=state)
        return state

    def flash_install(self, package, force=False):
        self.preflight(package)
        if not self.fresh and not force and self.shell("/opt/instrument/bin/instrument_app --version") == package["version"]:
            self.verify(package)
            return "已是 " + package["version"] + "，校验通过"
        self.notify("传输并检查烧录包…")
        self.push(package["path"], "bundle.tar.gz")
        if self.shell("sha256sum " + self.remote + "/bundle.tar.gz").split()[0] != package["sha256"]:
            raise RuntimeError("传输文件校验失败")
        pkg = self.remote + "/" + package["prefix"]
        self.shell("set -e; cd " + self.remote + "; gzip -dc bundle.tar.gz > payload.tar; tar -xf payload.tar; sh " + pkg + "/deploy/install_bundle.sh --check")
        if self.fresh:
            self.shell("set -e; test ! -e /opt/instrument; mkdir -p /opt/instrument/state /opt/instrument/capture/writing; "
                       "printf %s " + shlex.quote(json.dumps(self.initial_config)) + " > /opt/instrument/config.json; "
                       + pkg + "/instrument_app --check-config /opt/instrument/config.json")
            self.record(initialized=True, config_created=True, device_id=self.device_id)
        else:
            self.idle()
        self.notify("备份并烧录，请勿拔线…")
        self.stopped = True
        self.shell("set -e; if pidof instrument_app >/dev/null; then kill -TERM $(pidof instrument_app); fi; "
            "if pidof rkipc >/dev/null; then kill -TERM $(pidof rkipc); fi; n=0; "
            "while pidof instrument_app rkipc aplay >/dev/null; do n=$((n+1)); [ \"$n\" -lt 40 ] || exit 2; sleep 1; done")
        output = self.shell("sh " + pkg + "/deploy/install_bundle.sh --install --idle-confirmed --replace-startup")
        match = re.search(r"RECORD=(/opt/instrument/backups/bundle-[A-Za-z0-9-]+)", output)
        if not match:
            raise RuntimeError("未取得板端安装记录")
        backup = match[1]
        if self.shell("cat " + backup + "/result.txt") != "exit_code=0":
            raise RuntimeError("安装失败，回退备份位于 " + backup)
        self.shell("sha256sum -c " + backup + "/after-SHA256SUMS")
        self.check_preserved()
        self.shell("tar -cf " + self.remote + "/rollback-audit.tar -C / " + backup.lstrip("/"))
        staged = self.staging / "rollback-audit.tar"
        self.adb("pull", self.remote + "/rollback-audit.tar", str(staged))
        with tarfile.open(staged) as audit:
            if not any(m.name.endswith("/rollback-files.tar") for m in audit.getmembers()):
                raise RuntimeError("回退备份导出不完整")
        shutil.copyfile(staged, self.report / staged.name)
        self.record(installation="PASS", backup=backup, backup_sha256=hashlib.sha256(staged.read_bytes()).hexdigest())
        self.notify("烧录完成，正在重启校验…")
        self.adb("shell", "sync; reboot")
        self.stopped = False
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            time.sleep(2)
            try:
                if self.shell("cat /proc/device-tree/serial-number", timeout=8) == self.serial and self.shell("pidof instrument_app", timeout=8):
                    break
            except (RuntimeError, subprocess.TimeoutExpired):
                continue
        else:
            raise RuntimeError("烧录完成，但重启连接未恢复；请检查供电和 USB，再查看记录")
        self.shell("mkdir -p " + self.remote)
        self.push(ASSETS / "payload/udp_query", "udp_query")
        self.shell("chmod 755 " + self.remote + "/udp_query")
        self.shell("sha256sum -c " + backup + "/after-SHA256SUMS")
        state = self.verify(package, wait_startup_audio=True)
        if self.before and state["boot_id"] == self.before["boot_id"]:
            raise RuntimeError("未确认新启动，查看烧录记录")
        return "烧录完成 · " + package["version"] + ("" if self.has_camera else "（未检测到摄像头）")

    def close(self):
        if self.stopped:
            try:
                self.shell("if ! pidof rkipc >/dev/null; then nohup env TZ=CST-8 LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so "
                    "/oem/usr/bin/rkipc -a /oem/usr/share/iqfiles >/tmp/flash-recovery-camera.log 2>&1 </dev/null & sleep 2; fi; "
                    "if ! pidof instrument_app >/dev/null; then nohup /opt/instrument/bin/instrument_app /opt/instrument/config.json "
                    ">/tmp/flash-recovery-app.log 2>&1 </dev/null & sleep 1; fi")
            except Exception as error:
                self.record(recovery_error=str(error))
        # Only these three known temporary files; no recursive cleanup.
        for name in ("udp_query", "bundle.tar.gz", "rollback-audit.tar"):
            (self.staging / name).unlink(missing_ok=True)
        self.staging.rmdir()


def wifi_saved():
    path = HOME / "wifi-devices.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def wifi_exchange(address, device_id, timeout=2, bind_address=None):
    packet = dict(version=3, op="hello_query", host_id="wifi-flash-tool", device_id=device_id,
                  sequence=0, nonce=uuid.uuid4().hex)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        if bind_address:
            udp.bind((bind_address, 0))
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.settimeout(timeout)
        udp.sendto(json.dumps(packet).encode(), (address, 37020))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            udp.settimeout(max(0.01, deadline - time.monotonic()))
            raw, peer = udp.recvfrom(8192)
            try:
                state = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if peer[1] != 37020 or (address != "255.255.255.255" and peer[0] != address):
                continue
            if isinstance(state, dict) and state.get("op") == "hello_reply" and state.get("ok") is True and all(
                    state.get(k) == packet[k] for k in ("version", "host_id", "device_id", "sequence", "nonce")):
                return dict(device_id=device_id, address=peer[0], state=state)
    raise RuntimeError("仪器 Wi-Fi 无响应，请确认同一局域网并重新连接")


def wifi_devices():
    # Saved identities remain discoverable after the physical pairing window closes.
    saved = wifi_saved()
    identities = set(saved)
    db = Path(os.environ.get("LOCALAPPDATA", ".")) / "ScoliosisScreening/screening.sqlite3"
    if db.is_file():
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as connection:
            row = connection.execute("SELECT payload FROM runtime_state WHERE key='lastWorkspace'").fetchone()
        if row:
            book = Path(row[0]) / "设备.json"
            if book.is_file():
                identities.update(json.loads(book.read_text(encoding="utf-8-sig")).get("paired", []))
    found = {}
    addresses = {r[4][0] for r in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    addresses = {ip for ip in addresses if not ip.startswith(("127.", "169.254.", "198.18."))}
    for bind in sorted(addresses):
        request = dict(version=2, op="discover", nonce=uuid.uuid4().hex, http_port=49159)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.bind((bind, 0))
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.sendto(json.dumps(request).encode(), ("255.255.255.255", 37020))
            deadline = time.monotonic() + 0.7
            while time.monotonic() < deadline:
                udp.settimeout(max(0.01, deadline - time.monotonic()))
                try:
                    raw, peer = udp.recvfrom(8192)
                    reply = json.loads(raw)
                except socket.timeout:
                    break
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(reply, dict):
                    continue
                device = reply.get("device_id", "")
                if (peer[1] == 37020 and reply.get("version") == 2 and reply.get("op") == "here"
                        and reply.get("nonce") == request["nonce"] and isinstance(device, str)
                        and re.fullmatch(r"[A-Za-z0-9_-]{1,95}", device)):
                    found[(device, peer[0])] = dict(device_id=device, address=peer[0])
    for device in sorted(identities):
        targets = [("255.255.255.255", bind) for bind in sorted(addresses)]
        if saved.get(device, {}).get("address"):
            targets.append((saved[device]["address"], None))
        for address, bind in targets:
            try:
                item = wifi_exchange(address, device, timeout=0.7, bind_address=bind)
                found[(device, item["address"])] = item
            except (OSError, RuntimeError):
                continue
    return list(found.values())


class WifiInstaller(Installer):
    """Use the existing installer over SSH; never change capture pairing or gates."""
    def __init__(self, device, password="luckfox", notify=lambda message: None):
        self.address = str(ipaddress.IPv4Address(device["address"]))
        self.expected_id = device["device_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,95}", self.expected_id):
            raise RuntimeError("仪器 ID 无效")
        self.password = password
        self.transport = None
        self.fingerprint = wifi_saved().get(self.expected_id, {}).get("host_key")
        self.hello_state = wifi_exchange(self.address, self.expected_id)["state"]
        try:
            self.connect()
            serial = self.execute("cat /proc/device-tree/serial-number").replace("\x00", "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,95}", serial):
                raise RuntimeError("设备序列号无效")
            config = json.loads(self.execute("cat /opt/instrument/config.json"))
            previous = wifi_saved().get(self.expected_id, {})
            if config.get("device_id") != self.expected_id or (previous.get("serial") and previous["serial"] != serial):
                raise RuntimeError("Wi-Fi 设备身份不匹配，停止连接")
            # Require the discovered address to belong to wlan0, excluding USB networking.
            if not re.search(r"\binet " + re.escape(self.address) + r"/", self.execute("ip -4 addr show wlan0")):
                raise RuntimeError("目标不是仪器 Wi-Fi 地址")
            super().__init__(serial, notify)
            self.device_id = self.expected_id
            saved = wifi_saved()
            saved[self.device_id] = dict(serial=serial, address=self.address, host_key=self.fingerprint)
            temporary = HOME / "wifi-devices.json.tmp"
            temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(HOME / "wifi-devices.json")
            self.record(transport="wifi-ssh", address=self.address, device_id=self.device_id,
                        serial=serial, host_key=self.fingerprint, connected=True)
        except BaseException:
            if self.transport:
                self.transport.close()
            raise

    def connect(self):
        import base64
        import paramiko
        if self.transport:
            self.transport.close()
        transport = paramiko.Transport(socket.create_connection((self.address, 22), timeout=5))
        try:
            transport.start_client(timeout=5)
            fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(
                transport.get_remote_server_key().asbytes()).digest()).decode().rstrip("=")
            if self.fingerprint and fingerprint != self.fingerprint:
                raise RuntimeError("SSH 主机密钥改变，停止连接；请核对仪器")
            transport.auth_password("root", self.password)
            self.fingerprint = fingerprint
            self.transport = transport
        except BaseException:
            transport.close()
            raise

    def execute(self, script, timeout=60, upload=None, download=None):
        import paramiko
        try:
            if not self.transport or not self.transport.is_active():
                self.connect()
            channel = self.transport.open_session(timeout=8)
            channel.settimeout(timeout)
            try:
                channel.exec_command(script)
                if upload:
                    with Path(upload).open("rb") as source:
                        for chunk in iter(lambda: source.read(65536), b""):
                            channel.sendall(chunk)
                channel.shutdown_write()
                if download:
                    with Path(download).open("wb") as target:
                        shutil.copyfileobj(channel.makefile("rb"), target)
                    output = ""
                else:
                    output = channel.makefile("rb").read().decode(errors="replace")
                error = channel.makefile_stderr("rb").read().decode(errors="replace")
                if channel.recv_exit_status():
                    raise RuntimeError(error or output or "Wi-Fi 板端命令失败")
                return output.replace("\x00", "").replace("\r", "").strip()
            finally:
                channel.close()
        except (OSError, EOFError, paramiko.SSHException) as error:
            if self.transport:
                self.transport.close()
            raise RuntimeError("Wi-Fi 连接中断：" + str(error)) from error

    def adb(self, *args, timeout=60):
        # Adapter keeps USB's proven install, backup and verification sequence shared.
        try:
            if args[0] == "shell":
                script = args[1]
                if script == "sync; reboot":
                    # Detach reboot so SSH can report success before the network drops.
                    script = "sync; nohup sh -c 'sleep 1; reboot' >/tmp/wifi-flash-reboot.log 2>&1 </dev/null &"
                output = self.execute(script, timeout)
            elif args[0] == "push":
                output = self.execute("cat > " + shlex.quote(args[2]), timeout, upload=args[1])
            elif args[0] == "pull":
                output = self.execute("cat " + shlex.quote(args[1]), timeout, download=args[2])
            else:
                raise RuntimeError("不支持的 Wi-Fi 操作")
            self.record(transport="wifi-ssh", args=args, output=output)
            return output
        except Exception as error:
            self.record(transport="wifi-ssh", args=args, error=str(error))
            raise

    def preflight(self, package):
        state = wifi_exchange(self.address, self.expected_id)["state"]
        validate_idle(state)
        super().preflight(package)
        if self.device_id != self.expected_id:
            raise RuntimeError("安装前设备身份改变")

    def close(self):
        try:
            super().close()
        finally:
            if self.transport:
                self.transport.close()
            self.password = ""


def gui(package_path=None, wifi=False):
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    window = tk.Tk()
    window.title("下位机一键烧录")
    window.geometry("600x490")
    window.resizable(False, False)
    events = queue.Queue()
    busy = False
    chosen = None
    wifi_target = None
    mode = tk.StringVar(value="wifi" if wifi else "usb")
    password = tk.StringVar(value="luckfox")
    version = tk.StringVar(value="未选择烧录包")
    filename = tk.StringVar(value="")
    status = tk.StringVar(value="选择压缩包，再连接仪器 USB 开始烧录")
    ttk.Label(window, text="下位机一键烧录", font=("Microsoft YaHei", 17)).pack(pady=(23, 10))
    modes = ttk.Frame(window)
    modes.pack()
    ttk.Radiobutton(modes, text="USB 烧录", variable=mode, value="usb").pack(side="left", padx=12)
    ttk.Radiobutton(modes, text="Wi-Fi 烧录", variable=mode, value="wifi").pack(side="left", padx=12)
    network = ttk.Frame(window)
    network.pack(pady=8)
    connect_button = ttk.Button(network, text="配对连接", state="disabled")
    connect_button.pack(side="left", padx=8)
    ttk.Label(network, text="设备密码").pack(side="left")
    password_entry = ttk.Entry(network, textvariable=password, show="*", width=16, state="disabled")
    password_entry.pack(side="left", padx=8)
    selector = ttk.Button(window, text="选择压缩包", width=22)
    selector.pack(pady=5)
    ttk.Label(window, textvariable=version, font=("Microsoft YaHei", 13)).pack(pady=7)
    ttk.Label(window, textvariable=filename, wraplength=550, justify="center").pack(pady=3)
    ttk.Label(window, textvariable=status, wraplength=550, justify="center").pack(pady=8)
    button = ttk.Button(window, text="开始烧录", width=22, state="disabled")
    button.pack(pady=12)
    ttk.Button(window, text="打开烧录记录", command=lambda: (HOME / "记录").mkdir(exist_ok=True) or os.startfile(HOME / "记录")).pack()

    def ready():
        return chosen is not None and (mode.get() == "usb" or wifi_target is not None)

    def mode_changed(*_):
        button.config(state="normal" if ready() and not busy else "disabled")
        connect_button.config(state="normal" if mode.get() == "wifi" and not busy else "disabled")
        password_entry.config(state="normal" if mode.get() == "wifi" and not busy else "disabled")
        if not busy:
            status.set(("已连接 " + wifi_target["device_id"] if wifi_target else "同一局域网，点击配对连接；新仪器请先打开配对模式")
                       if mode.get() == "wifi" else "已选好烧录包，连接 USB 后点击开始烧录")

    def connect_wifi(device=None):
        nonlocal busy, wifi_target
        wifi_target = None
        busy = True
        mode_changed()
        selector.config(state="disabled")
        for widget in modes.winfo_children():
            widget.config(state="disabled")
        secret = password.get()
        def work():
            installer = None
            try:
                devices = [device] if device else wifi_devices()
                if len(devices) > 1:
                    events.put(("wifi_choose", devices))
                elif not devices:
                    raise RuntimeError("未发现仪器，请确认同一局域网；新仪器需开启配对模式")
                else:
                    installer = WifiInstaller(devices[0], secret)
                    events.put(("wifi_connected", dict(devices[0], serial=installer.serial)))
            except Exception as error:
                events.put(("error", str(error)))
            finally:
                if installer:
                    installer.close()
        threading.Thread(target=work, daemon=True).start()

    def select_package(path=None):
        nonlocal chosen
        path = path or filedialog.askopenfilename(parent=window, title="选择烧录压缩包",
            initialdir=str(RELEASES) if RELEASES.is_dir() else str(HOME),
            filetypes=[("仪器应用压缩包", "*.tar.gz *.tgz")])
        if not path:
            return
        chosen = None
        button.config(state="disabled")
        filename.set(str(path))
        try:
            chosen = read_package(path)
            version.set("版本：" + chosen["version"])
            status.set("已选好烧录包，连接 USB 后点击开始烧录")
            button.config(state="normal" if ready() else "disabled")
        except Exception as error:
            version.set("压缩包无效")
            status.set(str(error))
            messagebox.showerror("无法使用此压缩包", str(error))

    def launch(serial=None):
        nonlocal busy
        if chosen is None:
            return
        selected_path = chosen["path"]
        selected_mode, selected_wifi, secret = mode.get(), wifi_target, password.get()
        busy = True
        button.config(state="disabled")
        selector.config(state="disabled")
        connect_button.config(state="disabled")
        password_entry.config(state="disabled")
        for widget in modes.winfo_children():
            widget.config(state="disabled")
        def work():
            installer = None
            try:
                package = read_package(selected_path)
                notify = lambda text: events.put(("status", text))
                if selected_mode == "wifi":
                    if selected_wifi is None:
                        raise RuntimeError("请先配对连接仪器")
                    installer = WifiInstaller(selected_wifi, secret, notify)
                else:
                    devices = usb_devices()
                    if serial is None and len(devices) > 1:
                        events.put(("choose", devices))
                        return
                    installer = Installer(choose_serial(devices, serial), notify)
                events.put(("status", "目标 " + installer.serial + " · " + package["version"]))
                result = installer.flash_install(package)
                events.put(("done", result))
            except Exception as error:
                events.put(("error", str(error)))
            finally:
                if installer:
                    try:
                        installer.close()
                    except Exception as error:
                        events.put(("error", str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll():
        nonlocal busy, wifi_target
        while not events.empty():
            kind, value = events.get()
            if kind == "status":
                status.set(value)
            else:
                busy = False
                button.config(state="normal" if ready() else "disabled")
                selector.config(state="normal")
                for widget in modes.winfo_children():
                    widget.config(state="normal")
                mode_changed()
                if kind == "wifi_connected":
                    wifi_target = value
                    mode_changed()
                    continue
                if kind == "wifi_choose":
                    dialog = tk.Toplevel(window)
                    dialog.title("选择 Wi-Fi 仪器")
                    dialog.transient(window)
                    dialog.grab_set()
                    for device in value:
                        def select_wifi(d=device):
                            dialog.destroy()
                            connect_wifi(d)
                        ttk.Button(dialog, text=device["device_id"] + " · " + device["address"],
                                   command=select_wifi).pack(padx=20, pady=7, fill="x")
                    continue
                if kind == "choose":
                    dialog = tk.Toplevel(window)
                    dialog.title("选择烧录设备")
                    dialog.transient(window)
                    dialog.grab_set()
                    ttk.Label(dialog, text="连接了多台设备，请选一台：").pack(padx=20, pady=12)
                    for serial, state in value:
                        def select(s=serial):
                            dialog.destroy()
                            launch(s)
                        ttk.Button(dialog, text=serial + ("" if state == "device" else "（未授权或离线）"),
                                   command=select, state="normal" if state == "device" else "disabled").pack(padx=20, pady=7, fill="x")
                else:
                    status.set(value)
                    if kind == "error":
                        messagebox.showerror("烧录未完成", value)
        window.after(100, poll)

    button.config(command=launch)
    selector.config(command=select_package)
    connect_button.config(command=connect_wifi)
    mode.trace_add("write", mode_changed)
    mode_changed()
    if package_path:
        select_package(package_path)
    window.protocol("WM_DELETE_WINDOW", lambda: messagebox.showinfo("正在烧录", "请等待烧录结束") if busy else window.destroy())
    poll()
    window.mainloop()


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true", help="检查正式包、设备及空闲状态，不安装固件")
    actions.add_argument("--install", action="store_true")
    parser.add_argument("--force", action="store_true", help="验证用：同版本也重新安装")
    parser.add_argument("--serial")
    parser.add_argument("--wifi", action="store_true", help="通过局域网 Wi-Fi/SSH 操作，不使用 ADB")
    actions.add_argument("--discover", action="store_true", help="发现 Wi-Fi 仪器并输出 JSON，不安装")
    actions.add_argument("--connect", action="store_true", help="连接并保存 Wi-Fi 仪器身份，不安装")
    parser.add_argument("--address", help="明确指定 Wi-Fi IPv4 地址，需同时指定 --device-id")
    parser.add_argument("--device-id", help="明确指定仪器 ID；多台时必须选择")
    parser.add_argument("--password-stdin", action="store_true", help="从标准输入读取 SSH 密码；默认使用原厂口令，不保存密码")
    parser.add_argument("--package", type=Path, help="选择应用压缩包，版本从包内读取")
    args = parser.parse_args()
    if args.discover:
        print(json.dumps(wifi_devices(), ensure_ascii=False, indent=2))
    elif args.check or args.install or args.connect:
        installer = None
        try:
            package = None if args.connect else (read_package(args.package) if args.package else latest_package())
            if args.wifi or args.connect:
                if args.address and not args.device_id:
                    parser.error("--address 需要同时指定 --device-id")
                devices = ([dict(address=args.address, device_id=args.device_id)] if args.address else wifi_devices())
                if args.device_id:
                    devices = [d for d in devices if d["device_id"] == args.device_id]
                if len(devices) != 1:
                    raise RuntimeError("未找到唯一仪器，请使用 --discover 查看，再用 --device-id 及 --address 指定目标")
                secret = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else "luckfox"
                installer = WifiInstaller(devices[0], secret, print)
                if args.serial and installer.serial != args.serial:
                    raise RuntimeError("Wi-Fi 仪器序列号与 --serial 不一致")
            else:
                installer = Installer(choose_serial(usb_devices(), args.serial), print)
            if args.connect:
                print("CONNECTED " + installer.device_id + " " + installer.address)
            elif args.check:
                installer.preflight(package)
                print("CHECK_PASS " + package["version"] + " " + installer.serial)
            else:
                print(installer.flash_install(package, args.force))
            print("REPORT=" + str(installer.report))
        except Exception as error:
            if installer:
                installer.record(result="FAILED", error=str(error))
                print("REPORT=" + str(installer.report), file=sys.stderr)
            print("ERROR: " + str(error), file=sys.stderr)
            sys.exit(1)
        finally:
            if installer:
                installer.close()
    else:
        gui(args.package, wifi=args.wifi)
