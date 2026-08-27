# Lab Decoder Service — Installation Guide

This folder is self-contained. Copy the whole `PackageInstaller` folder to the
target Windows machine (e.g. `C:\LabDecoderService\`) and follow the steps
below.

## Prerequisites

- Windows 10/11 (or Windows Server)
- Python 3.14 installed, with **"Add python.exe to PATH"** checked during
  setup (download from https://www.python.org/downloads/ if not already
  installed). This must match — see "About this build" below.
- Internet access on this machine during install (to download the Python
  packages listed in `requirements.txt`), or a pre-populated pip cache

## Install

1. Copy this entire folder to the machine, e.g. `C:\LabDecoderService\`.
2. Right-click **PowerShell** and choose **Run as administrator**.
3. Navigate to the folder and run the installer:

   ```powershell
   cd C:\LabDecoderService
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\install.ps1
   ```

   This will:
   - Create a local virtual environment (`.venv`)
   - Install all required Python packages
   - Register **LabDecoderService** as a Windows service
   - Start the service immediately

4. Once it finishes, open a browser to **http://127.0.0.1:8000**.
   - Default login: **admin / admin123**
   - Health check: http://127.0.0.1:8000/health

The service also listens on **TCP port 5000** for direct analyzer
(HORIBA Yumizen H500/H500E) socket connections.

## About this build

The application code is shipped as compiled Python bytecode (`.pyc` files)
rather than plain source (`.py`) — the source itself is not included in this
package. Everything installs and runs exactly the same way; there is nothing
different to do here.

This build was compiled against **Python 3.14** specifically — `.pyc`
bytecode is tied to the exact Python minor version that produced it (its
"magic number"). If the target machine has a different version (3.11, 3.12,
3.13, ...), the service will fail to start with an error like
`RuntimeError: Bad magic number in .pyc file`. Check with:

```powershell
python --version
```

If it doesn't say `Python 3.14.x`, install Python 3.14 (or ask whoever built
this package for a `.pyc` build matching the version you have).

## What gets installed

- The service is registered under Windows Services as **"Lab Decoder
  Service"** (`LabDecoderService`), set to run automatically.
- Data (captures, decoded results, test mappings) is stored under
  `.\data\*.sqlite3` inside this folder.
- Generated histogram/scattergram PNGs are stored under `.\artifacts\`.
- The bundled test-catalog workbook (`data\SK CBC and ESR test id
  list.xlsx`) powers the test-mapping screen; replace that file (keep the
  same name) if the client needs an updated catalog.

Because the service reads its files relative to this folder, **do not move
the folder after installation** — reinstall (`install.ps1`) again if it must
be relocated.

## Managing the service afterwards

From an elevated PowerShell prompt, in this folder:

```powershell
.\manage_service.ps1 start      # start the service
.\manage_service.ps1 stop       # stop the service
.\manage_service.ps1 restart    # restart the service
.\manage_service.ps1 status     # show current service status
```

Or use the Windows **Services** app (`services.msc`) — look for
"Lab Decoder Service".

## Uninstalling

From an elevated PowerShell prompt, in this folder:

```powershell
.\uninstall.ps1
```

This stops and removes the Windows service. It does **not** delete `.venv`
or the `data\` folder (so captured data is preserved). Delete the whole
folder manually if a full removal is required.

## Troubleshooting

- **"python is not recognized"**: Python isn't installed or wasn't added to
  PATH. Reinstall Python and check "Add python.exe to PATH".
- **Port 8000 or 5000 already in use**: another application is bound to
  that port. Set the `LAB_APP_PORT` environment variable (system-wide) to a
  free port before running `install.ps1`, or stop the conflicting
  application.
- **Service starts, then quickly shows as Stopped in services.msc**: check
  **`logs\service.log`** in this folder first — it's created the moment the
  service starts and captures the full startup traceback (this is the most
  common cause: something raised during app startup, e.g. a locked/
  inaccessible `data\` folder, or port 5000/8000 already bound). Whatever
  exception appears near the bottom of that file is the real cause.
- **Service won't start at all / log file is empty**: check the Windows
  Event Viewer under *Windows Logs > Application* for `LabDecoderService`
  errors, or run `.\.venv\Scripts\python.exe service_installer.pyc debug`
  from this folder to see live console output directly (Ctrl+C to stop).
