#Requires -RunAsAdministrator
# Convenience wrapper: manage_service.ps1 <start|stop|restart|status>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$entry = if (Test-Path "service_installer.pyc") { "service_installer.pyc" } else { "service_installer.py" }

switch ($Action) {
    "start"   { .\.venv\Scripts\python.exe $entry start }
    "stop"    { .\.venv\Scripts\python.exe $entry stop }
    "restart" {
        .\.venv\Scripts\python.exe $entry stop
        .\.venv\Scripts\python.exe $entry start
    }
    "status"  { Get-Service -Name "LabDecoderService" | Format-List * }
}
