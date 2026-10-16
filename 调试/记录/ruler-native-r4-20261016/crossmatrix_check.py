"""Compare every frozen input against all five models, without saving training data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '工具'))
from ruler_native_export import encode
from ruler_native_verify import analyze, bind, compare, load, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--dll', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    reference = json.loads((args.export / 'reference.json').read_text(encoding='utf-8'))
    protected = reference['protected_input_sha256']
    assert all(sha(p) == value for p, value in protected.items())
    frozen = args.data_root / '训练实验_第四轮_最终复核后'
    samples = json.loads((frozen / 'labels.json').read_text(encoding='utf-8'))['samples']
    sys.path.insert(0, str(args.data_root / '训练实验_第二轮'))
    from segmented_reader import SignedReader, image
    images = {row['id']: image(row['source_image']) for row in samples}
    models = [('full', SignedReader.load(frozen))]
    for video in sorted({row['video_id'] for row in samples}):
        train = [row for row in samples if row['video_id'] != video]
        models.append((f'fold-{video}', SignedReader(train, [images[row['id']] for row in train])))
    dll = bind(args.dll)
    rows = []
    for name, model in models:
        binary = args.export / name / 'model.bin'
        assert hashlib.sha256(encode(model)).hexdigest() == sha(binary), name
        context = load(dll, binary)
        try:
            for row in samples:
                expected = model.predict(images[row['id']])
                native = analyze(dll, context, gray=images[row['id']])
                png = analyze(dll, context, path=row['source_image'])
                key = (name, row['id'])
                compare(native, expected, key)
                compare(png, expected, key)
                rows.append(dict(model=name, id=row['id'], source_sha256=row['image_sha256'],
                    expected=expected, status=native.status, reason=native.reason, branch=native.branch,
                    gray_difference_deg=None if expected['angle_deg'] is None else abs(native.angle-expected['angle_deg']),
                    png_difference_deg=None if expected['angle_deg'] is None else abs(png.angle-expected['angle_deg'])))
        finally:
            dll.rs_free(context)
    assert len(rows) == 310
    assert all(sha(p) == value for p, value in protected.items())
    result = dict(dll_sha256=sha(args.dll), script_sha256=sha(__file__), model_count=5,
        source_images=62, model_image_pairs=310, interface_checks=620, angle_tolerance_deg=0.001,
        status_reason_branch_exact=True, protected_inputs_unchanged=True,
        maximum_angle_difference_deg=max(r[k] for r in rows for k in ('gray_difference_deg', 'png_difference_deg') if r[k] is not None),
        scope='Migration equivalence only; includes training inputs and cannot establish independent accuracy', rows=rows)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
