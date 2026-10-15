"""Calibrate/evaluate the authoritative C reader; never rewrite source photographs."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import time

import cv2
import numpy as np


REASONS = {
    'ok': '已定位', 'shadow_not_resolved': '暗影不可可靠分辨',
    'outside_calibrated_path': '超出可用标定轨迹', 'shadow_off_path': '暗影偏离标定轨迹',
    'mount_or_image_changed': '安装或图像发生变化', 'ambiguous_shadows': '存在多个可疑暗影',
    'image_size_mismatch': '图像尺寸与标定不一致', 'exposure_changed': '曝光变化超出范围',
    'insufficient_contrast': '对比度不足',
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')


def images(root):
    return sorted((p for p in root.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png')),
                  key=lambda p: float(p.stem))


def read_gray(path):
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f'Unreadable image: {path}')
    return image


def run_frames(reader, profile, frames):
    process = subprocess.Popen([str(reader), str(profile), '--stream'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    results = []
    try:
        for image in frames:
            process.stdin.write(image.tobytes())
            process.stdin.flush()
            line = process.stdout.readline().decode('utf-8')
            if not line.startswith('ANGLE_RESULT_JSON '):
                raise RuntimeError(f'Reader failed: {line}')
            results.append(json.loads(line.split(' ', 1)[1]))
        process.stdin.close()
        if process.wait(timeout=10) != 0:
            raise RuntimeError(process.stderr.read().decode('utf-8', 'replace'))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()
    return results


def calibrate(args):
    paths = images(args.references)
    if len(paths) < 3:
        raise ValueError('Need at least three reference photographs')
    frames = [read_gray(p) for p in paths]
    stack = np.stack(frames)
    h, w = stack.shape[1:]
    background = np.percentile(stack, 95, axis=0).astype(np.uint8)
    # This automatic mask applies only to this fixed backlit mount. Recalibrate after optical changes.
    mask = background > 180
    mask[:max(1, round(h * 25 / 480))] = False
    gradient = cv2.magnitude(cv2.Sobel(background, cv2.CV_32F, 1, 0),
                             cv2.Sobel(background, cv2.CV_32F, 0, 1))
    anchors = np.flatnonzero((~mask) & (background > 15) & (background < 175)
                             & (stack.std(axis=0) < 4) & (gradient > 8))[::3]
    if len(anchors) < 30:
        raise ValueError('Not enough stable mount anchors; collect fixed-mount references')
    anchors = anchors[:16000]
    provenance = [{'file': p.name, 'manual_angle_deg': float(p.stem),
                   'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    version = 'manual-' + hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()[:16]
    profile = dict(schema_version=1, calibration_version=version, width=w, height=h,
                   min_area=max(100, round(w*h*100/(640*480))), max_anchor_error=8,
                   min_gain=0.6, max_gain=1.8, max_path_distance=8,
                   label_status='manual_unverified', device_id=args.device_id,
                   intended_range='full_physical_range_pending_capture', reference_images=provenance,
                   background=background.ravel().tolist(), mask_indices=np.flatnonzero(mask).tolist(),
                   anchor_indices=anchors.tolist(),
                   nodes=[dict(angle_deg=-180, x=0, y=0, usable=True),
                          dict(angle_deg=180, x=w-1, y=0, usable=True)])
    args.output.mkdir(parents=True, exist_ok=False)
    scratch = args.output / 'calibration-draft.json'
    write_json(scratch, {**profile, 'label_status': 'draft_not_for_use',
                         'device_id': 'UNBOUND-INTERNAL-DRAFT'})
    positions = run_frames(args.reader, scratch, frames)
    nodes = []
    for p, result in zip(paths, positions):
        usable = result['area'] >= profile['min_area'] and result['reason'] not in (
            'ambiguous_shadows', 'mount_or_image_changed', 'exposure_changed', 'insufficient_contrast')
        x, y = result['point']
        nodes.append(dict(angle_deg=float(p.stem), x=x, y=y, usable=usable, area=result['area']))
    # Refuse indistinguishable positions; never force monotonicity by moving measured points.
    for i in range(1, len(nodes)):
        if nodes[i-1]['usable'] and nodes[i]['usable'] and nodes[i]['x'] - nodes[i-1]['x'] < 1:
            nodes[i-1]['usable'] = nodes[i]['usable'] = False
    profile['nodes'] = nodes
    write_json(args.output / 'calibration.json', profile)
    write_json(args.output / 'reference_positions.json', nodes)
    # Final background and measured reference_positions retain the evidence; discard only our own scratch file.
    scratch.unlink()
    print(json.dumps(dict(profile=str(args.output / 'calibration.json'), nodes=nodes), ensure_ascii=False))


def overlay(image, result, label):
    canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if result['area']:
        point = tuple(round(v) for v in result['point'])
        cv2.drawMarker(canvas, point, (0, 255, 255), cv2.MARKER_CROSS, 22, 2)
    text = (f"angle={result['angle_deg']:.2f} deg" if result['valid'] else f"UNREADABLE: {result['reason']}")
    cv2.rectangle(canvas, (0, image.shape[0]-52), (image.shape[1], image.shape[0]), (0, 0, 0), -1)
    cv2.putText(canvas, text, (8, image.shape[0]-29), cv2.FONT_HERSHEY_SIMPLEX, .55,
                (0, 255, 0) if result['valid'] else (0, 180, 255), 1, cv2.LINE_AA)
    cv2.putText(canvas, f'manual label: {label:+.1f} deg (unverified)', (8, image.shape[0]-9),
                cv2.FONT_HERSHEY_SIMPLEX, .48, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


def evaluate(args):
    profile = json.loads(args.profile.read_text(encoding='utf-8-sig'))
    paths = images(args.tests)
    frames = [read_gray(p) for p in paths]
    if any(im.shape != (profile['height'], profile['width']) for im in frames):
        raise ValueError('Test image size differs from calibration; do not resize implicitly')
    args.output.mkdir(parents=True, exist_ok=False)
    results = run_frames(args.reader, args.profile, frames)
    rows, montage = [], []
    for p, image, result in zip(paths, frames, results):
        label = float(p.stem)
        difference = result['angle_deg']-label if result['valid'] else None
        rows.append(dict(file=p.name, manual_label_deg=label, difference_from_manual_deg=difference, **result))
        marked = overlay(image, result, label)
        cv2.imencode('.png', marked)[1].tofile(str(args.output / (p.stem+'.png')))
        montage.append(marked)
    if montage:
        cv2.imencode('.png', np.vstack(montage))[1].tofile(str(args.output/'test-contact-sheet.png'))
    # Native-only timing: repeated in one persistent process, including valid and rejected samples.
    timings = run_frames(args.reader, args.profile, frames*25)
    ms = [r['processing_ms'] for r in timings]
    perturbations = []
    source = frames[next((i for i, r in enumerate(results) if r['valid']), 0)]
    cases = {
        'blur_sigma_5': cv2.GaussianBlur(source, (0, 0), 5),
        'brightness_70_percent': np.clip(source.astype(float)*.7, 0, 255).astype(np.uint8),
        'translate_12_pixels': cv2.warpAffine(source, np.float32([[1, 0, 12], [0, 1, 0]]), (source.shape[1], source.shape[0])),
        'black_frame': np.zeros_like(source),
        'white_frame': np.full_like(source, 255),
    }
    covered=source.copy(); covered[25:260, 180:420]=0; cases['occlusion']=covered
    for name, result in zip(cases, run_frames(args.reader, args.profile, list(cases.values()))):
        perturbations.append(dict(case=name, **result))
    record = dict(label_status='manual_unverified', real_accuracy_verified=False,
                  calibration_version=profile['calibration_version'], tests=rows, perturbations=perturbations,
                  native_processing_ms=dict(p50=float(np.percentile(ms,50)), p95=float(np.percentile(ms,95)), maximum=max(ms)),
                  rtsp_updates_per_second=None, capture_to_display_latency_ms=None,
                  board_runtime_verified=False, reason='Still images and manual labels; not a live or independent accuracy acceptance')
    write_json(args.output/'results.json', record)
    lines = ['# 暗影读数探索验证', '', '**角度标签来自人工读尺，未通过独立精度验证。**', '',
             '| 图片 | 人工标签 | 算法读数 | 与人工标签差值 | 状态 |', '|---|---:|---:|---:|---|']
    for r in rows:
        value = f"{r['angle_deg']:+.3f}°" if r['valid'] else '—'
        delta = f"{r['difference_from_manual_deg']:+.3f}°" if r['valid'] else '—'
        lines.append(f"| {r['file']} | {r['manual_label_deg']:+.1f}° | {value} | {delta} | {REASONS.get(r['reason'],r['reason'])} |")
    lines += ['', f"本机原生核心耗时：p50={np.percentile(ms,50):.3f}ms，p95={np.percentile(ms,95):.3f}ms；不包含取图、解码、网络与显示。",
              '', '开发板运行帧率、RTSP更新频率、拍摄到显示延迟均未由静态图片验证。', '',
              '当前样本不能证明全量程±0.5°；不可见或无法区分的负角度按失败处理，未外推。', '',
              '![逐图定位与读数](test-contact-sheet.png)', '', '完整数值与扰动检查见 results.json。']
    (args.output/'README.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cal = sub.add_parser('calibrate')
    cal.add_argument('--references', type=Path, required=True)
    cal.add_argument('--reader', type=Path, required=True)
    cal.add_argument('--output', type=Path, required=True)
    cal.add_argument('--device-id', default='UNBOUND-EXPLORATORY')
    cal.set_defaults(run=calibrate)
    test = sub.add_parser('evaluate')
    test.add_argument('--profile', type=Path, required=True)
    test.add_argument('--tests', type=Path, required=True)
    test.add_argument('--reader', type=Path, required=True)
    test.add_argument('--output', type=Path, required=True)
    test.set_defaults(run=evaluate)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
