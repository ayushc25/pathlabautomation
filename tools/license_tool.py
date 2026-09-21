"""Vendor-side license issuing tool.

KEEP THIS FILE AND vendor_private_key.pem PRIVATE - never copy either of
them into PackageInstaller/ or hand them to a client. Only the public key
(pasted into app/services/license.py) ever leaves your machine.

Usage:

    # One-time setup: generate your signing keypair.
    python tools/license_tool.py genkeypair

    # Paste the printed public key into VENDOR_PUBLIC_KEY_B64 in
    # app/services/license.py, then rebuild/reship the app.

    # For each client machine: they run, on their machine,
    #   .venv\\Scripts\\python.exe -m app.services.license
    # which prints their machine ID. They send you that ID, and you run:
    python tools/license_tool.py issue --machine-id AB12-CD34-EF56-7890 \\
        --licensed-to "Client Lab Name" --expires 2027-08-30 \\
        --out license.lic

    # Send them the resulting license.lic - they drop it next to
    # service_installer.py in their install folder and restart the service.
"""
from __future__ import annotations

import argparse
import base64
import json
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BASE_DIR = Path(__file__).resolve().parent.parent
PRIVATE_KEY_PATH = BASE_DIR / "vendor_private_key.pem"


def cmd_genkeypair(_args: argparse.Namespace) -> None:
    if PRIVATE_KEY_PATH.exists():
        raise SystemExit(
            f"{PRIVATE_KEY_PATH} already exists - refusing to overwrite an "
            "existing signing key (that would invalidate every license "
            "issued so far). Delete it manually first if you really mean to."
        )
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes_raw()
    PRIVATE_KEY_PATH.write_bytes(private_bytes)

    public_bytes = private_key.public_key().public_bytes_raw()
    public_b64 = base64.b64encode(public_bytes).decode("ascii")

    print(f"Private key written to {PRIVATE_KEY_PATH} - back it up somewhere safe, keep it secret.")
    print()
    print("Paste this into VENDOR_PUBLIC_KEY_B64 in app/services/license.py:")
    print()
    print(f'VENDOR_PUBLIC_KEY_B64 = "{public_b64}"')


def _load_private_key() -> Ed25519PrivateKey:
    if not PRIVATE_KEY_PATH.exists():
        raise SystemExit(f"No signing key at {PRIVATE_KEY_PATH} - run 'genkeypair' first.")
    return Ed25519PrivateKey.from_private_bytes(PRIVATE_KEY_PATH.read_bytes())


def cmd_issue(args: argparse.Namespace) -> None:
    private_key = _load_private_key()

    payload = {
        "licensed_to": args.licensed_to,
        "machine_id": args.machine_id,
        "issued_at": date.today().isoformat(),
        "expires_at": args.expires,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(canonical)
    payload["signature"] = base64.b64encode(signature).decode("ascii")

    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"License written to {out_path}")
    print(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(required=True)

    genkeypair_parser = subparsers.add_parser("genkeypair", help="Generate the vendor signing keypair (one-time).")
    genkeypair_parser.set_defaults(func=cmd_genkeypair)

    issue_parser = subparsers.add_parser("issue", help="Issue a license.lic for a client machine.")
    issue_parser.add_argument("--machine-id", required=True, help="The machine ID printed by app.services.license on the client's machine.")
    issue_parser.add_argument("--licensed-to", required=True, help="Client/lab name, for your own records.")
    issue_parser.add_argument("--expires", default=None, help="Optional expiry date (YYYY-MM-DD). Omit for a perpetual license.")
    issue_parser.add_argument("--out", default="license.lic", help="Output path (default: ./license.lic).")
    issue_parser.set_defaults(func=cmd_issue)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
