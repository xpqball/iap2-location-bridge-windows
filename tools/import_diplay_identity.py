#!/usr/bin/env python3
"""Opt-in local import from the pinned DiPlay preview APK; never runs the APK."""

import argparse
import hashlib
import io
import os
import shlex
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from local_mfi_v3_helper import MAX_IDENTITY_BYTES, ProviderError, validate_identity

APK_URL = "https://github.com/shihabal3amri/DiPlay/releases/download/v0.2.7/DiPlay-0.2.7.apk"
APK_SHA256 = "27b434462da7e78b1ff0987d129ed0a4b0a0e56beceaf8ec221d47150d4675bd"
MAX_APK_BYTES = 64 * 1024 * 1024
CHECKOUT = Path(__file__).resolve().parents[1]
ASSETS = {
    "certificate.p7b": "assets/offline-mfi/certificate.p7b",
    "identity.pk8": "assets/offline-mfi/identity.pk8",
}
NOTICE_URL = (
    "https://github.com/shihabal3amri/DiPlay/blob/main/"
    "docs/THIRD_PARTY_NOTICES.md#experimental-authentication-data"
)


class IdentityImportError(Exception):
    pass


def default_identity_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / (
            "iap2-location-bridge-windows/identity"
        )
    return Path.home() / "Library/Application Support/iap2-location-bridge-windows/identity"


def create_private_directory(destination):
    if sys.platform != "win32":
        destination.mkdir(mode=0o700)
        return
    import ntsecuritycon
    import win32api
    import win32con
    import win32file
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    acl = win32security.ACL()
    acl.AddAccessAllowedAceEx(
        win32security.ACL_REVISION,
        win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE,
        ntsecuritycon.FILE_ALL_ACCESS,
        sid,
    )
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorDacl(1, acl, 0)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED, win32security.SE_DACL_PROTECTED
    )
    attributes = win32security.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    # Apply the protected DACL at creation, before any private bytes are written.
    win32file.CreateDirectory(str(destination), attributes)
    try:
        actual = win32security.GetFileSecurity(
            str(destination), win32security.DACL_SECURITY_INFORMATION
        )
        actual_acl = actual.GetSecurityDescriptorDacl()
        if (not actual.GetSecurityDescriptorControl()[0] & win32security.SE_DACL_PROTECTED
                or actual_acl is None or actual_acl.GetAceCount() != 1):
            raise IdentityImportError("Directory ACL is not protected and current-user-only")
        header, mask, actual_sid = actual_acl.GetAce(0)
        inherit = win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE
        if (header[0] != win32security.ACCESS_ALLOWED_ACE_TYPE
                or header[1] != inherit
                or mask != ntsecuritycon.FILE_ALL_ACCESS or actual_sid != sid):
            raise IdentityImportError("Directory ACL does not grant inheritable current-user access")
    except Exception as error:
        # No credential bytes have been written. Remove only the directory we created.
        destination.rmdir()
        raise IdentityImportError("Could not verify the private directory ACL") from error


def environment_assignment(variable, path):
    if sys.platform == "win32":
        escaped = str(path).replace("'", "''")
        return f"$env:{variable} = '{escaped}'"
    return f"export {variable}={shlex.quote(str(path))}"


def destination_path(path):
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise IdentityImportError("Output directory must not be a symbolic link")
    destination = expanded.resolve()
    if destination.is_relative_to(CHECKOUT):
        raise IdentityImportError("Keep the output directory outside the repository")
    if destination.exists():
        raise IdentityImportError("Output directory already exists; choose a new directory")
    return destination


def download_apk(stream):
    request = urllib.request.Request(APK_URL, headers={"User-Agent": "iap2-location-bridge-windows"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if not response.geturl().startswith("https://"):
            raise IdentityImportError("Download redirected outside HTTPS")
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_APK_BYTES:
                raise IdentityImportError("APK exceeds the download size limit")
            stream.write(chunk)
    stream.seek(0)


def read_identity(stream, expected_digest=None):
    """Verify the full archive before reading only the two named, bounded assets."""
    stream.seek(0)
    archive_bytes = stream.read(MAX_APK_BYTES + 1)
    if len(archive_bytes) > MAX_APK_BYTES:
        raise IdentityImportError("APK exceeds the size limit")
    if hashlib.sha256(archive_bytes).hexdigest() != (expected_digest or APK_SHA256):
        expected = "the supplied SHA-256" if expected_digest else "the pinned DiPlay v0.2.7 release"
        raise IdentityImportError(f"APK SHA-256 mismatch; expected {expected}")
    identity = {}
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = archive.namelist()
        for filename, asset in ASSETS.items():
            if names.count(asset) != 1:
                raise IdentityImportError(f"APK must contain exactly one {asset}")
            info = archive.getinfo(asset)
            if not 1 <= info.file_size <= MAX_IDENTITY_BYTES:
                raise IdentityImportError("Identity asset exceeds size limits")
            with archive.open(info) as entry:
                data = entry.read(MAX_IDENTITY_BYTES + 1)
            if not data or len(data) > MAX_IDENTITY_BYTES:
                raise IdentityImportError("Identity asset exceeds size limits")
            identity[filename] = data
    validate_identity(identity["certificate.p7b"], identity["identity.pk8"])
    return identity


def write_identity(identity, destination):
    destination = destination_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    create_private_directory(destination)
    created = []
    try:
        for filename in ASSETS:
            path = destination / filename
            # Create each file with owner-only permissions, independent of umask.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(fd, "wb") as stream:
                stream.write(identity[filename])
    except BaseException:
        for path in created:
            path.unlink()
        destination.rmdir()
        raise
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--download", action="store_true", help="download the pinned preview APK")
    source.add_argument("--apk", type=Path, help="read an existing DiPlay v0.2.7 APK")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_identity_dir(),
        help="new directory outside the checkout (existing directories are never overwritten)",
    )
    args = parser.parse_args(argv)
    try:
        destination = destination_path(args.output_dir)
        if args.download:
            with tempfile.TemporaryFile() as stream:
                download_apk(stream)
                identity = read_identity(stream)
        else:
            with args.apk.open("rb") as stream:
                identity = read_identity(stream)
        destination = write_identity(identity, destination)
    except (IdentityImportError, ProviderError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, RuntimeError):
        print("Import failed: could not download, read, or save the identity", file=sys.stderr)
        return 1
    print("Imported DiPlay v0.2.7's shared experimental accessory identity.")
    print(f"Provenance and distribution notes: {NOTICE_URL}")
    print("Local validation passed; device acceptance is not guaranteed.")
    print("Set these variables in the shell that will run the client:")
    for variable, filename in (
        ("IAP2_LOCATION_BRIDGE_WINDOWS_CERT_FILE", "certificate.p7b"),
        ("IAP2_LOCATION_BRIDGE_WINDOWS_KEY_FILE", "identity.pk8"),
    ):
        print(environment_assignment(variable, destination / filename))
    return 0


if __name__ == "__main__":
    sys.exit(main())
