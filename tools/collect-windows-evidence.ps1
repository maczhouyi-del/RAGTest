param([string]$InstallerPath = "")
$ErrorActionPreference = "Stop"
if (-not $IsWindows) { throw "WINDOWS_POWERSHELL_7_REQUIRED" }
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$EvidenceRoot = Join-Path $ProjectRoot "docs/engineering/evidence/windows-local"
New-Item -ItemType Directory -Path $EvidenceRoot -Force | Out-Null
$Stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffffffZ")
$Destination = Join-Path $EvidenceRoot "$Stamp-environment.json"
if (Test-Path -LiteralPath $Destination) { throw "EVIDENCE_ALREADY_EXISTS" }
$OsInfo = Get-CimInstance Win32_OperatingSystem
$Computer = Get-CimInstance Win32_ComputerSystem
$Cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$Processes = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "ragsystem*" })
$ProcessIds = @($Processes | Select-Object -ExpandProperty Id)
$Ports = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $ProcessIds } | Select-Object LocalAddress, LocalPort, OwningProcess)
$Defender = "NOT COLLECTED"
try { $Defender = Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled } catch { $Defender = "UNAVAILABLE_NONADMIN_OR_POLICY" }
$Installer = $null
if ($InstallerPath) {
    $File = Get-Item -LiteralPath $InstallerPath
    $Installer = @{name=$File.Name; bytes=$File.Length; sha256=(Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash}
}
$Tools = @{}
foreach ($Name in @("python", "python3", "node", "npm", "cargo", "docker", "wsl", "uv")) {
    $Tools[$Name] = [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}
$Record = [ordered]@{
    recorded_at=[DateTime]::UtcNow.ToString("o"); os=$OsInfo.Caption; os_version=$OsInfo.Version; os_build=$OsInfo.BuildNumber
    architecture=[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    cpu=$Cpu.Name; ram_bytes=$Computer.TotalPhysicalMemory; username=$env:USERNAME
    elevated=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    commands_visible=$Tools; defender=$Defender; installer=$Installer
    processes=@($Processes | Select-Object Id, ProcessName, Path); listening_ports=$Ports
    webview2="RECORD MANUALLY IN ACCEPTANCE FORM"; clean_install_acceptance="NOT EXECUTED BY THIS COLLECTOR"
    uploads_performed=$false
}
$Record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Destination -Encoding utf8
Write-Host "Local evidence saved: $Destination"
