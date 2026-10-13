"""Temporarily unmute the same default endpoint for the restoration phase of a board test."""
import argparse,importlib.util,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--state-file',type=Path,required=True);args=p.parse_args()
module_path=Path(__file__).with_name('windows_audio_fact_test.py')
spec=importlib.util.spec_from_file_location('audio_fact',module_path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=json.loads(args.state_file.read_text(encoding='utf-8'))
endpoint=module.Endpoint()
try:
 print(json.dumps(endpoint.set(False,original['volume'])))
finally:endpoint.close()

