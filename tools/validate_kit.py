#!/usr/bin/env python3
"""Validate the Codex planning kit's *static structure*, not the application.

Run from any working directory: python tools/validate_kit.py
It cannot assert that P0 implementation, PDF quality, Windows packaging or real benchmarks pass.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
WARNINGS: list[str] = []

REQUIRED = [
    'README.md', 'AGENTS.md', 'PLANS.md',
    'specs/RAGSystem_2.0_v1.1_source.docx',
    'specs/RAGSystem_2.0_v1.1_extracted.md',
    'specs/SOURCE_PRIORITY.md',
    'docs/phases/P0-taskboard.md',
    'docs/phases/P0-acceptance.md',
    'docs/phases/P0-benchmark.md',
    'docs/engineering/open-decisions.md',
    'docs/engineering/traceability.md',
    'docs/engineering/phase-report-template.md',
    'docs/evaluation/goldset-protocol.md',
    'contracts/README.md',
    'contracts/entity-dictionary.md',
    'contracts/source-anchor.schema.json',
    'contracts/evidence-span.schema.json',
    'contracts/job.schema.json',
    'contracts/vector-search-adapter.md',
    'contracts/query-and-coverage.md',
    'contracts/sidecar.openapi.yaml',
    'codex-prompts/00-plan-only.md',
    'codex-prompts/01-p0-start.md',
    'codex-prompts/02-p0-review.md',
]
for name in REQUIRED:
    path = ROOT / name
    if not path.is_file() or path.stat().st_size == 0:
        ERRORS.append('missing or empty: ' + name)

for path in (ROOT / 'contracts').glob('*.schema.json'):
    try:
        schema = json.loads(path.read_text(encoding='utf-8'))
        assert schema.get('$schema') == 'https://json-schema.org/draft/2020-12/schema'
        assert schema.get('type') == 'object'
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            WARNINGS.append('jsonschema package unavailable; did not validate schema semantics: ' + path.name)
        else:
            Draft202012Validator.check_schema(schema)
    except Exception as exc:  # Includes malformed JSON, invalid JSON Schema
        ERRORS.append(f'JSON Schema invalid: {path.name}: {exc}')

try:
    import yaml
except ImportError:
    WARNINGS.append('PyYAML not installed; skipped full OpenAPI YAML parsing')
else:
    try:
        openapi = yaml.safe_load((ROOT / 'contracts/sidecar.openapi.yaml').read_text(encoding='utf-8'))
        assert openapi.get('openapi') == '3.1.0'
        assert openapi.get('paths')
        assert openapi.get('components', {}).get('securitySchemes')
        assert openapi.get('security')
    except Exception as exc:
        ERRORS.append(f'OpenAPI YAML invalid: {exc}')

plan = (ROOT / 'docs/phases/P0-taskboard.md').read_text(encoding='utf-8')
for n in range(11):
    task_id = f'P0-{n:02d}'
    if not re.search(r'^## ' + re.escape(task_id) + r'\b', plan, re.MULTILINE):
        ERRORS.append('missing P0 task heading: ' + task_id)

matrix = (ROOT / 'docs/phases/P0-acceptance.md').read_text(encoding='utf-8')
for n in range(1, 15):
    gate_id = f'G{n:02d}'
    if not re.search(r'\| ' + gate_id + r' \|', matrix):
        ERRORS.append('missing P0 acceptance gate: ' + gate_id)

md_path = ROOT / 'specs/RAGSystem_2.0_v1.1_extracted.md'
md = md_path.read_text(encoding='utf-8')
for src in re.findall(r'<img\s+src="([^"]+)"', md):
    if not (md_path.parent / src).is_file():
        ERRORS.append(f'extracted Markdown image target missing: {src}')

for path in (ROOT / 'docs/evaluation').glob('*.csv'):
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            ERRORS.append('CSV empty: ' + str(path.relative_to(ROOT)))
            continue
        if len(header) < 5 or any(not col.strip() for col in header):
            ERRORS.append('CSV malformed header: ' + str(path.relative_to(ROOT)))
        for index, row in enumerate(reader, start=2):
            if len(row) != len(header):
                ERRORS.append(f'CSV row length mismatch: {path.name} line {index}: {len(row)} != {len(header)}')

if ERRORS:
    print('STATIC KIT VALIDATION: FAIL')
    for issue in ERRORS:
        print('  ERROR:', issue)
else:
    print('STATIC KIT VALIDATION: PASS (files and syntax only)')

for issue in WARNINGS:
    print('  WARNING:', issue)
print('IMPORTANT: No Windows runtime, PDF, embedding, retrieval or scientific quality tests were executed by this validator.')
sys.exit(1 if ERRORS else 0)
