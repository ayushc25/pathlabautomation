"""Install/remove the application as a Windows service."""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import win32event
    import win32service
    import win32serviceutil
    import servicemanager
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pywin32 is required to install/run the Windows service.") from exc


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "service.log"


def _redirect_std_streams() -> None:
    """Point stdout/stderr at a log file.

    A Windows service has no console, so sys.stdout/sys.stderr are None (or
    otherwise unusable). Anything that logs via a StreamHandler built on
    them - e.g. app.utils.logger, imported the moment app.service_runner is
    imported below - throws immediately and crashes SvcDoRun before main()
    ever runs, which the SCM reports simply as the service stopping right
    after it starts. Redirecting first, before that import happens, fixes
    both problems: the crash, and having nowhere to see why.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_PATH, "a", buffering=1, encoding="utf-8")
    sys.stdout = log_file
    sys.stderr = log_file


class LabDecoderService(win32serviceutil.ServiceFramework):
    _svc_name_ = "LabDecoderService"
    _svc_display_name_ = "Lab Decoder Service"
    _svc_description_ = "Hosts the FastAPI UI/API and keeps the analyzer socket listener running."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server_process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        _redirect_std_streams()
        servicemanager.LogInfoMsg("Lab Decoder Service starting")
        os.chdir(BASE_DIR)
        try:
            from app.service_runner import main

            main()
        except Exception:
            import traceback

            traceback.print_exc()
            servicemanager.LogErrorMsg(
                "Lab Decoder Service crashed on startup - see logs\\service.log for details"
            )
            raise


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(LabDecoderService)
