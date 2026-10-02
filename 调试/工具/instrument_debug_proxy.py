"""Compatibility entry; implementation lives in Python中间层/."""
import importlib.util
import pathlib
import sys

path = pathlib.Path(__file__).resolve().parent / 'Python中间层/instrument_debug_proxy.py'
spec = importlib.util.spec_from_file_location(__name__, path)
module = importlib.util.module_from_spec(spec)
sys.modules[__name__] = module
spec.loader.exec_module(module)
if __name__ == '__main__':
    module.main()
