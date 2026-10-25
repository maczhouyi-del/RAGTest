param()
$ErrorActionPreference = "Stop"
if (-not $IsWindows -or [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne "X64") {
    throw "WINDOWS_X64_BUILD_HOST_REQUIRED (PowerShell 7)"
}
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot
foreach ($CommandName in @("uv", "node", "npm", "cargo")) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "BUILD_TOOL_MISSING: $CommandName"
    }
}
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "BUILD_STEP_FAILED: $Program ($LASTEXITCODE)" }
}
Invoke-Checked -Program uv -Arguments @("sync", "--frozen", "--all-extras", "--project", "engine")
$LockPath = Join-Path $ProjectRoot "apps/desktop/package-lock.json"
$LockHash = (Get-FileHash $LockPath -Algorithm SHA256).Hash
# npm ci replaces node_modules; use an install that preserves existing files.
Invoke-Checked -Program npm -Arguments @("--prefix", "apps/desktop", "install", "--ignore-scripts", "--no-audit", "--no-fund")
if ((Get-FileHash $LockPath -Algorithm SHA256).Hash -ne $LockHash) { throw "DEPENDENCY_LOCK_CHANGED" }
$Python = Join-Path $ProjectRoot "engine/.venv/Scripts/python.exe"
Invoke-Checked -Program $Python -Arguments @("packaging/build_sidecar.py", "--include-vector-lab", "--include-generation-lab", "--include-ocr-lab", "--include-docling-lab")
$env:RAGSYSTEM_FROZEN_SIDECAR = Join-Path $ProjectRoot "apps/desktop/src-tauri/binaries/ragsystem-engine-x86_64-pc-windows-msvc.exe"
Invoke-Checked -Program $Python -Arguments @("-m", "pytest", "-c", "engine/pyproject.toml")
Invoke-Checked -Program cargo -Arguments @("test", "--manifest-path", "apps/desktop/src-tauri/Cargo.toml", "--locked")
Invoke-Checked -Program npm -Arguments @("--prefix", "apps/desktop", "run", "tauri", "--", "build", "--target", "x86_64-pc-windows-msvc", "--bundles", "nsis")
Write-Host "BUILD ONLY: clean Windows installation acceptance still required."
