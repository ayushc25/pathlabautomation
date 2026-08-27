#Requires -RunAsAdministrator
# Installs the Lab Decoder Service: creates a virtual environment, installs
# dependencies, then installs and starts the Windows service.

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Error "Please run this script from an elevated (Run as Administrator) PowerShell prompt."
    exit 1
}

Write-Host "== Checking for Python ==" -ForegroundColor Cyan
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python was not found on PATH. Install Python 3.11 (from python.org, with 'Add to PATH' checked) and re-run this script."
    exit 1
}

$pyVersion = (& python --version) 2>&1
Write-Host "Found $pyVersion"

if (-not (Test-Path ".venv")) {
    Write-Host "== Creating virtual environment (.venv) ==" -ForegroundColor Cyan
    python -m venv .venv
} else {
    Write-Host "== Virtual environment already exists, reusing .venv ==" -ForegroundColor Cyan
}

Write-Host "== Installing dependencies ==" -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "== Installing Windows service ==" -ForegroundColor Cyan
.\.venv\Scripts\python.exe service_installer.pyc install

Write-Host "== Starting Windows service ==" -ForegroundColor Cyan
.\.venv\Scripts\python.exe service_installer.pyc start

Write-Host ""
Write-Host "Done. The Lab Decoder Service is installed and running." -ForegroundColor Green
Write-Host "Dashboard: http://127.0.0.1:8000  (default login: admin / admin123)"
Write-Host "Health check: http://127.0.0.1:8000/health"
