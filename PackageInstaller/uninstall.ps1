#Requires -RunAsAdministrator
# Stops and removes the Lab Decoder Service (does not delete .venv or data).

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

.\.venv\Scripts\python.exe service_installer.pyc stop
.\.venv\Scripts\python.exe service_installer.pyc remove

Write-Host "Lab Decoder Service stopped and removed." -ForegroundColor Green
