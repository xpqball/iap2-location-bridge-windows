"""Import bounded MFi assets from a user-supplied APK with an explicit SHA-256."""

import argparse
import sys
from pathlib import Path

from import_diplay_identity import (
    default_identity_dir,
    environment_assignment,
    read_identity,
    write_identity,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output-dir", type=Path, default=default_identity_dir())
    args = parser.parse_args()
    digest = args.sha256.lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        parser.error("sha256 must contain 64 hexadecimal characters")
    try:
        with args.apk.open("rb") as stream:
            identity = read_identity(stream, expected_digest=digest)
        destination = write_identity(identity, args.output_dir)
    except Exception as error:
        print(f"Import failed ({type(error).__name__}): {error}", file=sys.stderr)
        return 1
    print("Certificate/key matching and format validation passed.")
    print("SHA-256 identifies the supplied file; it does not establish publisher authenticity.")
    for variable, filename in (
        ("IAP2_LOCATION_BRIDGE_WINDOWS_CERT_FILE", "certificate.p7b"),
        ("IAP2_LOCATION_BRIDGE_WINDOWS_KEY_FILE", "identity.pk8"),
    ):
        print(environment_assignment(variable, destination / filename))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
