"""Reuse the verified complete-directory packaging check for Flutter 3.3.4."""
from pathlib import Path

source = Path(__file__).parent.parent / 'realboard-20261009/package_flutter.py'
script = source.read_text(encoding='utf-8').replace('3.3.3', '3.3.4')
exec(compile(script, str(source), 'exec'), {'__file__': __file__, '__name__': '__main__'})
