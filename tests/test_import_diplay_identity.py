"""Import fixtures contain generated, untrusted identities; no real APK is fetched."""

import hashlib
import importlib
import io
import os
import stat
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs7
from test_local_mfi_v3_helper import encode_key, make_certificate


@pytest.fixture
def importer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    return importlib.import_module("import_diplay_identity")


@pytest.fixture
def identity():
    key = ec.generate_private_key(ec.SECP256R1())
    return {
        "certificate.p7b": pkcs7.serialize_certificates(
            [make_certificate(key)], serialization.Encoding.DER
        ),
        "identity.pk8": encode_key(key),
    }


def apk_bytes(importer, identity, extra=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in identity.items():
            archive.writestr(importer.ASSETS[name], data)
        for name, data in extra:
            archive.writestr(name, data)
    return stream.getvalue()


def read_fixture(importer, data):
    return importer.read_identity(io.BytesIO(data), hashlib.sha256(data).hexdigest())


def test_import_exact_assets_and_private_permissions(importer, identity, tmp_path):
    data = apk_bytes(importer, identity, [("../../unexpected.txt", b"never extracted")])
    result = read_fixture(importer, data)
    assert result == identity
    destination = tmp_path / "nested" / "identity"
    old_umask = os.umask(0)
    try:
        assert importer.write_identity(result, destination) == destination
    finally:
        os.umask(old_umask)
    if os.name == "nt":
        assert_private_windows_acl(destination, protected=True)
    else:
        assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert {path.name for path in destination.iterdir()} == set(identity)
    for name, value in identity.items():
        path = destination / name
        assert path.read_bytes() == value
        if os.name == "nt":
            assert_private_windows_acl(path)
        else:
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not (tmp_path / "unexpected.txt").exists()


def test_pinned_digest_rejects_other_apk(importer, identity):
    with pytest.raises(importer.IdentityImportError, match="SHA-256 mismatch"):
        importer.read_identity(io.BytesIO(apk_bytes(importer, identity)))


@pytest.mark.parametrize("problem", ["missing", "duplicate", "oversized", "mismatched", "bad_der"])
def test_invalid_assets(importer, identity, problem):
    extra = []
    if problem == "missing":
        del identity["identity.pk8"]
    elif problem == "duplicate":
        extra = [(importer.ASSETS["identity.pk8"], identity["identity.pk8"])]
    elif problem == "oversized":
        identity["identity.pk8"] = b"x" * (importer.MAX_IDENTITY_BYTES + 1)
    elif problem == "mismatched":
        identity["identity.pk8"] = encode_key(ec.generate_private_key(ec.SECP256R1()))
    else:
        identity["certificate.p7b"] = b"invalid DER"
    if problem == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate name"):
            data = apk_bytes(importer, identity, extra)
    else:
        data = apk_bytes(importer, identity, extra)
    with pytest.raises((importer.IdentityImportError, importer.ProviderError)):
        read_fixture(importer, data)


def test_archive_size_bound(importer, monkeypatch):
    monkeypatch.setattr(importer, "MAX_APK_BYTES", 10)
    with pytest.raises(importer.IdentityImportError, match="size limit"):
        read_fixture(importer, b"x" * 11)


def test_refuse_existing_checkout_and_symlink_destinations(importer, identity, tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "do-not-change"
    sentinel.write_text("original")
    with pytest.raises(importer.IdentityImportError, match="already exists"):
        importer.write_identity(identity, existing)
    assert sentinel.read_text() == "original"
    with pytest.raises(importer.IdentityImportError, match="outside the repository"):
        importer.destination_path(importer.CHECKOUT / "new-identity")


def test_refuse_symlink_destinations(importer, tmp_path):
    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path / "missing", target_is_directory=True)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows symlink creation requires Developer Mode or privilege")
        raise
    with pytest.raises(importer.IdentityImportError, match="symbolic link"):
        importer.destination_path(link)
    alias = tmp_path / "checkout-alias"
    alias.symlink_to(importer.CHECKOUT, target_is_directory=True)
    with pytest.raises(importer.IdentityImportError, match="outside the repository"):
        importer.destination_path(alias / "new-identity")


def test_failed_write_removes_partial_identity(importer, identity, tmp_path, monkeypatch):
    original_open = os.open

    def fail_second(path, *args):
        if Path(path).name == "identity.pk8":
            raise OSError("synthetic write failure")
        return original_open(path, *args)

    destination = tmp_path / "identity"
    monkeypatch.setattr(importer.os, "open", fail_second)
    with pytest.raises(OSError, match="synthetic write failure"):
        importer.write_identity(identity, destination)
    assert not destination.exists()


@pytest.mark.parametrize("source", ["local", "download"])
def test_cli_import_with_synthetic_release(
    importer, identity, tmp_path, monkeypatch, capsys, source
):
    data = apk_bytes(importer, identity)
    monkeypatch.setattr(importer, "APK_SHA256", hashlib.sha256(data).hexdigest())
    apk = tmp_path / "synthetic.apk"
    apk.write_bytes(data)
    destination = tmp_path / "identity with space"
    if source == "local":
        args = ["--apk", str(apk)]
    else:
        def fake_urlopen(request, timeout):
            assert request.full_url == importer.APK_URL
            assert timeout == 30
            stream = io.BytesIO(data)
            stream.geturl = lambda: importer.APK_URL
            return stream

        monkeypatch.setattr(importer.urllib.request, "urlopen", fake_urlopen)
        args = ["--download"]
    assert importer.main([*args, "--output-dir", str(destination)]) == 0
    output = capsys.readouterr().out
    for variable, filename in (
        ("IAP2_LOCATION_BRIDGE_WINDOWS_CERT_FILE", "certificate.p7b"),
        ("IAP2_LOCATION_BRIDGE_WINDOWS_KEY_FILE", "identity.pk8"),
    ):
        assert importer.environment_assignment(variable, destination / filename) in output
    assert "not guaranteed" in output
    assert (destination / "identity.pk8").read_bytes() == identity["identity.pk8"]


def test_cli_bad_archive_writes_nothing(importer, tmp_path, capsys):
    apk = tmp_path / "wrong.apk"
    apk.write_bytes(b"not the pinned APK")
    destination = tmp_path / "identity"
    assert importer.main(["--apk", str(apk), "--output-dir", str(destination)]) == 1
    assert "SHA-256 mismatch" in capsys.readouterr().err
    assert not destination.exists()


def test_download_is_bounded(importer, monkeypatch):
    monkeypatch.setattr(importer, "MAX_APK_BYTES", 10)
    response = io.BytesIO(b"x" * 11)
    response.geturl = lambda: importer.APK_URL
    monkeypatch.setattr(importer.urllib.request, "urlopen", lambda *a, **kw: response)
    with pytest.raises(importer.IdentityImportError, match="download size limit"):
        importer.download_apk(io.BytesIO())


def assert_private_windows_acl(path, protected=False):
    import ntsecuritycon
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    descriptor = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
    if protected:
        assert descriptor.GetSecurityDescriptorControl()[0] & win32security.SE_DACL_PROTECTED
    acl = descriptor.GetSecurityDescriptorDacl()
    assert acl is not None and acl.GetAceCount() == 1
    header, mask, sid = acl.GetAce(0)
    assert header[0] == win32security.ACCESS_ALLOWED_ACE_TYPE
    assert sid == user
    assert mask == ntsecuritycon.FILE_ALL_ACCESS


def test_windows_shell_quoting_and_default(importer, monkeypatch):
    monkeypatch.setattr(importer.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(Path.home() / "Local Test"))
    assert importer.default_identity_dir() == Path.home() / "Local Test/iap2-location-bridge-windows/identity"
    assert importer.environment_assignment("TEST", "a'b c") == "$env:TEST = 'a''b c'"


@pytest.mark.parametrize("case", ["valid", "wrong_digest", "invalid_digest", "existing"])
def test_local_apk_cli(importer, identity, tmp_path, monkeypatch, capsys, case):
    local = importlib.import_module("import_local_identity")
    data = apk_bytes(importer, identity)
    apk = tmp_path / "user-supplied.apk"
    apk.write_bytes(data)
    destination = tmp_path / "local identity"
    digest = hashlib.sha256(data).hexdigest().upper()
    if case == "wrong_digest":
        digest = "0" * 64
    elif case == "invalid_digest":
        digest = "invalid"
    elif case == "existing":
        destination.mkdir()
        (destination / "sentinel").write_text("original")
    monkeypatch.setattr(local.sys, "argv", [
        "import_local_identity.py", "--apk", str(apk), "--sha256", digest,
        "--output-dir", str(destination),
    ])
    if case == "invalid_digest":
        with pytest.raises(SystemExit) as error:
            local.main()
        assert error.value.code == 2
        assert not destination.exists()
    elif case == "valid":
        assert local.main() == 0
        assert (destination / "identity.pk8").read_bytes() == identity["identity.pk8"]
    elif case == "wrong_digest":
        assert local.main() == 1
        error = capsys.readouterr().err
        assert "SHA-256 mismatch" in error
        assert "v0.2.7" not in error
        assert not destination.exists()
    else:
        assert local.main() == 1
        assert (destination / "sentinel").read_text() == "original"
        assert not (destination / "identity.pk8").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL enforcement")
def test_no_private_data_written_if_acl_cannot_be_verified(importer, identity, tmp_path, monkeypatch):
    import win32security

    def unavailable(*args):
        raise OSError("security descriptors unavailable")

    destination = tmp_path / "identity"
    monkeypatch.setattr(win32security, "GetFileSecurity", unavailable)
    with pytest.raises(importer.IdentityImportError, match="ACL"):
        importer.write_identity(identity, destination)
    assert not destination.exists()
