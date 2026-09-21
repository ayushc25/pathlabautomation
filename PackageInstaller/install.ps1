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
    Write-Error "Python was not found on PATH. Install Python 3.11+ (from python.org, with 'Add to PATH' checked) and re-run this script."
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

if (-not (Test-Path ".env")) {
    Write-Host "== Generating .env with a random session secret ==" -ForegroundColor Cyan
    Copy-Item ".env.example" ".env"
    $chars = [char[]]([char]'a'..[char]'z') + [char[]]([char]'A'..[char]'Z') + [char[]]([char]'0'..[char]'9')
    $secret = -join (1..48 | ForEach-Object { Get-Random -InputObject $chars })
    Add-Content ".env" "SESSION_SECRET_KEY=$secret"
} else {
    Write-Host "== .env already exists, leaving it as-is ==" -ForegroundColor Cyan
}

if (Test-Path "app\main.py") {
    Write-Host "== Compiling application to bytecode and removing source (.py) files ==" -ForegroundColor Cyan
    # Compiles with -b (legacy layout: module.pyc next to module.py, not
    # __pycache__), using THIS machine's own Python - so it's never pinned to
    # a build machine's Python version like a pre-shipped .pyc would be.
    .\.venv\Scripts\python.exe -m compileall -b -q app service_installer.py
    Get-ChildItem -Path "app" -Recurse -Filter "*.py" | Remove-Item -Force
    Remove-Item "service_installer.py" -Force
    Get-ChildItem -Path "app" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
} else {
    Write-Host "== Application already compiled (no .py source present), skipping ==" -ForegroundColor Cyan
}

Write-Host "== Installing Windows service ==" -ForegroundColor Cyan
.\.venv\Scripts\python.exe service_installer.pyc install

Write-Host "== Starting Windows service ==" -ForegroundColor Cyan
try {
    .\.venv\Scripts\python.exe service_installer.pyc start
} catch {
    # handled by the license check below
}

Write-Host ""
Start-Sleep -Seconds 2
$service = Get-Service -Name "LabDecoderService" -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq "Running") {
    Write-Host "Done. The Lab Decoder Service is installed and running." -ForegroundColor Green
    Write-Host "Dashboard: http://127.0.0.1:8000  (default login: admin / admin123 unless ADMIN_PASSWORD was set in .env)"
    Write-Host "Health check: http://127.0.0.1:8000/health"
    Write-Host ""
    Write-Host "IMPORTANT: change the default admin password for production use -" -ForegroundColor Yellow
    Write-Host "set ADMIN_PASSWORD in .env, then run: .\manage_service.ps1 restart" -ForegroundColor Yellow
} else {
    Write-Host "The service was installed but is not running yet - this almost" -ForegroundColor Yellow
    Write-Host "always means a license.lic file is needed. This machine's ID is:" -ForegroundColor Yellow
    Write-Host ""
    .\.venv\Scripts\python.exe -m app.services.license
    Write-Host ""
    Write-Host "Send that ID to your vendor for a license.lic file, place it in" -ForegroundColor Yellow
    Write-Host "this folder (next to service_installer.pyc), then run:" -ForegroundColor Yellow
    Write-Host "  .\manage_service.ps1 start"
    Write-Host ""
    Write-Host "If a license.lic is already here, check logs\service.log for the real cause." -ForegroundColor Yellow
}
