"""看视频 + 三个按键测试。USB 连接，不用 Wi-Fi。"""

from __future__ import annotations

import configparser
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


TOOL_DIR = app_dir()
REPORT_ROOT = TOOL_DIR / "报告"
FORWARD_PORT = 8557
LIVE_URL = f"rtsp://127.0.0.1:{FORWARD_PORT}/live/0"
PREVIEW_SIZE = (640, 540)
POLL_INTERVAL = 0.1
CARD_BG = "#eef3fa"
PRESSED_BG = "#ffe0bf"
IDLE_FG = "#14324f"
PRESSED_FG = "#b34700"
PROBE_MARKERS = ("GADGET", "FUNCS", "LINKED", "FEEDER", "UDC")
PROBE_SCRIPT = (
    "G=/sys/kernel/config/usb_gadget; "
    'echo GADGET=$(ls $G 2>/dev/null | tr "\\n" " "); '
    'echo FUNCS=$(ls $G/*/functions 2>/dev/null | tr "\\n" " "); '
    "echo LINKED=$(ls -l $G/*/configs/*/ 2>/dev/null | grep -c uvc); "
    "echo FEEDER=$(ls /oem/usr/bin /usr/bin 2>/dev/null | grep -i -c uvc); "
    "echo UDC=$(cat /sys/class/udc/*/state 2>/dev/null)"
)
WINDOWS_CAMERAS = (
    "Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in 'Camera','Image' } "
    "| ForEach-Object { $_.FriendlyName + '|' + $_.Status }"
)


@dataclass(frozen=True)
class KeySpec:
    label: str
    pin: str
    gpio: int

    @property
    def short(self) -> str:
        return f"{self.pin} · GPIO {self.gpio}"


# 左 GPIO0_A3、中 GPIO0_A4、右 GPIO0_A0，低电平有效。
KEYS = (KeySpec("左键", "GPIO0_A3", 3), KeySpec("中键", "GPIO0_A4", 4), KeySpec("右键", "GPIO0_A0", 0))


@dataclass
class Tally:
    low: bool = False
    presses: int = 0
    since: float = 0.0
    hold_ms: int = 0
    first_press: str = ""
    last_press: str = ""
    releases: int = 0
    armed: bool = False


@dataclass
class KeyRead:
    levels: list[int]
    now: float


def load_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.optionxform = str
    path = TOOL_DIR / "config.ini"
    if path.is_file():
        parser.read(path, encoding="utf-8")
    return parser


def device_name() -> str:
    return load_config().get("device", "name", fallback="ISG1321")


def preferred_serial() -> str:
    return ""


def adb_exe() -> str:
    bundled = Path(getattr(sys, "_MEIPASS", TOOL_DIR)) / "adb" / "adb.exe"
    if bundled.is_file():
        return str(bundled)
    configured = load_config().get("device", "adb", fallback="adb.exe").strip() or "adb.exe"
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = TOOL_DIR / candidate
    if candidate.is_file():
        return str(candidate)
    beside = TOOL_DIR / "adb.exe"
    if beside.is_file():
        return str(beside)
    raise RuntimeError("找不到 adb.exe。请把 adb.exe、AdbWinApi.dll、AdbWinUsbApi.dll 放在程序同一目录，或改 config.ini 里的 adb 路径。")


def decode(data: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def run(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    completed = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=flags)
    completed.stdout = decode(completed.stdout)  # type: ignore[assignment]
    completed.stderr = decode(completed.stderr)  # type: ignore[assignment]
    return completed


def invoke_adb(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return run([adb_exe(), *args], timeout)


def list_devices() -> list[str]:
    try:
        completed = invoke_adb("devices", "-l", timeout=15)
    except Exception:
        return []
    # Windows ADB reports get-devpath=unknown; verify serials against physical PnP USB devices.
    physical = run([powershell_exe(), "-NoProfile", "-Command",
        "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\VID_*' } "
        "| ForEach-Object { ($_.InstanceId -split '\\\\')[-1] }"], 20)
    serials = {line.strip().lower() for line in physical.stdout.splitlines()}
    return [
        parts[0]
        for line in completed.stdout.splitlines()
        if len(parts := line.split()) >= 2 and parts[1] == "device" and parts[0].lower() in serials
    ]


_serial: str | None = None


def connected_serial() -> str:
    global _serial
    if _serial:
        return _serial
    serials = list_devices()
    preferred = preferred_serial()
    if preferred in serials:
        _serial = preferred
    elif len(serials) == 1:
        _serial = serials[0]
    elif not serials:
        raise RuntimeError("没有 ADB 设备。请用 USB 连接板子后再试。")
    else:
        raise RuntimeError("有多台 ADB 设备：" + "、".join(serials))
    log(f"adb {_serial}")
    return _serial


def use_serial(serial: str) -> str:
    global _serial
    _serial = serial.strip() or None
    return connected_serial()


def adb(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    completed = invoke_adb("-s", connected_serial(), *args, timeout=timeout)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or f"adb 失败：{args[0]}")
    return completed


def log(message: str) -> None:
    folder = TOOL_DIR / "logs"
    folder.mkdir(exist_ok=True)
    line = datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + " ".join(message.split())
    with (folder / "仪器测试.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def save_dir(root: Path, when: datetime | None = None) -> Path:
    folder = root / (when or datetime.now()).strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def unique_path(folder: Path, name: str) -> Path:
    path = folder / name
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while True:
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def prepare_keys() -> None:
    helper = Path(getattr(sys, "_MEIPASS", TOOL_DIR)) / "payload" / "button_inputs.sh"
    if helper.is_file():
        adb("push", str(helper), "/tmp/instrument-button-inputs.sh", timeout=15)
        adb("shell", "sh /tmp/instrument-button-inputs.sh", timeout=10)
        return
    script = "; ".join(
        [f"[ -d /sys/class/gpio/gpio{key.gpio} ] || echo {key.gpio} > /sys/class/gpio/export" for key in KEYS]
        + [f"echo in > /sys/class/gpio/gpio{key.gpio}/direction" for key in KEYS]
    )
    adb("shell", script, timeout=10)


def read_levels() -> list[int]:
    paths = " ".join(f"/sys/class/gpio/gpio{key.gpio}/value" for key in KEYS)
    completed = adb("shell", f"cat {paths} 2>&1", timeout=6)
    values = [line.strip() for line in completed.stdout.splitlines() if line.strip() in ("0", "1")]
    if len(values) != len(KEYS):
        detail = (completed.stdout + completed.stderr).strip()
        if "No such file" in detail:
            prepare_keys()
        raise RuntimeError("读不到三个按键电平。板上 GPIO 没初始化，先跑 /opt/instrument/bin/button_inputs.sh 或重新上电。")
    return [int(value) for value in values]


def apply_sample(tallies: list[Tally], levels: list[int], now: float, stamp: str) -> None:
    for index, (tally, level) in enumerate(zip(tallies, levels)):
        pressed = level == 0
        if not pressed:
            tally.armed = True
        if pressed and not tally.low and tally.armed:
            tally.presses += 1
            tally.since = now
            tally.first_press = tally.first_press or stamp
            tally.last_press = stamp
        if not pressed and tally.low and tally.since:
            tally.releases += 1
            tally.hold_ms = max(tally.hold_ms, int((now - tally.since) * 1000))
        tally.low = pressed


def key_mask(levels: list[int]) -> int:
    return sum(1 << index for index, level in enumerate(levels) if level == 0)


def passed(tallies: list[Tally]) -> list[str]:
    return [key.label for key, tally in zip(KEYS, tallies) if tally.releases > 0]


def verdict(tallies: list[Tally]) -> str:
    names = passed(tallies)
    if len(names) == len(KEYS):
        return "三个按键全部通过"
    missed = "、".join(key.label for key in KEYS if key.label not in names)
    return f"未通过：{missed}（未完成按下和松开）"


def report_text(serial: str, started: datetime, ended: datetime, tallies: list[Tally], combo: int) -> str:
    lines = [
        f"{device_name()} 三键测试报告",
        f"设备：{serial}",
        f"时间：{started:%Y-%m-%d %H:%M:%S} → {ended:%H:%M:%S}",
        "按键低电平有效：按下 = 0，松开 = 1。",
        "",
    ]
    for key, tally in zip(KEYS, tallies):
        result = "通过" if tally.releases else "未通过"
        lines.append(
            f"{key.label} {key.short}  按下 {tally.presses} 次  最长 {tally.hold_ms} ms  "
            f"首次 {tally.first_press or '—'}  {result}"
        )
    lines += ["", f"左+右 同时按住：{combo} 次", "", f"结论：{verdict(tallies)}"]
    return "\n".join(lines) + "\n"


def save_report(text: str, started: datetime, ended: datetime, serial: str) -> Path:
    folder = save_dir(REPORT_ROOT, ended)
    path = unique_path(folder, ended.strftime("按键测试_%H%M%S.txt"))
    path.write_text(text, encoding="utf-8")
    log(f"报告 {path.name} {serial} {verdict_line(text)}")
    return path


def verdict_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("结论"):
            return line
    return ""


def parse_probe(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        name, _, value = line.strip().partition("=")
        if name in PROBE_MARKERS:
            found[name] = value.strip()
    missing = [name for name in PROBE_MARKERS if name not in found]
    if missing:
        raise RuntimeError("板端探测没有返回：" + "、".join(missing))
    return found


def windows_cameras() -> list[str]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(
            [powershell_exe(), "-NoProfile", "-Command", WINDOWS_CAMERAS],
            capture_output=True,
            timeout=30,
            creationflags=flags,
        )
    except Exception:
        return []
    text = decode(completed.stdout)
    return sorted({line.strip() for line in text.splitlines() if line.strip()})


def uvc_lines(board: dict[str, str], cameras: list[str]) -> list[str]:
    funcs = board.get("FUNCS", "")
    has_function = "uvc" in funcs
    linked = board.get("LINKED", "0") not in ("", "0")
    feeder = board.get("FEEDER", "0") not in ("", "0")
    names = [item.split("|")[0] for item in cameras]
    output = [
        f"板端 USB 设备模式：{board.get('UDC', '未知')}，gadget={board.get('GADGET', '无')}",
        f"内核 UVC 设备功能：{'有' if has_function else '没有'}（functions：{funcs or '无'}）",
        f"已接进当前 USB 复合设备：{'是' if linked else '否，现在只挂了网卡和 adb'}",
        f"板端喂帧程序：{'有' if feeder else '没有（找不到 rk_mpi_uvc / uvc-gadget）'}",
        "Windows 现有摄像头：" + ("、".join(names) if names else "没读到"),
    ]
    if linked and feeder and has_function:
        output.append("结论：仅板端配置齐全；仍需 Windows 识别目标设备并实际读帧才能通过。")
        return output
    output.append("结论：现在还不能当电脑摄像头，得先在板端补两步：把 uvc 功能挂进 USB 配置、加一个把画面喂给 UVC 的程序。")
    output.append("注意：喂帧程序要占摄像头传感器，会和 rkipc 的推流、仪器录像冲突，切换期间 ADB 也会重连。")
    return output


def probe_uvc(serial: str) -> list[str]:
    completed = invoke_adb("-s", serial, "shell", PROBE_SCRIPT, timeout=20)
    if completed.returncode:
        raise RuntimeError(completed.stderr or "板端探测失败")
    board = parse_probe(completed.stdout)
    cameras = windows_cameras()
    lines = uvc_lines(board, cameras)
    log("UVC 探测 " + " | ".join(lines))
    return lines


def rkipc_running() -> bool:
    completed = adb("shell", "pidof rkipc || echo not-running", timeout=15)
    return "not-running" not in f"{completed.stdout}\n{completed.stderr}"


def start_rkipc() -> str:
    completed = adb(
        "shell",
        "setsid /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles >/tmp/rkipc-tool.log 2>&1 < /dev/null & "
        "sleep 2; pidof rkipc || echo not-running",
        timeout=25,
    )
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    log("启动 rkipc " + output)
    if "not-running" in output:
        detail = adb("shell", "tail -n 15 /tmp/rkipc-tool.log", timeout=10)
        raise RuntimeError("摄像头程序没有启动。\n" + (detail.stdout or output).strip())
    return output


def open_stream():
    import cv2

    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;8000000"
    for _ in range(3):
        capture = cv2.VideoCapture(LIVE_URL, cv2.CAP_FFMPEG)
        capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000)
        for _ in range(8):
            ok, frame = capture.read()
            if ok and frame is not None:
                return capture, frame
            time.sleep(0.25)
        capture.release()
        time.sleep(0.5)
    raise RuntimeError("没有画面。请确认 USB 已连接、板上 rkipc 在运行。")


def measure_video(seconds: float) -> str:
    serial = connected_serial()
    if not rkipc_running():
        start_rkipc()
    adb("forward", f"tcp:{FORWARD_PORT}", "tcp:554", timeout=15)
    capture, frame = open_stream()
    height, width = frame.shape[:2]
    frames = 1
    first = time.monotonic()
    last = first
    try:
        while time.monotonic() - first < seconds:
            ok, _ = capture.read()
            if ok:
                frames += 1
                last = time.monotonic()
    finally:
        capture.release()
        invoke_adb("-s", serial, "forward", "--remove", f"tcp:{FORWARD_PORT}", timeout=10)
    span = last - first
    fps = (frames - 1) / span if span > 0 else 0.0
    return f"{serial} {width}*{height} 帧数 {frames} 实测 {fps:.1f} fps"


from uvc_support import App, powershell_exe


def self_check() -> None:
    from test_tool import run_checks
    run_checks(sys.modules[__name__])

def main() -> None:
    import tkinter as tk

    root = tk.Tk()
    App(root, sys.modules[__name__])
    root.mainloop()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        self_check()
    elif len(sys.argv) > 1 and sys.argv[1] == "--acceptance":
        from acceptance import run as acceptance_run
        acceptance_run(sys.modules[__name__], float(sys.argv[2]), sys.argv[3],
                       switch="--switch" in sys.argv, validation_reboot="--validation-reboot" in sys.argv)
    elif len(sys.argv) > 1 and sys.argv[1] == "--keys-probe":
        connected_serial()
        for index in range(int(sys.argv[2]) if len(sys.argv) > 2 else 10):
            print(index, read_levels(), flush=True)
            time.sleep(0.2)
    elif len(sys.argv) > 1 and sys.argv[1] == "--video-probe":
        print(measure_video(float(sys.argv[2]) if len(sys.argv) > 2 else 5.0))
    elif len(sys.argv) > 1 and sys.argv[1] == "--uvc-probe":
        print("\n".join(probe_uvc(connected_serial())))
    else:
        main()
