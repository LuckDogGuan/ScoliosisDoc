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
    return load_config().get("device", "serial", fallback="3253c006806f5194")


def adb_exe() -> str:
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
        completed = invoke_adb("devices", timeout=15)
    except Exception:
        return []
    return [
        parts[0]
        for line in completed.stdout.splitlines()
        if len(parts := line.split()) >= 2 and parts[1] == "device"
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
        if pressed and not tally.low:
            tally.presses += 1
            tally.since = now
            tally.first_press = tally.first_press or stamp
            tally.last_press = stamp
        if not pressed and tally.low:
            tally.hold_ms = max(tally.hold_ms, int((now - tally.since) * 1000))
        tally.low = pressed


def key_mask(levels: list[int]) -> int:
    return sum(1 << index for index, level in enumerate(levels) if level == 0)


def passed(tallies: list[Tally]) -> list[str]:
    return [key.label for key, tally in zip(KEYS, tallies) if tally.presses > 0]


def verdict(tallies: list[Tally]) -> str:
    names = passed(tallies)
    if len(names) == len(KEYS):
        return "三个按键全部通过"
    missed = "、".join(key.label for key in KEYS if key.label not in names)
    return f"未通过：{missed}（没检测到按下）"


def report_text(serial: str, started: datetime, ended: datetime, tallies: list[Tally], combo: int) -> str:
    lines = [
        f"{device_name()} 三键测试报告",
        f"设备：{serial}",
        f"时间：{started:%Y-%m-%d %H:%M:%S} → {ended:%H:%M:%S}",
        "按键低电平有效：按下 = 0，松开 = 1。",
        "",
    ]
    for key, tally in zip(KEYS, tallies):
        result = "通过" if tally.presses else "未通过"
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
            ["powershell.exe", "-NoProfile", "-Command", WINDOWS_CAMERAS],
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
        output.append("结论：板端条件齐全，Windows「相机」里应能直接打开这颗摄像头。")
        return output
    output.append("结论：现在还不能当电脑摄像头，得先在板端补两步：把 uvc 功能挂进 USB 配置、加一个把画面喂给 UVC 的程序。")
    output.append("注意：喂帧程序要占摄像头传感器，会和 rkipc 的推流、仪器录像冲突，切换期间 ADB 也会重连。")
    return output


def probe_uvc(serial: str) -> list[str]:
    board = parse_probe(adb("-s", serial, "shell", PROBE_SCRIPT, timeout=20).stdout)
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


class App:
    def __init__(self, root) -> None:
        import tkinter as tk
        from tkinter import ttk
        from PIL import Image

        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.Image = Image
        self.busy = False
        self.live = False
        self.capture = None
        self.latest = None
        self.preview_thread = None
        self.keys_live = False
        self.keys_thread = None
        self.keys_lock = threading.Lock()
        self.tallies = [Tally() for _ in KEYS]
        self.combo = 0
        self.keys_error = ""
        self.keys_started: datetime | None = None
        self.levels: list[int] | None = None
        self.status = tk.StringVar(value="先选设备，再点「连接画面」。")
        self.link = tk.StringVar(value="未连接")
        self.keys_status = tk.StringVar(value="还没开始。按下每个键，窗口里会变色。")
        self.combo_text = tk.StringVar(value="左+右 同按：0 次")

        root.title(f"{device_name()} 视频与按键测试")
        root.resizable(False, False)

        outer = ttk.Frame(root, padding=12)
        outer.grid()
        top = ttk.Frame(outer)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="设备").grid(row=0, column=0, sticky="w")
        self.device_combo = ttk.Combobox(top, width=22, state="readonly")
        self.device_combo.grid(row=0, column=1, padx=8)
        ttk.Button(top, text="刷新", width=8, command=self.reload_devices).grid(row=0, column=2, padx=(0, 8))
        self.probe_btn = ttk.Button(top, text="探测能否当电脑摄像头", command=self.on_probe)
        self.probe_btn.grid(row=0, column=3)

        notebook = ttk.Notebook(outer)
        notebook.grid(row=1, column=0, pady=(10, 0))
        video_tab = ttk.Frame(notebook, padding=10)
        keys_tab = ttk.Frame(notebook, padding=10)
        notebook.add(video_tab, text="  画面  ")
        notebook.add(keys_tab, text="  按键  ")

        buttons = ttk.Frame(video_tab)
        buttons.grid(row=0, column=0, columnspan=4)
        self.connect_btn = ttk.Button(buttons, text="连接画面", width=12, command=self.on_connect)
        self.connect_btn.grid(row=0, column=0, padx=(0, 8))
        self.disconnect_btn = ttk.Button(buttons, text="断开", width=10, command=self.on_disconnect)
        self.disconnect_btn.grid(row=0, column=1)
        blank = self.Image.new("RGB", PREVIEW_SIZE, (32, 32, 32))
        self.preview_photo = self.ImageTk_photo(blank)
        self.preview = ttk.Label(video_tab, image=self.preview_photo)
        self.preview.grid(row=1, column=0, columnspan=4, pady=(10, 4))
        ttk.Label(video_tab, textvariable=self.link).grid(row=2, column=0, columnspan=4, sticky="w")
        ttk.Label(video_tab, text="画面经 USB 转发，不是电脑摄像头。正式改分辨率用摄像头测试工具。").grid(
            row=3, column=0, columnspan=4, sticky="w"
        )

        self.key_cards: list[tuple[object, object, object]] = []
        grid = ttk.Frame(keys_tab)
        grid.grid(row=0, column=0, columnspan=4)
        for index, key in enumerate(KEYS):
            card = self.tk.Frame(grid, bd=3, relief="raised", padx=18, pady=10, bg=CARD_BG)
            card.grid(row=0, column=index, padx=8)
            self.tk.Label(card, text=key.label, bg=CARD_BG, font=("", 11)).grid(row=0, column=0)
            state = self.tk.Label(card, text="—", bg=CARD_BG, fg=IDLE_FG, font=("", 24, "bold"))
            state.grid(row=1, column=0)
            count = self.tk.Label(card, text="按下 0 次", bg=CARD_BG, fg=IDLE_FG)
            count.grid(row=2, column=0)
            self.tk.Label(card, text=key.short, bg=CARD_BG, fg="#5b6b7d").grid(row=3, column=0)
            self.key_cards.append((card, state, count))

        control = ttk.Frame(keys_tab)
        control.grid(row=1, column=0, columnspan=4, pady=(14, 6))
        self.keys_start_btn = ttk.Button(control, text="开始测试", width=12, command=self.on_keys_start)
        self.keys_start_btn.grid(row=0, column=0, padx=(0, 8))
        self.keys_stop_btn = ttk.Button(control, text="停止", width=8, command=self.on_keys_stop)
        self.keys_stop_btn.grid(row=0, column=1, padx=(0, 8))
        self.keys_reset_btn = ttk.Button(control, text="清零", width=8, command=self.on_keys_reset)
        self.keys_reset_btn.grid(row=0, column=2)
        self.save_btn = ttk.Button(control, text="保存报告", width=10, command=self.on_save_report)
        self.save_btn.grid(row=0, column=3, padx=(8, 0))
        ttk.Label(keys_tab, textvariable=self.combo_text).grid(row=2, column=0, columnspan=4, sticky="w")
        ttk.Label(keys_tab, textvariable=self.keys_status, wraplength=620).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )
        ttk.Label(keys_tab, text="低电平有效：按下变橙色。三个键都按下过就算通过。报告存到本目录\\报告\\当天日期。").grid(
            row=4, column=0, columnspan=4, sticky="w"
        )

        ttk.Label(outer, textvariable=self.status, wraplength=680).grid(row=2, column=0, sticky="w", pady=(12, 0))

        self.reload_devices()
        self.refresh()
        root.after(200, self.tick)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def ImageTk_photo(self, image):
        from PIL import ImageTk

        return ImageTk.PhotoImage(image)

    def reload_devices(self) -> list[str]:
        devices = list_devices()
        self.device_combo["values"] = devices
        current = self.device_combo.get().strip()
        if current in devices:
            pass
        elif preferred_serial() in devices:
            self.device_combo.set(preferred_serial())
        elif len(devices) == 1:
            self.device_combo.set(devices[0])
        elif not devices:
            self.device_combo.set("")
        if not self.live:
            self.link.set(f"发现 {len(devices)} 台" if devices else "没有 ADB 设备")
        return devices

    def chosen_serial(self) -> str:
        return use_serial(self.device_combo.get())

    def refresh(self) -> None:
        self.probe_btn["state"] = "disabled" if self.busy else "normal"
        self.connect_btn["state"] = "disabled" if self.busy or self.live else "normal"
        self.disconnect_btn["state"] = "normal" if self.live and not self.busy else "disabled"
        self.device_combo["state"] = "disabled" if self.busy or self.live else "readonly"
        self.keys_start_btn["state"] = "disabled" if self.keys_live or self.busy else "normal"
        self.keys_stop_btn["state"] = "normal" if self.keys_live else "disabled"
        self.keys_reset_btn["state"] = "disabled" if self.keys_live or self.busy else "normal"
        self.save_btn["state"] = "disabled" if self.busy else "normal"

    def fail(self, message: str) -> None:
        from tkinter import messagebox

        self.busy = False
        self.refresh()
        self.status.set(message)
        log("失败 " + message)
        messagebox.showerror("仪器测试", message)

    def done(self, message: str) -> None:
        self.busy = False
        self.refresh()
        self.status.set(message)
        log(message)

    def on_probe(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.refresh()
        self.status.set("正在探测…")

        def work() -> None:
            try:
                serial = self.chosen_serial()
                lines = probe_uvc(serial)
            except Exception as exc:
                self.root.after(0, lambda error=exc: self.fail(str(error)))
                return

            def finish() -> None:
                from tkinter import messagebox

                conclusion = next((line for line in lines if line.startswith("结论")), lines[0])
                self.done(conclusion)
                messagebox.showinfo("能否当电脑摄像头", "\n".join(lines))
                log("探测结论 " + conclusion)

            self.root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def on_connect(self) -> None:
        if self.busy or self.live:
            return
        devices = self.reload_devices()
        if not self.device_combo.get():
            if len(devices) == 1:
                self.device_combo.set(devices[0])
            else:
                self.link.set("没有 ADB 设备" if not devices else "请先选设备")
                return
        serial = self.chosen_serial()
        self.busy = True
        self.refresh()
        self.link.set(f"正在连接 {serial}…")

        def work() -> None:
            try:
                if not rkipc_running():
                    log("连接时 rkipc 未运行")
                    start_rkipc()
                adb("forward", f"tcp:{FORWARD_PORT}", "tcp:554", timeout=15)
                capture, frame = open_stream()
            except Exception as exc:
                self.root.after(0, lambda error=exc: self.fail_link(str(error)))
                return

            def started() -> None:
                self.capture = capture
                self.latest = frame
                self.live = True
                height, width = frame.shape[:2]
                self.link.set(f"已连接 {serial}  {width}*{height}")
                self.busy = False
                self.refresh()
                self.show_frame()
                self.preview_thread = threading.Thread(target=self.preview_loop, daemon=True)
                self.preview_thread.start()

            self.root.after(0, started)

        threading.Thread(target=work, daemon=True).start()

    def fail_link(self, message: str) -> None:
        self.busy = False
        self.live = False
        self.link.set("连接失败")
        self.refresh()
        self.fail(message)

    def show_frame(self) -> None:
        if self.latest is None:
            return
        import cv2
        from PIL import Image

        rgb = cv2.cvtColor(self.latest, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        image.thumbnail(PREVIEW_SIZE, Image.Resampling.BILINEAR)
        self.preview_photo = self.ImageTk_photo(image)
        self.preview.configure(image=self.preview_photo)

    def preview_loop(self) -> None:
        misses = 0
        window_start = time.monotonic()
        frames = 0
        while self.live and self.capture is not None:
            ok, frame = self.capture.read()
            if not ok or frame is None:
                misses += 1
                if misses >= 8:
                    self.root.after(0, self.on_stream_lost)
                    break
                continue
            misses = 0
            frames += 1
            self.latest = frame
            self.root.after(0, self.show_frame)
            elapsed = time.monotonic() - window_start
            if elapsed >= 2.0:
                fps = frames / elapsed
                window_start = time.monotonic()
                frames = 0
                self.root.after(0, lambda value=fps: self.link.set(f"已连接  实测 {value:.1f} fps"))
            time.sleep(0.03)
        capture = self.capture
        self.capture = None
        if capture is not None:
            capture.release()

    def on_stream_lost(self) -> None:
        self.live = False
        self.link.set("连接已断开：没有画面")
        self.refresh()

    def on_disconnect(self) -> None:
        if not self.live:
            return
        serial = self.device_combo.get().strip()
        self.live = False
        thread = self.preview_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)
        capture = self.capture
        self.capture = None
        if capture is not None:
            capture.release()
        self.preview_thread = None
        self.latest = None
        self.link.set("已断开")
        self.refresh()
        if serial:
            try:
                invoke_adb("-s", serial, "forward", "--remove", f"tcp:{FORWARD_PORT}", timeout=10)
            except Exception:
                pass

    def on_keys_start(self) -> None:
        if self.keys_live or self.busy:
            return
        try:
            self.chosen_serial()
        except Exception as exc:
            self.fail(str(exc))
            return
        self.keys_live = True
        if self.keys_started is None:
            self.keys_started = datetime.now()
        self.keys_status.set("正在监听三个按键。每个都按一下，按住约 1 秒。")
        self.keys_thread = threading.Thread(target=self.keys_loop, daemon=True)
        self.keys_thread.start()
        self.refresh()

    def on_keys_stop(self) -> None:
        self.keys_live = False
        thread = self.keys_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)
        self.keys_thread = None
        with self.keys_lock:
            self.keys_status.set("已停止监听。" + verdict(self.tallies))
        self.refresh()

    def on_keys_reset(self) -> None:
        with self.keys_lock:
            self.tallies = [Tally() for _ in KEYS]
            self.combo = 0
            self.levels = None
            self.keys_error = ""
            self.keys_started = datetime.now() if self.keys_live else None
        self.keys_status.set("已清零。")
        self.paint_cards()

    def keys_loop(self) -> None:
        while self.keys_live:
            began = time.monotonic()
            try:
                levels = read_levels()
            except Exception as exc:
                with self.keys_lock:
                    self.keys_error = str(exc)
                time.sleep(0.5)
                continue
            now = time.monotonic()
            stamp = datetime.now().strftime("%H:%M:%S")
            with self.keys_lock:
                previous = self.levels
                apply_sample(self.tallies, levels, now, stamp)
                mask = key_mask(levels)
                if previous is not None and (mask & 5) == 5 and (previous & 5) != 5:
                    self.combo += 1
                self.levels = levels
                self.keys_error = ""
            delay = POLL_INTERVAL - (time.monotonic() - began)
            if delay > 0:
                time.sleep(delay)

    def paint_cards(self) -> None:
        with self.keys_lock:
            cards = [
                (
                    tally.presses,
                    tally.low,
                    max(tally.hold_ms, int((time.monotonic() - tally.since) * 1000)) if tally.low else tally.hold_ms,
                )
                for tally in self.tallies
            ]
            combo = self.combo
            error = self.keys_error
            live = self.keys_live
            names = verdict(self.tallies)
        for (card, state, count), (presses, low, hold) in zip(self.key_cards, cards):
            background = PRESSED_BG if low else CARD_BG
            foreground = PRESSED_FG if low else IDLE_FG
            card.configure(bg=background)
            state.configure(text="按下" if low else "松开", fg=foreground, bg=background)
            count.configure(text=f"按下 {presses} 次 · {hold} ms", fg=foreground, bg=background)
        self.combo_text.set(f"左+右 同按：{combo} 次")
        if error:
            self.keys_status.set(error)
        elif live:
            self.keys_status.set(f"正在监听。{names}。")

    def tick(self) -> None:
        if self.levels_shown() or self.keys_live:
            self.paint_cards()
        self.root.after(500, self.tick)

    def levels_shown(self) -> bool:
        with self.keys_lock:
            return self.levels is not None

    def on_save_report(self) -> None:
        if self.busy:
            return
        started = self.keys_started or datetime.now()
        ended = datetime.now()
        with self.keys_lock:
            tallies = [
                Tally(
                    presses=tally.presses,
                    hold_ms=tally.hold_ms,
                    first_press=tally.first_press,
                    last_press=tally.last_press,
                )
                for tally in self.tallies
            ]
            combo = self.combo
        serial = self.device_combo.get().strip() or "未选择设备"
        text = report_text(serial, started, ended, tallies, combo)

        def work() -> None:
            try:
                path = save_report(text, started, ended, serial)
            except Exception as exc:
                self.root.after(0, lambda error=exc: self.fail(str(error)))
                return
            self.root.after(0, lambda: self.done(f"报告已保存 报告\\{ended:%Y-%m-%d}\\{path.name}"))

        threading.Thread(target=work, daemon=True).start()

    def on_close(self) -> None:
        if self.busy:
            self.status.set("请等当前操作结束再关闭。")
            return
        if self.live:
            self.on_disconnect()
        self.keys_live = False
        self.root.destroy()


def self_check() -> None:
    tallies = [Tally(), Tally(), Tally()]
    apply_sample(tallies, [0, 1, 1], 10.0, "20:00:01")
    apply_sample(tallies, [0, 1, 1], 10.5, "20:00:01")
    apply_sample(tallies, [1, 1, 1], 11.0, "20:00:02")
    apply_sample(tallies, [1, 0, 1], 12.0, "20:00:03")
    apply_sample(tallies, [1, 1, 0], 13.0, "20:00:04")
    apply_sample(tallies, [1, 1, 1], 14.0, "20:00:05")
    if [tally.presses for tally in tallies] != [1, 1, 1]:
        raise SystemExit(f"按下次数不对：{[t.presses for t in tallies]}")
    if tallies[0].hold_ms != 1000:
        raise SystemExit(f"按住时长不对：{tallies[0].hold_ms}")
    if verdict(tallies) != "三个按键全部通过":
        raise SystemExit(f"结论不对：{verdict(tallies)}")
    if key_mask([0, 1, 0]) != 5:
        raise SystemExit("左+右 掩码不对")
    partial = [Tally(presses=2), Tally(), Tally(presses=1)]
    if verdict(partial) != "未通过：中键（没检测到按下）":
        raise SystemExit(f"缺键结论不对：{verdict(partial)}")
    text = report_text("abc123", datetime(2026, 10, 1, 20, 0), datetime(2026, 10, 1, 20, 1), tallies, 3)
    if "左键 GPIO0_A3" not in text or "左+右 同时按住：3 次" not in text or "结论：三个按键全部通过" not in text:
        raise SystemExit("报告内容不对：\n" + text)
    board = parse_probe(
        "GADGET=rockchip\nFUNCS=ffs.adb uvc.gs6\nLINKED=0\nFEEDER=0\nUDC=configured\n"
    )
    if board["LINKED"] != "0" or "uvc.gs6" not in board["FUNCS"]:
        raise SystemExit("探测解析不对")
    lines = uvc_lines(board, ["Integrated Camera|OK"])
    if not any(line.startswith("结论：现在还不能") for line in lines):
        raise SystemExit("缺条件时结论应是不能：" + "\n".join(lines))
    ready = uvc_lines(
        {"GADGET": "rockchip", "FUNCS": "uvc.gs6", "LINKED": "1", "FEEDER": "1", "UDC": "configured"},
        ["Rockchip UVC Camera|OK"],
    )
    if not any("条件齐全" in line for line in ready):
        raise SystemExit("条件齐全时应判定可用：" + "\n".join(ready))
    if windows_cameras() == []:
        raise SystemExit("读不到 Windows 摄像头列表")
    import tempfile
    import tkinter as tk

    with tempfile.TemporaryDirectory() as temporary:
        folder = save_dir(Path(temporary), datetime(2026, 9, 30, 15, 30, 12))
        if folder.name != "2026-09-30":
            raise SystemExit("日期目录不对")
        first = unique_path(folder, "按键测试_200000.txt")
        first.write_text("x", encoding="utf-8")
        if unique_path(folder, "按键测试_200000.txt").name != "按键测试_200000_2.txt":
            raise SystemExit("重名文件没有避开")

    root = tk.Tk()
    root.withdraw()
    app = App(root)
    if len(app.key_cards) != 3:
        raise SystemExit("三键卡片数量不对")
    if "连接画面" not in str(app.connect_btn["text"]):
        raise SystemExit("没有连接按钮")
    app.device_combo.set("abc")
    if app.chosen_serial() != "abc":
        raise SystemExit("设备选择没有生效")
    root.destroy()
    print("ok 三键判定、报告、UVC 探测、界面 全部通过")


def main() -> None:
    import tkinter as tk

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        self_check()
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
