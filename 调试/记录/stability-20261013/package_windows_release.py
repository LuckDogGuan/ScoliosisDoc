"""Archive the complete committed Windows stability release and verify read-back hashes."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,zipfile
parser=argparse.ArgumentParser();parser.add_argument("--version",required=True);args=parser.parse_args()
version=args.version
assert version in {"3.3.6","3.3.7","3.3.8","3.3.9"}
root=Path(r'D:\code\Scoliosis\ScoliosisFlutter')
source=root/'build/windows/x64/runner/Release'
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert (root/'pubspec.yaml').read_text(encoding='utf-8').find('version: '+version+'+20261013')>=0
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True).strip()
runtime=json.loads((root/'thirdPartyLibrary/runtime-manifest.json').read_text(encoding='utf-8'))
for row in runtime['files']:
 file=source/'thirdPartyLibrary'/row['path']
 assert file.stat().st_size==row['bytes'] and hashlib.sha256(file.read_bytes()).hexdigest()==row['sha256']
out=root/('releases/windows-'+version+'-'+head[:7]+'-20261013')
assert not out.exists();out.mkdir()
bundle=out/'Release';shutil.copytree(source,bundle)
files=[]
for file in sorted(source.rglob('*')):
 if not file.is_file():continue
 target=bundle/file.relative_to(source);digest=hashlib.sha256(file.read_bytes()).hexdigest()
 assert digest==hashlib.sha256(target.read_bytes()).hexdigest()
 files.append(dict(path=file.relative_to(source).as_posix(),bytes=file.stat().st_size,sha256=digest))
archive=out/('scoliosis-windows-'+version+'-20261013.zip')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
 for row in files:z.write(bundle/row['path'],row['path'])
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for row in files:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
record=dict(version=version+'+20261013',source_commit=head,source_clean=True,files=files,archive=archive.name,archive_sha256=digest)
(out/'release.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'SHA256SUMS').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
(out/'.gitattributes').write_text('Release/** -text\n*.zip -text\n',encoding='utf-8')
(out/'README.md').write_text('# Windows '+version+' stability\n\nSource: '+head+'\n\nStart Release/scoliosis_flutter.exe with the entire Release directory. Firmware 3.3.9 recommended for query-based capture progress recovery; legacy firmware remains supported. Test evidence is recorded separately.\n',encoding='utf-8')
index_path=root/'releases/INDEX.json';index=json.loads(index_path.read_text(encoding='utf-8'))
index['working_source_commit']=head
index['artifacts'].insert(0,dict(directory=bundle.relative_to(root).as_posix(),version=record['version'],source_commit=head,archive=archive.name,archive_sha256=digest,files={r['path']:r['sha256'] for r in files}))
index_path.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(directory=str(out),files=len(files),bytes=archive.stat().st_size,sha256=digest)))

