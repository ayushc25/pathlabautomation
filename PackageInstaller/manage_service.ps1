#Requires -RunAsAdministrator
# Convenience wrapper: manage_service.ps1 <start|stop|restart|status>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

switch ($Action) {
    "start"   { .\.venv\Scripts\python.exe service_installer.pyc start }
    "stop"    { .\.venv\Scripts\python.exe service_installer.pyc stop }
    "restart" {
        .\.venv\Scripts\python.exe service_installer.pyc stop
        .\.venv\Scripts\python.exe service_installer.pyc start
    }
    "status"  { Get-Service -Name "LabDecoderService" | Format-List * }
}
