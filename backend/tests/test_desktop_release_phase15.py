"""
Phase 15 Desktop Release Engineering Test Suite
Verifies:
- Signed Update Manifest Generation & JSON Schema
- Separate Staging and Production Update Channels
- Anti-Rollback & Downgrade Prevention
- Version Compatibility Matrix & Semver Evaluation
- Windows NSIS Installer Configuration & Silent Switch Handlers
- macOS LaunchAgent Property List Configuration
- Tauri Updater Configuration & Pinned Cryptographic Keys
"""

import json
import os
import sys
import plistlib
import pytest

# Ensure repository root is on sys.path for desktop scripts import
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from desktop.scripts.generate_update_manifest import generate_manifest, parse_semver


def test_update_manifest_generation_and_schema(tmp_path):
    """Verify update manifest generation generates valid JSON matching Tauri v2 schema."""
    output_path = tmp_path / "latest.json"
    manifest = generate_manifest(
        version="0.1.0",
        channel="production",
        notes="Production release with stability enhancements",
        base_url="https://updates.enterprise.com",
        output_path=str(output_path),
    )

    assert manifest["version"] == "0.1.0"
    assert manifest["channel"] == "production"
    assert "pub_date" in manifest
    assert "platforms" in manifest

    platforms = manifest["platforms"]
    assert "windows-x86_64" in platforms
    assert "darwin-x86_64" in platforms
    assert "darwin-aarch64" in platforms

    for target, info in platforms.items():
        assert "signature" in info
        assert "url" in info
        assert info["url"].startswith("https://updates.enterprise.com/production/")
        assert len(info["signature"]) > 10


def test_staging_and_production_channels(tmp_path):
    """Verify separate staging and production manifests point to isolated channel directories."""
    staging_file = tmp_path / "staging" / "latest.json"
    prod_file = tmp_path / "production" / "latest.json"

    staging_manifest = generate_manifest(
        version="0.2.0-beta.1",
        channel="staging",
        notes="Staging pilot release",
        base_url="https://updates.enterprise.com",
        output_path=str(staging_file),
    )

    prod_manifest = generate_manifest(
        version="0.1.0",
        channel="production",
        notes="General availability production release",
        base_url="https://updates.enterprise.com",
        output_path=str(prod_file),
    )

    assert staging_manifest["channel"] == "staging"
    assert prod_manifest["channel"] == "production"

    assert "staging" in staging_manifest["platforms"]["windows-x86_64"]["url"]
    assert "production" in prod_manifest["platforms"]["windows-x86_64"]["url"]


def test_anti_rollback_and_downgrade_prevention(tmp_path):
    """Verify anti-rollback: attempting to release version <= previous version is rejected."""
    out_file = tmp_path / "latest.json"

    # 1. Monotonically increasing version (0.1.1 > 0.1.0) -> Allowed
    valid_manifest = generate_manifest(
        version="0.1.1",
        channel="production",
        notes="Patch release",
        base_url="https://updates.enterprise.com",
        output_path=str(out_file),
        previous_version="0.1.0",
    )
    assert valid_manifest["version"] == "0.1.1"

    # 2. Downgrade attempt (0.0.9 < 0.1.0) -> MUST FAIL
    with pytest.raises(ValueError) as exc1:
        generate_manifest(
            version="0.0.9",
            channel="production",
            notes="Illegal downgrade attempt",
            base_url="https://updates.enterprise.com",
            output_path=str(out_file),
            previous_version="0.1.0",
        )
    assert "Anti-Rollback/Downgrade Protection" in str(exc1.value)

    # 3. Same version re-release (0.1.0 == 0.1.0) -> MUST FAIL
    with pytest.raises(ValueError) as exc2:
        generate_manifest(
            version="0.1.0",
            channel="production",
            notes="Duplicate release attempt",
            base_url="https://updates.enterprise.com",
            output_path=str(out_file),
            previous_version="0.1.0",
        )
    assert "Anti-Rollback/Downgrade Protection" in str(exc2.value)


def test_semver_parsing_and_monotonicity():
    """Verify semver parsing logic handles prefixes and build metadata."""
    assert parse_semver("0.1.0") == (0, 1, 0)
    assert parse_semver("v1.2.3") == (1, 2, 3)
    assert parse_semver("2.0.1-beta") == (2, 0, 1)


def get_repo_root() -> str:
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, "desktop")):
        return cwd
    parent = os.path.dirname(cwd)
    if os.path.exists(os.path.join(parent, "desktop")):
        return parent
    return cwd


def test_windows_nsis_installer_configuration():
    """Verify NSIS installer script contains enterprise silent installation flags and startup keys."""
    nsis_path = os.path.join(get_repo_root(), "desktop", "src-tauri", "windows", "installer.nsi")
    assert os.path.exists(nsis_path)

    with open(nsis_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check key enterprise directives
    assert "InstallDir" in content
    assert "RequestExecutionLevel admin" in content
    assert "UninstallString" in content
    assert "QuietUninstallString" in content
    assert "Software\\Microsoft\\Windows\\CurrentVersion\\Run" in content
    assert "schtasks" in content
    assert "taskkill" in content


def test_macos_launchagent_plist_structure():
    """Verify macOS LaunchAgent plist structure, keys, and background arguments."""
    plist_path = os.path.join(get_repo_root(), "desktop", "src-tauri", "macos", "com.enterprise.attendance.agent.plist")
    assert os.path.exists(plist_path)

    with open(plist_path, "rb") as f:
        plist_data = plistlib.load(f)

    assert plist_data.get("Label") == "com.enterprise.attendance.agent"
    assert plist_data.get("RunAtLoad") is True
    assert plist_data.get("KeepAlive") == {"SuccessfulExit": False, "Crashed": True}

    args = plist_data.get("ProgramArguments", [])
    assert len(args) == 2
    assert "enterprise-attendance-desktop" in args[0]
    assert args[1] == "--background"


def test_tauri_updater_and_security_configuration():
    """Verify tauri.conf.json has pinned Ed25519 public key and update endpoints configured."""
    tauri_conf_path = os.path.join(get_repo_root(), "desktop", "src-tauri", "tauri.conf.json")
    assert os.path.exists(tauri_conf_path)

    with open(tauri_conf_path, "r", encoding="utf-8") as f:
        conf = json.load(f)

    plugins = conf.get("plugins", {})
    updater = plugins.get("updater", {})

    assert "pubkey" in updater
    assert len(updater["pubkey"]) > 20
    assert "endpoints" in updater
    assert len(updater["endpoints"]) >= 2
    assert any("production" in ep for ep in updater["endpoints"])
    assert any("staging" in ep for ep in updater["endpoints"])
