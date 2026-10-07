"""Independent OpenCV client: verify the released UVC can be reopened."""
import json
import sys
import time
from pathlib import Path

import cv2
from comtypes import CoInitialize, CoUninitialize, GUID
from pygrabber.dshow_graph import DeviceCategories, IPropertyBag, SystemDeviceEnum

CoInitialize()
devices = []
enumerator = SystemDeviceEnum().system_device_enum.CreateClassEnumerator(
    GUID(DeviceCategories.VideoInputDevice), dwFlags=0)
while True:
    try:
        moniker, count = enumerator.Next(1)
    except (ValueError, AttributeError):
        break
    if not count:
        break
    bag = moniker.BindToStorage(0, 0, IPropertyBag._iid_).QueryInterface(IPropertyBag)
    devices.append({"index": len(devices), "name": bag.Read("FriendlyName", pErrorLog=None),
                    "path": bag.Read("DevicePath", pErrorLog=None).lower()})
CoUninitialize()
target = [d for d in devices if "usb#vid_2207&pid_0016&mi_00#" in d["path"]]
if len(target) != 1:
    raise RuntimeError("Expected exactly one target UVC camera")
capture = cv2.VideoCapture(target[0]["index"], cv2.CAP_DSHOW)
try:
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    start = time.monotonic()
    frames = 0
    while time.monotonic() - start < 5:
        ok, frame = capture.read()
        if not ok or frame is None or not frame.size:
            raise RuntimeError("Independent client failed to receive a frame")
        frames += 1
    result = {"status": "passed", "client": "Independent OpenCV DirectShow process",
              "camera": target[0], "frames": frames, "seconds": time.monotonic() - start,
              "width": frame.shape[1], "height": frame.shape[0]}
    Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
finally:
    capture.release()
