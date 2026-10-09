from pathlib import Path
import hashlib, json

repo = Path('D:/code/Scoliosis/ScoliosisFlutter')
index_path = repo / 'releases/INDEX.json'
index = json.loads(index_path.read_text(encoding='utf-8'))
for name in ['windows-3.3.3-d321f4c-20261009', 'windows-3.3.4-5852c50-20261009']:
    folder = repo / 'releases' / name
    release = json.loads((folder / 'release.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((folder / release['archive']).read_bytes()).hexdigest() == release['archive_sha256']
    for file in release['files']:
        assert hashlib.sha256((folder / 'Release' / file['path']).read_bytes()).hexdigest() == file['sha256']
    directory = f'releases/{name}/Release'
    if not any(item.get('directory') == directory for item in index['artifacts']):
        index['artifacts'].insert(0, {'directory': directory, 'version': release['version'],
            'source_commit': release['source_commit'], 'archive': release['archive'],
            'archive_sha256': release['archive_sha256'],
            'files': {file['path']: file['sha256'] for file in release['files']}})
index['working_source_commit'] = release['source_commit']
index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Release 3.3.3 and 3.3.4 hashes checked and indexed; prior entries preserved.')
