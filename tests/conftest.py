import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# fetch-taxi.py's hyphenated filename isn't a valid module name, so it can't be
# `import`-ed normally; load it directly from its file path instead.
def _load_script_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fetch_taxi = _load_script_module("fetch_taxi", "fetch-taxi.py")
