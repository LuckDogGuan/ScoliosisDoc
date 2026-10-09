"""Archive the complete verified Windows build without touching older releases."""
from pathlib import Path
import hashlib, json, shutil, subprocess, zipfile

repo = Path('D:/code/Scoliosis/ScoliosisFlutter')
commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
assert not subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip()
source = repo / 'build/windows/x64/runner/Release'
dest = repo / f'releases/windows-3.3.3-{commit[:7]}-20261009'
assert not dest.exists(), 'Preserve any existing release; choose a new destination.'
assert (source / 'scoliosis_flutter.exe').is_file()
assert (source / 'thirdPartyLibrary/runtime-manifest.json').is_file()
dest.mkdir(parents=True)
shutil.copytree(source, dest / 'Release')
digest = lambda data: hashlib.sha256(data).hexdigest()
files = []
for file in sorted((dest / 'Release').rglob('*')):
    if not file.is_file(): continue
    relative = file.relative_to(dest / 'Release').as_posix()
    data = file.read_bytes()
    assert data == (source / relative).read_bytes()
    files.append({'path': relative, 'bytes': len(data), 'sha256': digest(data)})
archive = dest / 'scoliosis-windows-3.3.3-20261009.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
    for item in files:
        bundle.write(dest / 'Release' / item['path'], 'Release/' + item['path'])
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    for item in files:
        assert digest(bundle.read('Release/' + item['path'])) == item['sha256']
report = {'version': '3.3.3+20261009', 'source_commit': commit,
          'source_clean': True, 'files': files, 'archive': archive.name,
          'archive_sha256': digest(archive.read_bytes()), 'archive_verified': True}
(dest / 'release.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
(dest / 'SHA256SUMS').write_text(report['archive_sha256'] + '  ' + archive.name + '\n', encoding='utf-8')
(dest / 'README.md').write_text('# Flutter 3.3.3\n\n启动 Release/scoliosis_flutter.exe，保留整个 Release 目录。男女均导出，其他筛选条件保留；历史测试图读数明确标记。旧版本保留，可使用原完整目录回退。\n', encoding='utf-8')
Path(__file__).with_name('flutter-release.json').write_text(json.dumps({k:v for k,v in report.items() if k != 'files'} | {'path': str(dest), 'file_count': len(files)}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'path': str(dest), 'file_count': len(files), 'sha256': report['archive_sha256']}, ensure_ascii=False))
