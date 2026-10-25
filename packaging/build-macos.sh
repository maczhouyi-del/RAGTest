#!/bin/sh
# Local development bundle. Does not install toolchains, sign, notarize or publish.
set -eu
cd "$(dirname "$0")/.."
[ "$(uname -s)" = Darwin ] || { echo 'MACOS_BUILD_HOST_REQUIRED'; exit 1; }
[ "$(uname -m)" = arm64 ] || { echo 'THIS_HELPER_REQUIRES_APPLE_SILICON'; exit 1; }
export CARGO_HOME="$PWD/.tools/cargo"
export RUSTUP_HOME="$PWD/.tools/rustup"
export PATH="$CARGO_HOME/bin:$PATH"
command -v cargo >/dev/null
command -v uv >/dev/null
command -v npm >/dev/null
uv sync --frozen --all-extras --project engine
engine/.venv/bin/python tools/run_logged.py --label freeze-macos -- engine/.venv/bin/python packaging/build_sidecar.py --include-vector-lab --include-generation-lab --include-ocr-lab --include-docling-lab
export RAGSYSTEM_FROZEN_SIDECAR="$PWD/apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin"
engine/.venv/bin/python tools/run_logged.py --label pytest-macos -- engine/.venv/bin/python -m pytest -c engine/pyproject.toml
engine/.venv/bin/python tools/run_logged.py --label rust-macos -- cargo test --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
engine/.venv/bin/python tools/run_logged.py --label bundle-macos -- npm --prefix apps/desktop run tauri -- build --debug --bundles app
echo 'Development bundle only: clean installation, signing and notarization remain unverified.'
