"""Hardware-locked license enforcement.

The service refuses to start unless a `license.lic` file is present next to
it, signed by the vendor's private key (see `tools/license_tool.py`, kept
outside this shipped app), and issued for *this specific machine*. Copying
the install folder to a second machine will not work there without a new
license issued for that machine's fingerprint.

This raises the bar against casual copying; it is not meant to defeat a
determined attacker with full control of the machine (nothing can be, for
code that has to run on hardware you don't control) - see the obfuscated
build step for the source-reading side of that threat model.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Public key for the vendor's signing keypair (see tools/license_tool.py
# genkeypair). Safe to ship - it can only verify signatures, never create
# them.
VENDOR_PUBLIC_KEY_B64 = "Wistqp5Mdq6OZqedexaQMbwIMWO5G8frGJkBc1BKCRU="

BASE_DIR = Path(__file__).resolve().parents[2]
LICENSE_PATH = BASE_DIR / "license.lic"

SUPPORT_CONTACT = os.environ.get("LICENSE_SUPPORT_CONTACT", "your vendor")


class LicenseError(RuntimeError):
    """Raised when the license is missing, invalid, expired, or wrong-machine."""


def get_machine_fingerprint() -> str:
    """A stable identifier for this Windows installation.

    Derived from the OS-generated MachineGuid (regenerated only on a fresh
    Windows install/reimage) plus the computer name, so a straight file copy
    to another PC yields a different fingerprint.
    """
    if sys.platform != "win32":
        raise LicenseError("Licensing is only supported on Windows.")

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            machine_guid = winreg.QueryValueEx(key, "MachineGuid")[0]
    except OSError as exc:
        raise LicenseError("Unable to read this machine's identity (MachineGuid).") from exc

    computer_name = os.environ.get("COMPUTERNAME", "")
    raw = f"{machine_guid}|{computer_name}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest().upper()[:16]
    return "-".join(digest[i : i + 4] for i in range(0, 16, 4))


def _canonical_payload(data: Dict[str, Any]) -> bytes:
    payload = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_signature(data: Dict[str, Any]) -> None:
    try:
        signature = base64.b64decode(data["signature"])
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(VENDOR_PUBLIC_KEY_B64))
        public_key.verify(signature, _canonical_payload(data))
    except (KeyError, ValueError, InvalidSignature) as exc:
        raise LicenseError("License file is invalid or has been tampered with.") from exc


def verify_license(license_path: Optional[Path] = None) -> Dict[str, Any]:
    """Validate the license file, raising LicenseError if it's not good.

    Returns the license payload (licensed_to, machine_id, issued_at,
    expires_at) on success.
    """
    path = license_path or LICENSE_PATH
    if not path.exists():
        raise LicenseError(
            f"No license file found at {path}. Run "
            "'.venv\\Scripts\\python.exe -m app.services.license' to get this "
            f"machine's ID and send it to {SUPPORT_CONTACT} for a license.lic file."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseError(f"License file at {path} could not be read: {exc}") from exc

    _verify_signature(data)

    current_fp = get_machine_fingerprint()
    if data.get("machine_id") != current_fp:
        raise LicenseError(
            f"This license is not valid for this machine (this machine's ID is "
            f"{current_fp}). Contact {SUPPORT_CONTACT} for a license matching it."
        )

    expires_at = data.get("expires_at")
    if expires_at and date.today().isoformat() > expires_at:
        raise LicenseError(f"License expired on {expires_at}. Contact {SUPPORT_CONTACT} to renew.")

    return data


def _bypass_active() -> bool:
    if "pytest" in sys.modules:
        return True
    return os.environ.get("LICENSE_BYPASS") == "1"


def ensure_licensed() -> None:
    """Call once at process startup. Raises LicenseError if unlicensed,
    unless running under pytest or LICENSE_BYPASS=1 is set (local dev)."""
    if _bypass_active():
        return
    verify_license()


if __name__ == "__main__":
    print(f"Machine ID: {get_machine_fingerprint()}")
