"""Inspect this tool's own Tk window and optionally its real UVC preview."""
import json
import multiprocessing as mp
import sys
import time
import tkinter as tk
from pathlib import Path
from PIL import ImageGrab

TOOL = Path(__file__).resolve().parents[2] / "工具" / "仪器测试工具"
sys.path.insert(0, str(TOOL))
import 仪器测试工具 as core


def main():
    root = tk.Tk()
    app = core.App(root, core)
    root.update()
    started = time.monotonic()
    preview_started = False
    def check():
        nonlocal preview_started
        if app.busy:
            if time.monotonic() - started > 30:
                raise RuntimeError("GUI enumeration timed out")
            root.after(100, check); return
        if "--preview" in sys.argv and not preview_started:
            app.on_connect(); preview_started = True
            root.after(6000, check); return
        root.update()
        out = Path(__file__).resolve().parent
        bbox = (root.winfo_rootx(), root.winfo_rooty(), root.winfo_rootx() + root.winfo_width(), root.winfo_rooty() + root.winfo_height())
        ImageGrab.grab(bbox=bbox).save(out / "gui-preview.png")
        result = {"status": app.status.get(), "sensor": app.sensor_status.get(), "usb": app.usb_status.get(),
                  "frame": app.frame_status.get(), "camera": app.camera_result}
        (out / "gui-smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        app.on_close()
    root.after(100, check)
    root.mainloop()


if __name__ == "__main__":
    mp.freeze_support()
    main()
