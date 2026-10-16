"""Compare the native R4 DLL with frozen Python fixtures; never change source data."""
from pathlib import Path
import argparse
import copy
import ctypes as C
import hashlib
import json
import math
import platform
import shutil
import struct
import sys
import time
import uuid

import cv2
import numpy as np
from PIL import Image

REASONS = {
    'ok': 0, 'image_size_mismatch': 1, 'exposure_or_image_changed': 2,
    'right_shadow_not_resolved': 3, 'outside_calibrated_right_edge': 4,
    'ambiguous_angle_at_same_edge': 5, 'nonmonotonic_calibration': 6,
    'left_shadow_outside_reference_appearance': 7, 'left_neighbors_disagree': 8,
    'ok_local_shadow_match_experimental': 9,
}
BRANCHES = {'input_rejected': 0, 'right_edge': 1, 'left_shadow': 2, 'right_edge_rejected': 3}


class Result(C.Structure):
    _fields_ = [('status', C.c_int32), ('reason', C.c_int32), ('branch', C.c_int32),
                ('reserved', C.c_int32), ('angle', C.c_double), ('point_x', C.c_double),
                ('point_y', C.c_double), ('elapsed_ms', C.c_double)]


class Guid(C.Structure):
    _fields_ = [('data1', C.c_uint32), ('data2', C.c_uint16), ('data3', C.c_uint16), ('data4', C.c_ubyte * 8)]


def guid(value):
    return Guid.from_buffer_copy(uuid.UUID(value).bytes_le)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wic_gray(path):
    """Independently exercise the system RGB decoder and the exact libpng mapping."""
    ptr, uint, hr = C.c_void_p, C.c_uint32, C.c_long
    ole, wic = C.OleDLL('ole32'), C.WinDLL('windowscodecs')
    ole.CoInitializeEx.argtypes, ole.CoInitializeEx.restype = [ptr, uint], hr
    ole.CoCreateInstance.argtypes = [C.POINTER(Guid), ptr, uint, C.POINTER(Guid), C.POINTER(ptr)]
    ole.CoCreateInstance.restype = hr
    wic.WICConvertBitmapSource.argtypes = [C.POINTER(Guid), ptr, C.POINTER(ptr)]
    wic.WICConvertBitmapSource.restype = hr

    def check(code):
        if code < 0:
            raise OSError(f'WIC HRESULT {code & 0xffffffff:08x}')

    def method(obj, slot, args, *values):
        table = C.cast(obj, C.POINTER(C.POINTER(ptr))).contents
        return C.WINFUNCTYPE(hr, ptr, *args)(table[slot])(obj, *values)

    initialized = ole.CoInitializeEx(None, 0)
    if initialized != -2147417850:  # RPC_E_CHANGED_MODE: use the existing apartment.
        check(initialized)
    factory, decoder, frame, source = ptr(), ptr(), ptr(), ptr()
    try:
        check(ole.CoCreateInstance(C.byref(guid('cacaf262-9370-4615-a13b-9f5539da4c0a')), None, 1,
                                  C.byref(guid('ec5ec8a9-c395-4314-9c77-54d7a935ff70')), C.byref(factory)))
        check(method(factory, 3, [C.c_wchar_p, ptr, uint, uint, C.POINTER(ptr)], str(path), None,
                     0x80000000, 0, C.byref(decoder)))
        check(method(decoder, 13, [uint, C.POINTER(ptr)], 0, C.byref(frame)))
        width, height = uint(), uint()
        check(method(frame, 3, [C.POINTER(uint), C.POINTER(uint)], C.byref(width), C.byref(height)))
        check(wic.WICConvertBitmapSource(C.byref(guid('6fddc324-4e03-4bfe-b185-3d77768dc90d')),
                                        frame, C.byref(source)))
        size = width.value * height.value * 3
        buffer = (C.c_ubyte * size)()
        check(method(source, 7, [ptr, uint, uint, ptr], None, width.value * 3, size, C.cast(buffer, ptr)))
        rgb = np.ctypeslib.as_array(buffer).reshape(height.value, width.value, 3).astype(np.uint32)
        return ((9797 * rgb[:, :, 0] + 19234 * rgb[:, :, 1] + 3737 * rgb[:, :, 2]) >> 15).astype(np.uint8)
    finally:
        for obj in (source, frame, decoder, factory):
            if obj:
                method(obj, 2, [])
        if initialized >= 0:
            ole.CoUninitialize()


def bind(path):
    dll = C.CDLL(str(path))
    dll.rs_abi_version.argtypes, dll.rs_abi_version.restype = [], C.c_int32
    dll.rs_load_w.argtypes, dll.rs_load_w.restype = [C.c_wchar_p, C.POINTER(C.c_void_p)], C.c_int32
    dll.rs_analyze_png_w.argtypes = [C.c_void_p, C.c_wchar_p, C.POINTER(Result)]
    dll.rs_analyze_png_w.restype = C.c_int32
    dll.rs_analyze_gray8.argtypes = [C.c_void_p, C.POINTER(C.c_ubyte), C.c_int32, C.c_int32, C.c_int32, C.POINTER(Result)]
    dll.rs_analyze_gray8.restype = C.c_int32
    dll.rs_free.argtypes, dll.rs_free.restype = [C.c_void_p], None
    assert dll.rs_abi_version() == 1 and C.sizeof(Result) == 48
    return dll


def load(dll, path):
    context = C.c_void_p()
    code = dll.rs_load_w(str(path), C.byref(context))
    assert code == 0 and context.value, (str(path), code)
    return context


def analyze(dll, context, gray=None, path=None):
    result = Result()
    if path is not None:
        status = dll.rs_analyze_png_w(context, str(path), C.byref(result))
    else:
        assert gray.flags.c_contiguous and gray.dtype == np.uint8
        h, w = gray.shape
        status = dll.rs_analyze_gray8(context, gray.ctypes.data_as(C.POINTER(C.c_ubyte)), w, h, w, C.byref(result))
    assert status == result.status and result.reserved == 0
    assert math.isfinite(result.elapsed_ms) and result.elapsed_ms >= 0
    return result


def compare(actual, expected, key):
    value = expected['angle_deg']
    assert actual.status == (1 if value is None else 0), (key, 'status', actual.status, expected)
    assert actual.reason == REASONS[expected['reason']], (key, 'reason', actual.reason, expected)
    assert actual.branch == BRANCHES[expected['branch']], (key, 'branch', actual.branch, expected)
    if value is None:
        assert math.isnan(actual.angle), (key, 'rejected angle is not NaN')
    else:
        assert abs(actual.angle - value) <= 0.001, (key, 'angle', actual.angle, value)
    point = expected.get('point')
    if point is None:
        assert math.isnan(actual.point_x) and math.isnan(actual.point_y), (key, 'missing point')
    else:
        assert abs(actual.point_x - point['x']) <= 0.001 and abs(actual.point_y - point['y']) <= 0.001, (key, 'point')


def summary(times):
    return dict(count=len(times), p50_ms=float(np.percentile(times, 50)),
                p95_ms=float(np.percentile(times, 95)), max_ms=max(times))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', dest='export_root', type=Path, required=True)
    parser.add_argument('--dll', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export, output = args.export_root.resolve(), args.output.resolve()
    if output.exists():
        parser.error('Output must not exist; preserve earlier verification evidence')
    reference = json.loads((export / 'reference.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=False)
    dll = bind(args.dll.resolve())
    images, fixtures = {}, {}
    for row in reference['rows']:
        if row['id'] in images:
            continue
        path = Path(row['source_image'])
        assert sha(path) == row['source_sha256']
        gray = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 0)
        assert gray.shape == (1080, 1280) and hashlib.sha256(gray.tobytes()).hexdigest() == row['gray_sha256']
        assert np.array_equal(wic_gray(path), gray), ('WIC gray mismatch', row['id'])
        images[row['id']], fixtures[row['id']] = gray, row
    matches, native_times, call_times, png_times = [], [], [], []
    for name in sorted({r['model'] for r in reference['rows']}):
        manifest = json.loads((export / name / 'manifest.json').read_text(encoding='utf-8'))
        assert sha(export / name / 'model.bin') == manifest['files']['model.bin']
        context = load(dll, export / name / 'model.bin')
        try:
            for row in (r for r in reference['rows'] if r['model'] == name):
                gray = analyze(dll, context, gray=images[row['id']])
                png = analyze(dll, context, path=Path(row['source_image']))
                compare(gray, row['expected'], (name, row['id'], 'gray'))
                compare(png, row['expected'], (name, row['id'], 'png'))
                assert (gray.status, gray.reason, gray.branch) == (png.status, png.reason, png.branch)
                if gray.status == 0:
                    assert gray.angle == png.angle, (name, row['id'], 'gray and PNG native outputs differ')
                matches.append(dict(model=name, id=row['id'], angle=None if png.status else png.angle,
                                    status=png.status, reason=png.reason, branch=png.branch,
                                    absolute_difference_deg=None if png.status else abs(png.angle-row['expected']['angle_deg'])))
            if name == 'full':
                rows = [r for r in reference['rows'] if r['model'] == name]
                for i in range(186):
                    start = time.perf_counter()
                    result = analyze(dll, context, gray=images[rows[i % 62]['id']])
                    call_times.append((time.perf_counter() - start) * 1000)
                    native_times.append(result.elapsed_ms)
                for i in range(62):
                    start = time.perf_counter()
                    analyze(dll, context, path=rows[i]['source_image'])
                    png_times.append((time.perf_counter() - start) * 1000)
        finally:
            dll.rs_free(context)
    assert len(matches) == 124
    # All malformed payloads overwrite only this newly-created, explicit test file.
    original = (export / 'full' / 'model.bin').read_bytes()
    badpath = output / '坏模型.bin'
    cases = {'truncated': original[:-1], 'trailing': original + b'\0', 'magic': b'INVALID!' + original[8:]}
    for key, offset, value in [('version', 8, 2), ('width', 12, 640), ('baseline_width', 20, 501),
                               ('anchors_zero', 36, 0), ('refs_zero', 40, 0), ('reserved', 44, 1)]:
        data = bytearray(original)
        struct.pack_into('<I', data, offset, value)
        cases[key] = bytes(data)
    for key, offset in [('brightness_nan', 48), ('distance_nan', 56), ('span_nan', 64), ('anchor_nan', 300072)]:
        data = bytearray(original)
        struct.pack_into('<d', data, offset, math.nan)
        cases[key] = bytes(data)
    nanchors = struct.unpack_from('<I', original, 36)[0]
    nrefs = struct.unpack_from('<I', original, 40)[0]
    for key, offset, format_code in [('feature_nan', 300072 + nanchors * 16, '<f'),
            ('label_nan', 300072 + nanchors * 16 + nrefs * 10752 * 4, '<d')]:
        data = bytearray(original)
        struct.pack_into(format_code, data, offset, math.nan)
        cases[key] = bytes(data)
    malformed = []
    for name, data in cases.items():
        badpath.write_bytes(data)
        pointer = C.c_void_p()
        code = dll.rs_load_w(str(badpath), C.byref(pointer))
        if pointer.value:
            dll.rs_free(pointer)
        assert code < 0 and not pointer.value, (name, code)
        malformed.append(dict(case=name, status=code))
    context = load(dll, export / 'full' / 'model.bin')
    input_checks = []
    try:
        for name, size, color in [('black', (1280, 1080), 0), ('white', (1280, 1080), 255), ('wrong_size', (640, 480), 127)]:
            path = output / f'{name}.png'
            Image.new('RGB', size, (color, color, color)).save(path)
            result = analyze(dll, context, path=path)
            assert result.status != 0 and math.isnan(result.angle), (name, result.status)
            input_checks.append(dict(case=name, status=result.status, reason=result.reason))
        path = output / '非图片.png'
        path.write_bytes(b'not a png')
        for name, source in [('corrupt_png', path), ('missing_png', output / 'missing.png')]:
            result = analyze(dll, context, path=source)
            assert result.status < 0
            input_checks.append(dict(case=name, status=result.status, reason=result.reason))
        unicode_path = output / '中文 空格 帧.png'
        first = next(iter(fixtures.values()))
        shutil.copyfile(first['source_image'], unicode_path)
        compare(analyze(dll, context, path=unicode_path),
                next(r['expected'] for r in reference['rows'] if r['model'] == 'full' and r['id'] == first['id']), 'unicode path')
        for name, w, h, stride, pointer in [('null_gray', 1280, 1080, 1280, None),
                ('bad_stride', 1280, 1080, 1279, next(iter(images.values())).ctypes.data_as(C.POINTER(C.c_ubyte))),
                ('wrong_gray_size', 640, 480, 640, next(iter(images.values())).ctypes.data_as(C.POINTER(C.c_ubyte)))]:
            result = Result()
            status = dll.rs_analyze_gray8(context, pointer, w, h, stride, C.byref(result))
            assert status != 0 and result.status == status
            input_checks.append(dict(case=name, status=status, reason=result.reason))
        dll.rs_free(None)
        for name, invoke in [('null_context', lambda: dll.rs_analyze_png_w(None, str(unicode_path), C.byref(Result()))),
                             ('null_result', lambda: dll.rs_analyze_png_w(context, str(unicode_path), None))]:
            status = invoke()
            assert status < 0
            input_checks.append(dict(case=name, status=status))
    finally:
        dll.rs_free(context)
    # Frozen data does not exercise these branches; legal synthetic calibrations do.
    from ruler_native_export import encode
    metadata = json.loads((export / 'full' / 'manifest.json').read_text(encoding='utf-8'))
    reference_base = next(Path(p).parent.parent for p in metadata['algorithm_sources_sha256']
                          if Path(p).name == 'train_reader.py')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(reference_base / '训练实验_第二轮'))
    from segmented_reader import SignedReader
    full = SignedReader.load(reference_base / '训练实验_第四轮_最终复核后')
    right_row = max((r for r in reference['rows'] if r['model'] == 'full' and
                     r['expected'].get('point') is not None and r['expected']['angle_deg'] is not None),
                    key=lambda r: r['expected']['point']['x'])
    x = right_row['expected']['point']['x']
    assert x >= 300
    diagnostic_checks = []
    for reason, anchors in [(5, [(100.0, 0.0, 'start'), (x, 9.0, 'conflict-a'),
                                (x, 11.0, 'conflict-b'), (1100.0, 12.0, 'end')]),
                            (6, [(100.0, 0.0, 'start'), (500.0, 2.0, 'peak'), (1100.0, 0.0, 'end')])]:
        model = copy.copy(full)
        model.right = copy.copy(full.right)
        model.right.anchors = anchors
        expected = model.predict(images[right_row['id']])
        assert REASONS[expected['reason']] == reason and expected['branch'] == 'right_edge_rejected'
        folder = output / f'synthetic-reason-{reason}'
        folder.mkdir()
        (folder / 'model.bin').write_bytes(encode(model))
        (folder / 'expected.json').write_text(json.dumps(dict(source_id=right_row['id'], anchors=anchors,
            expected=expected, purpose='Diagnostic branch equivalence only; not training or accuracy data'),
            ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        context = load(dll, folder / 'model.bin')
        try:
            for interface in ('gray', 'png'):
                actual = analyze(dll, context, gray=images[right_row['id']]) if interface == 'gray' else \
                    analyze(dll, context, path=right_row['source_image'])
                compare(actual, expected, ('synthetic', reason, interface))
            diagnostic_checks.append(dict(reason=reason, branch=3, status=1, interfaces=['gray', 'png'],
                                          model_sha256=sha(folder / 'model.bin')))
        finally:
            dll.rs_free(context)
    assert reference['protected_input_sha256'] == {p: sha(p) for p in reference['protected_input_sha256']}
    report = dict(dll_sha256=sha(args.dll), verifier_sha256=sha(Path(__file__)),
        wic_exact_gray_matches=len(images), full_matches=62, holdout_matches=62,
        angle_tolerance_deg=0.001, status_reason_branch_exact=True, matches=matches,
        max_abs_angle_difference_deg=max(r['absolute_difference_deg'] for r in matches if r['absolute_difference_deg'] is not None),
        png_gray_output_exact_matches=124,
        native_core_benchmark=summary(native_times), gray_dll_call_benchmark=summary(call_times),
        png_decode_and_dll_call_benchmark=summary(png_times), malformed_models=malformed,
        input_checks=input_checks, unicode_path_passed=True, protected_inputs_unchanged=True,
        synthetic_diagnostic_checks=diagnostic_checks,
        opencv_version=cv2.__version__, numpy_version=np.__version__,
        machine=dict(os=platform.platform(), architecture=platform.machine(), processor=platform.processor()),
        scope='PC native migration equivalence and timing; excludes video extraction, UI, camera, network; no independent accuracy claim')
    (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('matches', 'malformed_models', 'input_checks')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
