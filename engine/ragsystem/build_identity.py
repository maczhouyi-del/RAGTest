"""Identify the running sidecar, not a separately edited source checkout."""

import json
import sys
from pathlib import Path


def build_identity():
    if getattr(sys, 'frozen', False):
        path = Path(sys._MEIPASS) / 'ragsystem-build.json'
        if path.is_file():
            value = json.loads(path.read_text())
            return {key: value[key] for key in ('built_at', 'source_sha256', 'label')}
        return {'label': 'unidentified-frozen-build', 'source_sha256': None, 'built_at': None}
    return {'label': 'source-checkout', 'source_sha256': None, 'built_at': None}
