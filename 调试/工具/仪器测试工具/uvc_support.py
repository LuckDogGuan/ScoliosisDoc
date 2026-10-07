"""Official RV1106 UVC test mode, DirectShow capture and the tester UI."""
from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import queue
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

VERSION = "1.0.0"
BOARD_DIR = "/tmp/instrument-uvc-test"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def asset_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def powershell_exe() -> str:
    win = os.environ.get("SystemRoot", os.environ.get("SYSTEMROOT", r"C:\Windows"))
    return str(Path(win) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def shell(core, serial: str, script: str, timeout: int = 15) -> str:
    result = core.invoke_adb("-s", serial, "shell", script, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "设备连接失败")
    return result.stdout


def board_probe(core, serial: str) -> dict:
    script = """printf 'MODEL='; tr -d '\\000' </proc/device-tree/model; echo;
printf 'ARCH='; uname -m;
printf 'SENSORS='; for f in /sys/class/video4linux/v4l-subdev*/name; do cat "$f"; done | grep -Ei 'mia1321|mis0400|isg1321' | tr '\\n' ';'; echo;
printf 'INSTRUMENT='; pidof instrument_app | tr '\\n' ' '; echo;
printf 'LIBROCKIT='; sha256sum /oem/usr/lib/librockit.so 2>/dev/null | cut -d' ' -f1; echo;
printf 'LIBRKAIQ='; sha256sum /oem/usr/lib/librkaiq.so 2>/dev/null | cut -d' ' -f1; echo;
printf 'UVC='; test -d /sys/kernel/config/usb_gadget/rockchip/functions/uvc.gs6 && echo yes || echo no;
printf 'IQ='; test -f /oem/usr/share/iqfiles/mia1321_MIA1321_30IRC-F16.json && echo yes || echo no;
printf 'UDC='; cat /sys/kernel/config/usb_gadget/rockchip/UDC;
"""
    text = shell(core, serial, script)
    result = dict(line.strip().split("=", 1) for line in text.splitlines() if "=" in line)
    if not all(k in result for k in ("MODEL", "ARCH", "SENSORS", "INSTRUMENT", "UVC", "IQ")):
        raise RuntimeError("板端探测不完整，无法确认摄像头状态")
    result.update(serial=serial, checked_at=datetime.now().isoformat(timespec="seconds"))
    return result


def validate_board(board: dict, manifest: dict) -> None:
    if board.get("MODEL") != "Luckfox Pico Zero" or board.get("ARCH") != "armv7l":
        raise RuntimeError("当前组件支持 RV1106 Pico Zero ARM/uClibc 板卡；板型不兼容")
    if not board.get("SENSORS"):
        raise RuntimeError("未识别 ISG1321 传感器。请断电检查摄像头和排线；不能仅凭无画面判断排线故障")
    if board.get("UVC") != "yes" or board.get("IQ") != "yes":
        raise RuntimeError("缺少内核 UVC 功能或 ISG1321 图像配置，不能进入 USB 摄像头模式")
    for key in ("LIBROCKIT", "LIBRKAIQ"):
        if board.get(key) != manifest["board_libraries"][key]:
            raise RuntimeError(f"板端媒体库版本不兼容（{key}）。需要匹配组件，工具不会刷机")


def stop_idle_instrument(core, serial: str) -> None:
    if not shell(core, serial, "pidof instrument_app || true").strip():
        return
    config = json.loads(shell(core, serial, "cat /opt/instrument/config.json"))
    request = {"version": 3, "op": "hello_query", "device_id": config["device_id"],
               "host_id": "instrument-usb-tester", "sequence": 0, "nonce": uuid.uuid4().hex}
    text = shell(core, serial, f"chmod 755 {BOARD_DIR}/udp_query; {BOARD_DIR}/udp_query " +
                 shlex.quote(json.dumps(request, separators=(",", ":"))))
    state = json.loads(text)
    required = ("phase", "gate_enabled", "capture_id", "uploading_capture_id", "audio_busy")
    if (not all(k in state for k in required) or state.get("nonce") != request["nonce"] or
            state.get("device_id") != request["device_id"] or not state.get("ok")):
        raise RuntimeError("无法核实仪器空闲状态，停止测试切换")
    if (state["phase"] not in ("idle", "paired") or state["gate_enabled"] or state["capture_id"] or
            state["uploading_capture_id"] or state["audio_busy"] or state.get("pair_window_remaining_ms", 0)):
        raise RuntimeError("仪器正在录像、上传、播报或已授权拍摄，请结束业务后再测试")
    # SIGTERM follows the firmware's graceful shutdown, including reaping workers.
    shell(core, serial, "killall -TERM instrument_app; "
          "for i in 1 2 3 4 5 6 7 8 9 10; do pidof instrument_app >/dev/null || exit 0; sleep 1; done; exit 20", 13)


def switch_uvc(core, serial: str) -> dict:
    payload = asset_dir() / "payload"
    manifest = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
    board = board_probe(core, serial)
    validate_board(board, manifest)
    # Validate all local bytes before creating any board-side files.
    for name, expected in manifest["files"].items():
        if Path(name).name != name or hashlib.sha256((payload / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("内置 UVC 组件校验失败，停止切换")
    shell(core, serial, f"mkdir -p {BOARD_DIR}")
    # ASCII staging avoids adb.exe's legacy Chinese-path bugs.
    with tempfile.TemporaryDirectory(prefix="instrument-uvc-") as temporary:
        for name in [*manifest["files"], "manifest.json"]:
            staged = Path(temporary) / name
            shutil.copyfile(payload / name, staged)
            result = core.invoke_adb("-s", serial, "push", str(staged), f"{BOARD_DIR}/{name}", timeout=30)
            if result.returncode:
                raise RuntimeError("USB 安装组件失败：" + result.stderr)
    check = " && ".join(f"[ \"$(sha256sum {BOARD_DIR}/{name} | cut -d' ' -f1)\" = '{digest}' ]"
                        for name, digest in manifest["files"].items())
    shell(core, serial, check, 20)
    stop_idle_instrument(core, serial)
    board["instrument_stopped_for_test"] = bool(board.get("INSTRUMENT"))
    # Check again immediately before launching; never terminate instrument_app.
    shell(core, serial, f"if pidof instrument_app >/dev/null; then exit 20; fi; chmod 755 {BOARD_DIR}/rk_mpi_uvc; "
          f"setsid sh {BOARD_DIR}/switch.sh >{BOARD_DIR}/switch.log 2>&1 </dev/null & sleep 1; "
          "echo SWITCH_SCHEDULED", 10)
    return board


def prepare_board_keys(core, serial: str) -> dict:
    board = board_probe(core, serial)
    if board.get("MODEL") != "Luckfox Pico Zero" or board.get("ARCH") != "armv7l":
        raise RuntimeError("三键引脚配置仅适用于 Pico Zero，请确认板型")
    shell(core, serial, f"mkdir -p {BOARD_DIR}")
    with tempfile.TemporaryDirectory(prefix="instrument-keys-") as temporary:
        for name in ("udp_query", "button_inputs.sh"):
            path = Path(temporary) / name
            shutil.copyfile(asset_dir() / "payload" / name, path)
            result = core.invoke_adb("-s", serial, "push", str(path), f"{BOARD_DIR}/{name}", timeout=15)
            if result.returncode:
                raise RuntimeError("按键测试组件安装失败：" + result.stderr)
    stop_idle_instrument(core, serial)
    shell(core, serial, f"sh {BOARD_DIR}/button_inputs.sh")
    board["instrument_stopped_for_test"] = bool(board.get("INSTRUMENT"))
    return board


def cameras() -> list[dict]:
    """Enumerate names AND device paths in OpenCV DirectShow index order."""
    from comtypes import CoInitialize, CoUninitialize, GUID
    from pygrabber.dshow_graph import DeviceCategories, IPropertyBag, SystemDeviceEnum
    CoInitialize()
    try:
        enumerator = SystemDeviceEnum().system_device_enum.CreateClassEnumerator(
            GUID(DeviceCategories.VideoInputDevice), dwFlags=0)
        found = []
        while True:
            try:
                moniker, count = enumerator.Next(1)
            except (ValueError, AttributeError):
                break
            if not count:
                break
            bag = moniker.BindToStorage(0, 0, IPropertyBag._iid_).QueryInterface(IPropertyBag)
            found.append({"index": len(found), "name": bag.Read("FriendlyName", pErrorLog=None).strip(),
                          "path": bag.Read("DevicePath", pErrorLog=None).lower()})
        # UVC has two interfaces: its interface path contains a generated Windows
        # instance ID. Resolve the physical parent's serial instead of guessing.
        script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
                  "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\VID_2207&PID_0016&MI_*' } "
                  "| ForEach-Object { $p=(Get-PnpDeviceProperty -InstanceId $_.InstanceId "
                  "-KeyName DEVPKEY_Device_Parent).Data; $_.InstanceId+'|'+$p }")
        result = subprocess.run([powershell_exe(), "-NoProfile", "-Command", script], capture_output=True,
                                timeout=20, creationflags=CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("读取 Windows USB 父设备身份失败，不能安全选择摄像头")
        parents = {}
        for line in result.stdout.decode("utf-8", "replace").splitlines():
            child, sep, parent = line.strip().lower().partition("|")
            if sep and parent.startswith("usb\\vid_2207&pid_0016\\"):
                parents[child] = parent.rsplit("\\", 1)[-1]
        for camera in found:
            match = re.search(r"(usb)#(vid_2207&pid_0016&mi_00)#([^#]+)#", camera["path"])
            if match:
                instance = "\\".join(match.groups())
                camera["serial"] = parents.get(instance, "")
        return found
    finally:
        CoUninitialize()


def target_cameras(items: list[dict], serial: str = "") -> list[dict]:
    result = [c for c in items if re.search(r"usb#vid_2207&pid_0016(?:&mi_00)?#", c["path"]) and camera_serial(c)]
    if serial:
        result = [c for c in result if camera_serial(c) == serial.lower()]
    return result


def camera_serial(camera: dict) -> str:
    if "&mi_00#" in camera["path"]:
        return camera.get("serial", "")
    match = re.search(r"usb#vid_2207&pid_0016#([^#]+)#", camera["path"])
    if not match:
        raise RuntimeError("无法关联目标 USB 板卡")
    return match.group(1)


def capture_worker(path: str, output, stop) -> None:
    """A killable process bounds a stuck Windows camera open/read call."""
    import cv2
    capture = None
    try:
        matches = [c for c in cameras() if c["path"] == path]
        if len(matches) != 1:
            raise RuntimeError("目标 USB 摄像头已断开或枚举发生变化")
        capture = cv2.VideoCapture(matches[0]["index"], cv2.CAP_DSHOW)
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        capture.set(cv2.CAP_PROP_FPS, 30)
        if not capture.isOpened():
            raise RuntimeError("无法打开目标摄像头；可能被其他软件占用，或相机权限未开启")
        again = cameras()
        index = matches[0]["index"]
        if index >= len(again) or again[index]["path"] != path:
            raise RuntimeError("USB 摄像头枚举已变化，已停止采集，请重新连接")
        first = last = None
        frames = misses = 0
        while not stop.is_set():
            ok, frame = capture.read()
            if not ok or frame is None or not frame.size:
                misses += 1
                if misses >= 8:
                    raise RuntimeError("目标设备已识别，但没有有效画面；请检查板端摄像头服务")
                continue
            misses = 0
            now = time.monotonic()
            first = now if first is None else first
            last = now
            frames += 1
            h, w = frame.shape[:2]
            ratio = min(640 / w, 540 / h)
            display = cv2.resize(frame, (max(1, int(w * ratio)), max(1, int(h * ratio))))
            data = {"kind": "frame", "width": w, "height": h, "frames": frames,
                    "seconds": last - first, "fps": (frames - 1) / (last - first) if last > first else 0,
                    "at": now, "rgb": cv2.cvtColor(display, cv2.COLOR_BGR2RGB)}
            try:
                output.put_nowait(data)
            except queue.Full:
                pass
    except Exception as exc:
        try:
            output.put({"kind": "error", "message": str(exc)}, timeout=0.5)
        except queue.Full:
            pass
    finally:
        if capture is not None:
            capture.release()


class App:
    def __init__(self, root, core) -> None:
        import tkinter as tk
        from tkinter import ttk
        from PIL import Image, ImageTk
        self.root, self.core = root, core
        self.tk, self.Image, self.ImageTk = tk, Image, ImageTk
        self.events = queue.Queue()
        self.busy = self.closing = self.keys_live = False
        self.generation = 0
        self.key_stop = threading.Event()
        self.key_thread = None
        self.camera_process = self.camera_queue = self.camera_stop = None
        self.capture_deadline = 0.0
        self.one_frame = False
        self.board, self.camera_result = {}, {}
        self.session_serial = ""
        self.started = datetime.now()
        self.tallies = [core.Tally() for _ in core.KEYS]
        self.levels = None
        self.combo = 0
        self.last_key_at = 0.0
        self.camera_items = []
        self.status = tk.StringVar(value="插 USB 后点刷新。摄像头与三个按键分模式测试。")
        self.sensor_status = tk.StringVar(value="传感器：未检测")
        self.usb_status = tk.StringVar(value="Windows USB 摄像头：未检测")
        self.frame_status = tk.StringVar(value="实时画面：未检测")
        self.key_status = tk.StringVar(value="未开始；每个键按下并松开一次。")
        root.title(f"仪器测试工具 {VERSION}")
        root.resizable(False, False)
        outer = ttk.Frame(root, padding=12)
        outer.grid()
        top = ttk.Frame(outer)
        top.grid(sticky="ew")
        ttk.Label(top, text="USB 板卡").grid(row=0, column=0)
        self.device_combo = ttk.Combobox(top, width=25, state="readonly")
        self.device_combo.grid(row=0, column=1, padx=8)
        self.device_combo.bind("<<ComboboxSelected>>", self.device_changed)
        self.reload_btn = ttk.Button(top, text="刷新设备", command=self.reload_devices)
        self.reload_btn.grid(row=0, column=2)
        self.report_btn = ttk.Button(top, text="保存报告", command=self.on_save_report)
        self.report_btn.grid(row=0, column=3, padx=8)
        tabs = ttk.Notebook(outer)
        tabs.grid(row=1, column=0, pady=10)
        video = ttk.Frame(tabs, padding=10)
        keys = ttk.Frame(tabs, padding=10)
        tabs.add(video, text=" USB 摄像头 ")
        tabs.add(keys, text=" 三个按键 ")
        row = ttk.Frame(video)
        row.grid(row=0, column=0)
        self.probe_btn = ttk.Button(row, text="检测摄像头连接", command=self.on_probe)
        self.probe_btn.grid(row=0, column=0, padx=4)
        self.switch_btn = ttk.Button(row, text="进入 USB 摄像头模式", command=self.on_switch)
        self.switch_btn.grid(row=0, column=1, padx=4)
        self.connect_btn = ttk.Button(row, text="预览", command=self.on_connect)
        self.connect_btn.grid(row=0, column=2, padx=4)
        self.disconnect_btn = ttk.Button(row, text="停止预览", command=self.on_disconnect)
        self.disconnect_btn.grid(row=0, column=3, padx=4)
        self.preview = ttk.Label(video)
        self.preview.grid(row=1, column=0, pady=10)
        self.blank()
        self.camera_combo = ttk.Combobox(video, width=72, state="readonly")
        self.camera_combo.grid(row=2, column=0)
        self.camera_combo.bind("<<ComboboxSelected>>", self.camera_changed)
        for index, var in enumerate((self.sensor_status, self.usb_status, self.frame_status), 3):
            ttk.Label(video, textvariable=var).grid(row=index, column=0, sticky="w", pady=2)
        ttk.Label(video, text="返回按键测试，请断电重启板卡。停止预览后可用其他软件打开摄像头。",
                  wraplength=640).grid(row=6, column=0, sticky="w", pady=5)
        self.key_cards = []
        for index, spec in enumerate(core.KEYS):
            card = tk.Frame(keys, bg=core.CARD_BG, relief="raised", bd=2, padx=18, pady=12)
            card.grid(row=0, column=index, padx=8)
            tk.Label(card, text=spec.label, bg=core.CARD_BG, font=("", 14)).pack()
            state = tk.Label(card, text="未知", bg=core.CARD_BG, font=("", 22, "bold"))
            state.pack()
            count = tk.Label(card, text="按下 0 次 · 松开 0 次", bg=core.CARD_BG)
            count.pack()
            tk.Label(card, text=spec.short, bg=core.CARD_BG).pack()
            self.key_cards.append((card, state, count))
        row = ttk.Frame(keys)
        row.grid(row=1, column=0, columnspan=3, pady=15)
        self.keys_start_btn = ttk.Button(row, text="开始测试", command=self.on_keys_start)
        self.keys_start_btn.grid(row=0, column=0, padx=4)
        self.keys_stop_btn = ttk.Button(row, text="停止", command=self.on_keys_stop)
        self.keys_stop_btn.grid(row=0, column=1, padx=4)
        self.keys_reset_btn = ttk.Button(row, text="清零", command=self.on_keys_reset)
        self.keys_reset_btn.grid(row=0, column=2, padx=4)
        ttk.Label(keys, textvariable=self.key_status, wraplength=620).grid(row=2, column=0, columnspan=3)
        ttk.Label(outer, textvariable=self.status, wraplength=680).grid(row=2, column=0, sticky="w")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(50, self.tick)
        self.reload_devices()

    def blank(self):
        self.photo = self.ImageTk.PhotoImage(self.Image.new("RGB", (640, 540), (32, 32, 32)))
        self.preview.configure(image=self.photo)

    def task(self, worker, success):
        if self.busy or self.closing:
            return
        self.busy = True
        self.refresh()
        generation = self.generation
        def work():
            try:
                result = worker()
                self.events.put((generation, "done", (success, result)))
            except Exception as exc:
                self.events.put((generation, "error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        locked = self.busy or self.keys_live or self.camera_process is not None or (self.key_thread is not None and self.key_thread.is_alive())
        self.device_combo["state"] = "disabled" if locked else "readonly"
        self.camera_combo["state"] = "disabled" if locked else "readonly"
        for button in (self.reload_btn, self.probe_btn, self.switch_btn, self.connect_btn, self.keys_start_btn, self.keys_reset_btn):
            button["state"] = "disabled" if locked else "normal"
        self.keys_stop_btn["state"] = "normal" if self.keys_live else "disabled"
        self.disconnect_btn["state"] = "normal" if self.camera_process else "disabled"
        self.report_btn["state"] = "disabled" if self.busy else "normal"

    def reset_session(self, serial):
        if serial == self.session_serial:
            return
        self.session_serial = serial
        self.generation += 1
        self.board, self.camera_result = {}, {}
        self.sensor_status.set("传感器：未检测")
        self.usb_status.set("Windows USB 摄像头：未检测")
        self.frame_status.set("实时画面：未检测")
        self.on_keys_reset()
        self.blank()

    def device_changed(self, event=None):
        self.reset_session(self.device_combo.get())

    def camera_changed(self, event=None):
        index = self.camera_combo.current()
        if index >= 0:
            self.reset_session(camera_serial(self.camera_items[index]))
            self.device_combo.set("")

    def reload_devices(self):
        def finish(result):
            devices, available = result
            current = self.device_combo.get()
            self.device_combo["values"] = devices
            chosen = current if current in devices else devices[0] if len(devices) == 1 else ""
            self.device_combo.set(chosen)
            self.set_cameras(available)
            if chosen:
                self.reset_session(chosen)
            elif len(self.camera_items) == 1:
                self.reset_session(camera_serial(self.camera_items[0]))
            self.status.set(f"发现 {len(devices)} 块 USB ADB 板卡、{len(self.camera_items)} 个目标 USB 摄像头。")
        self.task(lambda: (self.core.list_devices(), cameras()), finish)

    def set_cameras(self, available):
        self.camera_items = target_cameras(available)
        self.camera_combo["values"] = [f"{c['name']} · {camera_serial(c)}" for c in self.camera_items]
        wanted = [i for i, c in enumerate(self.camera_items) if camera_serial(c) == self.session_serial]
        if wanted:
            self.camera_combo.current(wanted[0])
        elif len(self.camera_items) == 1:
            self.camera_combo.current(0)
        else:
            self.camera_combo.set("")

    def selected_camera(self):
        index = self.camera_combo.current()
        if index < 0:
            raise RuntimeError("没有选中的目标 USB 摄像头，请先进入摄像头模式并刷新")
        camera = self.camera_items[index]
        if self.session_serial != camera_serial(camera):
            raise RuntimeError("板卡与摄像头身份不一致，请重新选择设备")
        return camera

    def selected_board(self):
        serial = self.device_combo.get().strip()
        if not serial:
            raise RuntimeError("请先选择 USB 板卡；UVC 模式下返回按键测试需断电重启")
        return serial

    def show_board(self, board):
        self.board = board
        sensor = board.get("SENSORS", "").strip(";")
        self.sensor_status.set("传感器：" + (f"已识别 {sensor}" if sensor else "未识别 ISG1321，请断电检查"))

    def on_probe(self):
        serial = self.device_combo.get().strip()
        if serial:
            self.status.set("正在检查传感器和 USB 摄像头…")
            def finish(result):
                board, available = result
                self.show_board(board)
                self.set_cameras(available)
                if target_cameras(available, serial):
                    self.start_capture(one_frame=True)
                else:
                    self.usb_status.set("Windows USB 摄像头：尚未识别目标板卡")
                    self.frame_status.set("实时画面：未检测，需先进入 USB 摄像头模式")
                    self.status.set("传感器识别与实际出图分开判定。可进入 USB 摄像头模式继续检测。")
            self.task(lambda: (board_probe(self.core, serial), cameras()), finish)
        else:
            try:
                self.start_capture(one_frame=True)
            except Exception as exc:
                self.fail(str(exc))

    def on_switch(self):
        try:
            serial = self.selected_board()
        except Exception as exc:
            self.fail(str(exc)); return
        self.status.set("正在核对并安装匹配组件，随后切换 USB 模式…")
        def worker():
            board = switch_uvc(self.core, serial)
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                available = cameras()
                if target_cameras(available, serial):
                    return board, available
                time.sleep(1)
            raise RuntimeError("35 秒内 Windows 未识别目标 UVC。请断电重启恢复 ADB；日志位于板端 /tmp/instrument-uvc-test")
        def finish(result):
            self.show_board(result[0])
            self.set_cameras(result[1])
            self.device_combo.set("")
            self.status.set("已进入 USB 摄像头模式，正在验证出图。返回按键测试，请断电重启板卡。")
            self.start_capture(one_frame=True)
        self.task(worker, finish)

    def on_connect(self):
        try:
            self.start_capture(one_frame=False)
        except Exception as exc:
            self.fail(str(exc))

    def start_capture(self, one_frame):
        camera = self.selected_camera()
        self.one_frame = one_frame
        context = mp.get_context("spawn")
        self.camera_queue = context.Queue(maxsize=2)
        self.camera_stop = context.Event()
        self.camera_process = context.Process(target=capture_worker,
            args=(camera["path"], self.camera_queue, self.camera_stop), daemon=True)
        self.camera_process.start()
        self.capture_deadline = time.monotonic() + 12
        self.usb_status.set(f"Windows USB 摄像头：已识别 {camera['name']}")
        self.frame_status.set("实时画面：等待有效帧…")
        self.refresh()

    def on_disconnect(self):
        if self.camera_process:
            self.camera_stop.set()
            self.camera_process.join(timeout=0.5)
            if self.camera_process.is_alive():
                self.camera_process.terminate()
                self.camera_process.join(timeout=1)
            self.camera_queue.cancel_join_thread()
            self.camera_queue.close()
        self.camera_process = self.camera_queue = self.camera_stop = None
        self.blank()
        self.frame_status.set("实时画面：已停止，摄像头已释放")
        self.refresh()

    def on_keys_start(self):
        if self.key_thread is not None and self.key_thread.is_alive():
            return
        try:
            serial = self.selected_board()
        except Exception as exc:
            self.fail(str(exc)); return
        self.core.use_serial(serial)
        self.key_stop = threading.Event()
        stop = self.key_stop
        self.keys_live = True
        generation = self.generation
        self.last_key_at = time.monotonic()
        self.key_status.set("正在初始化并监听；每个键按下并松开一次。")
        def work():
            try:
                board = prepare_board_keys(self.core, serial)
                self.events.put((generation, "board", board))
                while not stop.is_set():
                    levels = self.core.read_levels()
                    self.events.put((generation, "keys", (levels, time.monotonic(), datetime.now().strftime("%H:%M:%S"))))
                    stop.wait(self.core.POLL_INTERVAL)
            except Exception as exc:
                self.events.put((generation, "keys_error", str(exc)))
        self.key_thread = threading.Thread(target=work, daemon=True)
        self.key_thread.start()
        self.refresh()

    def on_keys_stop(self):
        self.key_stop.set()
        self.generation += 1
        self.keys_live = False
        self.levels = None
        for tally in self.tallies:
            tally.low = tally.armed = False
            tally.since = 0.0
        self.paint_cards()
        self.key_status.set(self.core.verdict(self.tallies) + "；监听已停止")
        self.refresh()

    def on_keys_reset(self):
        self.tallies = [self.core.Tally() for _ in self.core.KEYS]
        self.levels = None
        self.combo = 0
        self.started = datetime.now()
        self.key_status.set("已清零；每个键按下并松开一次。")
        self.paint_cards()

    def paint_cards(self):
        for index, (card, state, count) in enumerate(self.key_cards):
            tally = self.tallies[index]
            low = self.levels is not None and self.levels[index] == 0
            color = self.core.PRESSED_BG if low else self.core.CARD_BG
            card.configure(bg=color)
            state.configure(bg=color, text="未知" if self.levels is None else "按下" if low else "松开")
            hold = max(tally.hold_ms, int((time.monotonic() - tally.since) * 1000)) if low and tally.since else tally.hold_ms
            count.configure(bg=color, text=f"按下 {tally.presses} 次 · 松开 {tally.releases} 次\n最长 {hold} ms")

    def fail(self, message):
        self.status.set(message)
        self.core.log("失败 " + message)
        self.refresh()

    def tick(self):
        if self.closing:
            return
        while True:
            try:
                generation, kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation:
                continue
            if kind in ("done", "error"):
                self.busy = False
                if kind == "done":
                    try:
                        data[0](data[1])
                    except Exception as exc:
                        self.fail(str(exc))
                else:
                    self.fail(data)
                self.refresh()
            elif kind == "board":
                self.show_board(data)
            elif kind == "keys" and self.keys_live:
                levels, now, stamp = data
                previous = self.levels
                self.core.apply_sample(self.tallies, levels, now, stamp)
                if previous is not None and self.core.key_mask(levels) & 5 == 5 and self.core.key_mask(previous) & 5 != 5:
                    self.combo += 1
                self.levels = levels
                self.last_key_at = time.monotonic()
                self.key_status.set(self.core.verdict(self.tallies) + f"；左+右同时按住 {self.combo} 次")
                self.paint_cards()
            elif kind == "keys_error":
                self.on_keys_stop()
                self.key_status.set("连接或读取失败：" + data)
        if self.keys_live and time.monotonic() - self.last_key_at > 10:
            self.on_keys_stop()
            self.key_status.set("按键读取超时，状态已清除，请检查 USB 后重试")
        if self.camera_process:
            try:
                data = self.camera_queue.get_nowait()
            except queue.Empty:
                data = None
            if data:
                if data["kind"] == "error":
                    self.on_disconnect()
                    self.camera_result["status"] = "read_failed"
                    self.frame_status.set("实时画面：失败，已清除旧画面")
                    self.fail(data["message"])
                else:
                    self.capture_deadline = time.monotonic() + 8
                    self.camera_result = {k: v for k, v in data.items() if k != "rgb"}
                    self.camera_result.update(status="frames_received", serial=self.session_serial,
                        checked_at=datetime.now().isoformat(timespec="seconds"))
                    self.photo = self.ImageTk.PhotoImage(self.Image.fromarray(data["rgb"]))
                    self.preview.configure(image=self.photo)
                    self.frame_status.set(f"实时画面：正常 {data['width']}×{data['height']}，实测 {data['fps']:.1f} FPS，{data['frames']} 帧")
                    if self.one_frame:
                        self.on_disconnect()
                        self.frame_status.set("实时画面：检测通过，已收到有效帧；摄像头已释放")
            if self.camera_process and (time.monotonic() > self.capture_deadline or not self.camera_process.is_alive()):
                self.on_disconnect()
                self.camera_result["status"] = "disconnected_or_timeout"
                self.frame_status.set("实时画面：断开或超时，已清除旧画面")
                self.fail("摄像头读取已停止，请刷新设备并检查连接")
        self.refresh()
        self.root.after(50, self.tick)

    def on_save_report(self):
        ended = datetime.now()
        serial = self.session_serial or "未选择设备"
        report = {"tool_version": VERSION, "serial": serial, "started": self.started.isoformat(),
                  "ended": ended.isoformat(), "board": self.board, "camera": self.camera_result,
                  "keys": [{"label": spec.label, "gpio": spec.gpio, **asdict(tally)}
                           for spec, tally in zip(self.core.KEYS, self.tallies)],
                  "keys_verdict": self.core.verdict(self.tallies), "combo": self.combo}
        try:
            folder = self.core.save_dir(self.core.REPORT_ROOT, ended)
            path = self.core.unique_path(folder, ended.strftime("仪器测试_%H%M%S.json"))
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            text = self.core.report_text(serial, self.started, ended, self.tallies, self.combo)
            text += "\n摄像头证据：\n" + json.dumps({"board": self.board, "camera": self.camera_result}, ensure_ascii=False, indent=2)
            path.with_suffix(".txt").write_text(text, encoding="utf-8")
            self.status.set("报告已保存：" + str(path))
        except Exception as exc:
            self.fail("报告保存失败：" + str(exc))

    def on_close(self):
        if self.busy:
            self.status.set("设备操作正在进行，请等待结束后关闭。切换模式后断电重启恢复 ADB。")
            return
        self.closing = True
        self.key_stop.set()
        if self.key_thread:
            self.key_thread.join(timeout=0.5)
        self.on_disconnect()
        self.root.destroy()
