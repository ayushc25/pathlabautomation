# Lab Decoder Service — Installation Guide

This folder is self-contained. Copy the whole `PackageInstaller` folder to the
target Windows machine (e.g. `C:\LabDecoderService\`) and follow the steps
below.

## Prerequisites

- Windows 10/11 (or Windows Server)
- Python 3.11 or newer installed, with **"Add python.exe to PATH"** checked
  during setup (download from https://www.python.org/downloads/ if not
  already installed).
- Internet access on this machine during install (to download the Python
  packages listed in `requirements.txt`), or a pre-populated pip cache.

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
   - Generate a `.env` file with a random `SESSION_SECRET_KEY` (if one
     doesn't already exist)
   - Compile the application to bytecode and **delete the `.py` source
     files** (see "Licensing and code protection" below)
   - Register **LabDecoderService** as a Windows service
   - Start the service immediately

4. **The service will refuse to start without a license.** If this is a
   machine that hasn't been licensed yet, `install.ps1` will print that
   machine's ID at the end — send it to your vendor, drop the `license.lic`
   file they send back into this folder, then run `.\manage_service.ps1 start`.

5. Once it's running, open a browser to **http://127.0.0.1:8000**.
   - Default login: **admin / admin123** (change this — see below)
   - Health check: http://127.0.0.1:8000/health

The service also listens on **TCP port 5000** for direct analyzer
(HORIBA Yumizen H500/H500E) socket connections.

## Licensing and code protection

This build is locked to run only on the machine it's licensed for, and ships
no readable Python source:

- **Hardware lock**: the service checks `license.lic` (next to
  `service_installer.pyc`) against this machine's identity at every startup.
  Copying this folder to another PC will not work there without a new
  license issued for that PC. To get one, run
  `.\.venv\Scripts\python.exe -m app.services.license` in this folder to
  print the machine ID, and send it to your vendor.
- **No source on disk**: `install.ps1` compiles every `.py` file to bytecode
  (`.pyc`) using this machine's own Python — so, unlike a pre-compiled build,
  it's never pinned to a specific Python version — and then deletes the
  source. Only compiled bytecode remains after install.

## Before going live: change the default admin password

The install ships with a fallback local login of `admin / admin123`. Before
handing the system to the client, edit `.env` in this folder and add:

```
ADMIN_PASSWORD=<a strong password>
```

Then apply it:

```powershell
.\manage_service.ps1 restart
```

## What gets installed

- The service is registered under Windows Services as **"Lab Decoder
  Service"** (`LabDecoderService`), set to run automatically.
- Data (captures, decoded results, test mappings) is stored under
  `.\data\*.sqlite3` inside this folder — created fresh on first run.
- Generated histogram/scattergram PNGs are stored under `.\artifacts\`.
- Two bundled workbooks power the test-mapping screen:
  - `data\new stag test ids.xlsx` — the laboratory's own test ID catalog
    (lab side of the mapping). Replace this file (keep the same name) if
    the client's lab test IDs change.
  - `data\SK CBC and ESR test id list.xlsx` — the HORIBA analyzer's own
    universal test ID codes (device side of the mapping, `HorribaTestIDs`
    sheet). This normally does not need to change between installs.

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

This stops and removes the Windows service. It does **not** delete `.venv`,
`.env`, or the `data\` folder (so captured data is preserved). Delete the
whole folder manually if a full removal is required.

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
- **"License file is invalid" / "not valid for this machine"**: the
  `license.lic` in this folder doesn't match this PC, or was edited/corrupted
  in transit (e.g. by an email client mangling line endings). Re-run
  `.\.venv\Scripts\python.exe -m app.services.license` to get this machine's
  current ID and confirm it matches what the license was issued for; if not,
  ask your vendor to re-issue it.
