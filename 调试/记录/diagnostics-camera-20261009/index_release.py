from pathlib import Path
import hashlib, json

repo = Path('D:/code/Scoliosis/ScoliosisFlutter')
folder = repo / 'releases/windows-3.3.5-956dc97-20261009'
release = json.loads((folder / 'release.json').read_text(encoding='utf-8'))
assert hashlib.sha256((folder / release['archive']).read_bytes()).hexdigest() == release['archive_sha256']
for item in release['files']:
    assert hashlib.sha256((folder / 'Release' / item['path']).read_bytes()).hexdigest() == item['sha256']
index_path = repo / 'releases/INDEX.json'
index = json.loads(index_path.read_text(encoding='utf-8'))
directory = 'releases/windows-3.3.5-956dc97-20261009/Release'
if not any(item.get('directory') == directory for item in index['artifacts']):
    index['artifacts'].insert(0, {'directory':directory, 'version':release['version'],
       'source_commit':release['source_commit'], 'archive':release['archive'],
       'archive_sha256':release['archive_sha256'], 'files':{f['path']:f['sha256'] for f in release['files']}})
index['working_source_commit'] = release['source_commit']
index_path.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('3.3.5 package hashes verified and index updated.')
