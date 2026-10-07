"""Repeatable real-device acceptance using the same capture worker as the GUI."""
import json
import multiprocessing as mp
import queue
import time
from pathlib import Path
from datetime import datetime
import uvc_support as u


def run(core, seconds, output, switch=False, validation_reboot=False):
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"started": datetime.now().isoformat(), "requested_seconds": seconds, "status": "starting"}
    proc = messages = stop = None
    def save():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    try:
        if switch:
            devices = core.list_devices()
            if len(devices) != 1:
                raise RuntimeError("实板验收要求仅连接一块 USB ADB 板卡")
            serial = devices[0]
            if validation_reboot:
                delay = int(seconds + 150)
                u.shell(core, serial, f"setsid sh -c 'sleep {delay}; reboot' >/tmp/uvc-validation-reboot.log 2>&1 </dev/null & sleep 1")
            report["board"] = u.switch_uvc(core, serial)
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                found = u.target_cameras(u.cameras(), serial)
                if found:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Windows 未识别目标摄像头")
        else:
            found = u.target_cameras(u.cameras())
            if len(found) != 1:
                raise RuntimeError("实板验收要求仅连接一个目标 UVC 摄像头")
        report["camera"] = found[0]
        ctx = mp.get_context("spawn")
        messages, stop = ctx.Queue(maxsize=2), ctx.Event()
        proc = ctx.Process(target=u.capture_worker, args=(found[0]["path"], messages, stop))
        proc.start()
        first = None
        latest = {}
        started = time.monotonic()
        last = started
        next_save = started
        while first is None or time.monotonic() - first < seconds:
            try:
                data = messages.get(timeout=1)
            except queue.Empty:
                if not proc.is_alive() or time.monotonic() - last > (15 if first is None else 8):
                    raise RuntimeError("采集进程退出或超过读取超时")
                continue
            if data["kind"] == "error":
                raise RuntimeError(data["message"])
            last = time.monotonic()
            if first is None:
                first = last
            latest = {k: v for k, v in data.items() if k != "rgb"}
            report.update(status="running", capture=latest, elapsed=time.monotonic() - first)
            if last >= next_save:
                save(); next_save = last + 10
        report.update(status="passed", elapsed=time.monotonic() - first, capture=latest)
    except Exception as exc:
        report.update(status="failed", error=str(exc))
    finally:
        if proc:
            stop.set(); proc.join(1)
            if proc.is_alive():
                proc.terminate(); proc.join(2)
            messages.cancel_join_thread(); messages.close()
        report["ended"] = datetime.now().isoformat()
        save()
    if report["status"] != "passed":
        raise SystemExit(1)
    return report
