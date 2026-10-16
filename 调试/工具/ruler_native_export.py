"""Export the frozen R4 model and independently reconstructed video folds to C data."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import sys

import numpy as np

HEADER = struct.Struct('<8s10I3d')
MAGIC = b'RSR4BIN1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def encode(model):
    baseline = np.asarray(model.right.baseline, dtype=np.uint8)
    white = np.asarray(model.right.white, dtype=np.uint8)
    features = np.asarray(model.left_features, dtype='<f4')
    angles = np.asarray(model.left_y, dtype='<f8')
    anchors = np.asarray([(a[0], a[1]) for a in model.right.anchors], dtype='<f8')
    assert baseline.shape == white.shape == (300, 500)
    assert features.shape == (len(angles), 96 * 112)
    assert 1 <= len(angles) <= 62 and 2 <= len(anchors) <= 62
    assert anchors.shape == (len(anchors), 2)
    assert all(np.isfinite(a).all() for a in (features, angles, anchors))
    assert np.all(np.diff(anchors[:, 0]) >= 0) and set(np.unique(white)) <= {0, 1}
    assert np.isfinite(model.right.reference_brightness) and np.isfinite(model.distance_limit)
    header = HEADER.pack(MAGIC, 1, 1280, 1080, 500, 300, 96, 112,
                         len(anchors), len(angles), 0,
                         model.right.reference_brightness, model.distance_limit, 1.0)
    data = header + b''.join(a.tobytes(order='C') for a in (baseline, white, anchors, features, angles))
    assert len(data) == HEADER.size + 300000 + len(anchors) * 16 + len(angles) * (10752 * 4 + 8)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dll', type=Path, help='Optional built DLL to include in each exported model folder')
    args = parser.parse_args()
    base, output = args.data_root.resolve(), args.output.resolve()
    if output.exists():
        parser.error('Output must not exist; preserve prior exports')
    if args.dll is not None and not args.dll.is_file():
        parser.error('DLL does not exist')
    frozen = base / '训练实验_第四轮_最终复核后'
    sources = [base / '训练实验_第一轮' / 'train_reader.py',
               base / '训练实验_第二轮' / 'segmented_reader.py']
    meta = json.loads((frozen / 'signed-model.json').read_text(encoding='utf-8'))
    for name, expected in meta['algorithm_sources_sha256'].items():
        assert sha(name) == expected, f'Frozen source changed: {name}'
    samples = json.loads((frozen / 'labels.json').read_text(encoding='utf-8'))['samples']
    original = json.loads((frozen / 'training-results.json').read_text(encoding='utf-8'))
    assert len(samples) == len({r['id'] for r in samples}) == 62
    protected = [frozen / n for n in ('labels.json', 'signed-model.json', 'signed-model.npz', 'training-results.json')]
    protected += sources + [Path(r['source_image']) for r in samples]
    before = {str(p): sha(p) for p in protected}
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(base / '训练实验_第二轮'))
    from segmented_reader import SignedReader, image
    images = {r['id']: image(r['source_image']) for r in samples}
    assert all(sha(r['source_image']) == r['image_sha256'] for r in samples)
    expected = {r['id']: r for r in original['predictions']}
    models = [('full', SignedReader.load(frozen), samples, samples)]
    for video in sorted({r['video_id'] for r in samples}):
        train = [r for r in samples if r['video_id'] != video]
        test = [r for r in samples if r['video_id'] == video]
        assert not {r['image_sha256'] for r in train} & {r['image_sha256'] for r in test}
        models.append((f'fold-{video}', SignedReader(train, [images[r['id']] for r in train]), train, test))
    references = []
    payloads = []
    for name, model, train, test in models:
        data = encode(model)
        for row in test:
            predicted = model.predict(images[row['id']])
            if name != 'full':
                stored = expected[row['id']]
                assert set(stored['train_ids']) == {r['id'] for r in train}
                for key, value in predicted.items():
                    # JSON stores ROI tuples as lists; normalize before comparison.
                    assert json.loads(json.dumps(value)) == stored[key], (name, row['id'], key)
            references.append(dict(model=name, id=row['id'], source_image=row['source_image'],
                source_sha256=row['image_sha256'], gray_sha256=hashlib.sha256(images[row['id']].tobytes()).hexdigest(),
                video_id=row['video_id'], human_angle_deg=row['angle_deg'], expected=predicted))
        manifest = dict(schema='ruler-signed-native-manifest-v1', binary_format='RSR4BIN1', abi_version=1,
            schema_version=1, algorithm_version='ruler-signed-r4-native-v1',
            files={'model.bin': hashlib.sha256(data).hexdigest()},
            model_version=meta['version'], model_scope=name, image_size=[1280, 1080],
            baseline_size=[500, 300], left_feature_size=[96, 112],
            nanchors=len(model.right.anchors), nrefs=len(model.left_y),
            bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
            right_brightness=model.right.reference_brightness, left_distance_limit=model.distance_limit,
            max_neighbor_span_deg=1.0, training_ids=[r['id'] for r in train],
            reference_ids=[r['id'] for r in model.left_samples],
            source_model_sha256=sha(frozen / 'signed-model.npz'), source_labels_sha256=sha(frozen / 'labels.json'),
            algorithm_sources_sha256={str(p): sha(p) for p in sources},
            grayscale='RGB8: (9797*R + 19234*G + 3737*B) >> 15; no gamma or rounding',
            accuracy_scope='Same-session development validation; full-model self matches are not accuracy evidence')
        payloads.append((name, data, manifest))
    assert len(references) == 124
    assert before == {str(p): sha(p) for p in protected}, 'Historical inputs changed'
    output.mkdir(parents=True, exist_ok=False)
    for name, data, manifest in payloads:
        folder = output / name
        folder.mkdir()
        (folder / 'model.bin').write_bytes(data)
        if args.dll is not None:
            shutil.copyfile(args.dll, folder / 'ruler_signed.dll')
            manifest['files']['ruler_signed.dll'] = sha(folder / 'ruler_signed.dll')
        dump(folder / 'manifest.json', manifest)
    dump(output / 'reference.json', dict(schema='ruler-signed-native-reference-v1', rows=references,
         protected_input_sha256=before, exporter_sha256=sha(Path(__file__)),
         numpy_version=np.__version__, reconstructed_holdout_predictions_match=62,
         model_count=5, full_model_rows=62, holdout_rows=62))
    print(json.dumps(dict(output=str(output), models=5, full_rows=62, heldout_rows=62,
                         reconstructed_holdout_matches=62), ensure_ascii=False))


if __name__ == '__main__':
    main()
