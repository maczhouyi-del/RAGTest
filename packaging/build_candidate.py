"""Build a local unsigned engineering candidate. Never install, sign or publish it.

Requires an already built complete sidecar and matching source hashes. Toolchains
are developer prerequisites only; the resulting app embeds Python/native runtime.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def verify_sidecar(record):
    expected = 'aarch64-apple-darwin' if sys.platform == 'darwin' and platform.machine() == 'arm64' else 'x86_64-pc-windows-msvc' if sys.platform == 'win32' and platform.machine().lower() in {'amd64','x86_64'} else None
    if record.get('target') != expected or expected is None:
        raise ValueError('CANDIDATE_TARGET_MISMATCH')
    if not all(record.get(key) is True for key in ('vector_lab_bundled','generation_lab_bundled','ocr_lab_bundled','docling_lab_bundled')) or record.get('model_weights_bundled') is not False:
        raise ValueError('CANDIDATE_RUNTIME_PROFILE_MISMATCH')
    for name, digest in record['source_sha256'].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError('CANDIDATE_SOURCE_MISMATCH:'+name)
    binary = (ROOT/record['path']).resolve()
    if not binary.is_relative_to(ROOT) or binary.is_symlink() or sha(binary) != record['sha256']:
        raise ValueError('CANDIDATE_SIDECAR_MISMATCH')
    return binary, expected


def webview_config(manifest_path):
    if manifest_path is None:
        raise ValueError('APPROVED_FIXED_WEBVIEW2_MANIFEST_REQUIRED')
    resource = json.loads(manifest_path.read_text())
    directory = (manifest_path.parent/resource['directory']).resolve()
    files = resource['files']
    if not resource.get('version') or not files or 'msedgewebview2.exe' not in files:
        raise ValueError('WEBVIEW2_MANIFEST_INVALID')
    actual = set()
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise ValueError('WEBVIEW2_SYMLINK_FORBIDDEN')
        if path.is_file():
            actual.add(str(path.relative_to(directory)).replace('\\','/'))
    if actual != set(files):
        raise ValueError('WEBVIEW2_FILE_SET_MISMATCH')
    for relative, digest in files.items():
        path = directory/relative
        if not path.resolve().is_relative_to(directory) or sha(path) != digest:
            raise ValueError('WEBVIEW2_HASH_MISMATCH')
    return {'webviewInstallMode':{'type':'fixedRuntime','path':str(directory)}, 'allowDowngrades':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sidecar-manifest', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--webview2-manifest', type=Path)
    args = parser.parse_args()
    record = json.loads(args.sidecar_manifest.read_text())
    binary, target = verify_sidecar(record)
    windows = webview_config(args.webview2_manifest) if sys.platform == 'win32' else None
    output = args.output_directory.resolve()
    if not output.is_relative_to(ROOT/'.tools/build'):
        raise ValueError('CANDIDATE_OUTPUT_MUST_BE_PROJECT_BUILD_DIRECTORY')
    output.mkdir(parents=True, exist_ok=False)
    stem = binary.parent/'ragsystem-engine'
    config = {'build':{'beforeBuildCommand':'npm run build -- --emptyOutDir=false'},
              'bundle':{'externalBin':[str(stem)]}}
    if sys.platform == 'win32':
        # No implicit latest-version bootstrapper download. Provisioning is manual.
        config['bundle']['windows'] = windows
    config_path = output/'candidate.tauri.json'
    config_path.write_text(json.dumps(config,indent=2)+'\n')
    command = ['npm.cmd' if sys.platform=='win32' else 'npm','--prefix','apps/desktop','run','tauri','--','build','--ci','--no-sign','--target',target,'--bundles','app,dmg' if sys.platform=='darwin' else 'nsis','--config',str(config_path)]
    env = dict(os.environ)
    env['CARGO_HOME'] = str(ROOT/'.tools/cargo')
    env['RUSTUP_HOME'] = str(ROOT/'.tools/rustup')
    env['PATH'] = str(ROOT/'.tools/cargo/bin')+os.pathsep+env['PATH']
    # Fresh task-owned target: no replacing or deleting previous bundles/builds.
    env['CARGO_TARGET_DIR'] = str(output/'target')
    result = subprocess.run(command,cwd=ROOT,env=env,check=False)
    artifact_root = output/'target'/target/'release/bundle'
    artifacts = [{'path':str(p.relative_to(ROOT)), 'sha256':sha(p),'bytes':p.stat().st_size}
                 for p in artifact_root.rglob('*') if p.is_file() and p.suffix.lower() in {'.dmg','.exe','.msi'}]
    manifest = {'built_at':datetime.now(UTC).isoformat(), 'target':target,
                'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'source_files':record['source_sha256'], 'sidecar_sha256':record['sha256'],
                'locks':{name:sha(ROOT/name) for name in ('engine/uv.lock','apps/desktop/package-lock.json','apps/desktop/src-tauri/Cargo.lock')},
                'command':command,'exit_code':result.returncode,'artifacts':artifacts,
                'status':'BUILD_ONLY' if result.returncode==0 else 'BUILD_FAILED',
                'release_signed':False,'signing_note':'No certificate/account operation; linker ad-hoc signatures may exist','notarized':False,'installed_tested':False,'release_approved':False,
                'blockers':['DEPENDENCY_AUDIT','TARGET_NOTICES','CLEAN_INSTALL','SCIENTIFIC_GOLD','PLATFORM_SIGNING_REVIEW']}
    (output/'candidate-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k not in {'source_files'}}))
    return result.returncode


if __name__=='__main__':
    raise SystemExit(main())
