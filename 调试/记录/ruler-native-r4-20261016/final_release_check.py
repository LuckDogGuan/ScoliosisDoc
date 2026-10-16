"""Check immutable release hashes and probe only the native files read from ZIP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release', type=Path, required=True)
parser.add_argument('--assessment', type=Path, required=True)
parser.add_argument('--probe', type=Path, required=True)
parser.add_argument('--workspace', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert not args.output.exists()
record = json.loads((args.release / 'ARCHIVE.json').read_text(encoding='utf-8'))
for field in ('archive', 'installer'):
    assert hashlib.sha256((args.release / record[field]).read_bytes()).hexdigest() == record[field+'_sha256']
assert record['source_commit'] == '7323966ce2a6e5130cf89c7cc3cdbf0cc453f5cd'
runtime = args.workspace / 'build' / 'final-zip-native-probe-3.3.18'
runtime.mkdir(parents=True, exist_ok=False)
with zipfile.ZipFile(args.release / record['archive']) as archive:
    assert set(archive.namelist()) == set(record['files'])
    for name in archive.namelist():
        assert not any(part in ('test-ruler-v1', '__pycache__', 'site-packages') for part in name.split('/')), name
        assert Path(name).suffix.lower() not in ('.jpg', '.jpeg', '.npz', '.py', '.pyc'), name
        assert hashlib.sha256(archive.read(name)).hexdigest() == record['files'][name], name
    for name in ('ruler_signed.dll', 'model.bin', 'manifest.json', 'BUILD.json'):
        (runtime / name).write_bytes(archive.read('thirdPartyLibrary/ruler-signed/'+name))
manifest = json.loads((runtime / 'manifest.json').read_text(encoding='utf-8'))
for name, expected in manifest['files'].items():
    assert hashlib.sha256((runtime / name).read_bytes()).hexdigest() == expected
labels = json.loads((args.assessment / '训练实验_第四轮_最终复核后/labels.json').read_text(encoding='utf-8'))['samples']
environment = dict(os.environ, PATH=str(Path(os.environ['SystemRoot'])/'System32'))
outputs = []
for sample_id, expected_angle in [('V01_f000245_t009017ms', 0.5), ('V04_f000114_t004417ms', None)]:
    sample = next(row for row in labels if row['id'] == sample_id)
    call = subprocess.run([str(args.probe), str(runtime), sample['source_image']], env=environment,
        capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    value = json.loads(call.stdout)
    assert value['angle_deg'] == expected_angle
    if expected_angle is None:
        assert value['reason'] == 8 and value['branch'] == 2
    outputs.append(dict(sample_id=sample_id, output=value))
result = dict(version=record['version'], source_commit=record['source_commit'],
    archive_sha256=record['archive_sha256'], installer_sha256=record['installer_sha256'],
    file_count=len(record['files']), complete_zip_readback=True, training_photos_and_python_environment_absent=True,
    native_files_from_zip=True, system_only_path=environment['PATH'], native_manifest=manifest['files'],
    runtime_manifest_sha256=hashlib.sha256((runtime/'manifest.json').read_bytes()).hexdigest(),
    probe_sha256=hashlib.sha256(args.probe.read_bytes()).hexdigest(), outputs=outputs,
    limitations=['No clean virtual machine tested', 'Installer compiled, not installed over current application'])
args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('outputs','native_manifest')}, ensure_ascii=False))
