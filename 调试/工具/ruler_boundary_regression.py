"""Reproduce boundary-background blockage with real PNGs and the shipped ABI."""
import argparse
import ctypes as C
import json
import math
from pathlib import Path


class Result(C.Structure):
    _fields_ = [(k, C.c_int32) for k in ('status', 'reason', 'branch', 'reserved')] + [
        (k, C.c_double) for k in ('angle', 'x', 'y', 'ms')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime.resolve()
    lib = C.CDLL(str(root / 'ruler_signed.dll'))
    lib.rs_load_w.argtypes = [C.c_wchar_p, C.POINTER(C.c_void_p)]
    lib.rs_analyze_png_w.argtypes = [C.c_void_p, C.c_wchar_p, C.POINTER(Result)]
    lib.rs_free.argtypes = [C.c_void_p]
    context = C.c_void_p()
    assert lib.rs_load_w(str(root / 'model.bin'), C.byref(context)) == 0
    results = []
    try:
        for name in ('V09_0', 'V09_1', 'V09_2', 'V10_0', 'V10_1', 'V10_2'):
            value = Result()
            status = lib.rs_analyze_png_w(context, str((args.frames / (name + '.png')).resolve()), C.byref(value))
            results.append(dict(image=name, status=status, reason=value.reason, branch=value.branch,
                                angle=value.angle if math.isfinite(value.angle) else None,
                                x=value.x if math.isfinite(value.x) else None,
                                y=value.y if math.isfinite(value.y) else None))
    finally:
        lib.rs_free(context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8', newline='\n')
    for row in results:
        if row['image'] == 'V09_2':
            assert row['status'] == 1 and row['angle'] is None, 'Obscured image must not gain a fabricated angle'
        else:
            assert row['status'] == 0 and row['reason'] == 10 and row['angle'] is not None, row
    print('Boundary recovery regression passed: five estimated readings; obscured frame stays invalid.')


if __name__ == '__main__':
    main()
