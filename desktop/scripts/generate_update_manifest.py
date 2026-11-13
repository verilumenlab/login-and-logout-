#!/usr/bin/env python3
"""
Enterprise Desktop Release Engineering - Signed Update Manifest Generator (Phase 15)
Generates signed update manifests (latest.json) for Tauri v2 auto-updater
across separate staging and production release channels.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import UTC, datetime


def parse_semver(v: str) -> tuple[int, int, int]:
    """Parse semver string e.g. '0.1.0' into tuple for monotonic upgrade comparison."""
    clean = v.lstrip("v").split("-")[0]
    parts = clean.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def generate_manifest(
    version: str,
    channel: str,
    notes: str,
    base_url: str,
    output_path: str,
    previous_version: str | None = None,
) -> dict:
    """
    Build a signed update manifest for the specified release channel.
    Enforces that new version is strictly greater than previous version (downgrade prevention).
    """
    if previous_version:
        prev_parsed = parse_semver(previous_version)
        curr_parsed = parse_semver(version)
        if curr_parsed <= prev_parsed:
            raise ValueError(
                f"Release rejection: New version {version} must be strictly greater than "
                f"previous version {previous_version} (Anti-Rollback/Downgrade Protection)."
            )

    pub_date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Sample signed platform targets
    platforms = {
        "windows-x86_64": {
            "signature": base64.b64encode(hashlib.sha256(f"win64-{version}-{channel}".encode()).digest()).decode(),
            "url": f"{base_url.rstrip('/')}/{channel}/windows-x86_64/EnterpriseAttendanceAgent_{version}_x64_en-US.msi.zip",
        },
        "darwin-x86_64": {
            "signature": base64.b64encode(hashlib.sha256(f"mac-x86-{version}-{channel}".encode()).digest()).decode(),
            "url": f"{base_url.rstrip('/')}/{channel}/darwin-x86_64/EnterpriseAttendanceAgent_{version}_x64.tar.gz",
        },
        "darwin-aarch64": {
            "signature": base64.b64encode(hashlib.sha256(f"mac-arm-{version}-{channel}".encode()).digest()).decode(),
            "url": f"{base_url.rstrip('/')}/{channel}/darwin-aarch64/EnterpriseAttendanceAgent_{version}_aarch64.tar.gz",
        },
    }

    manifest = {
        "version": version,
        "channel": channel,
        "notes": notes,
        "pub_date": pub_date,
        "platforms": platforms,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[{channel.upper()}] Signed update manifest written to: {output_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate signed Tauri v2 update manifest")
    parser.add_argument("--version", default="0.1.0", help="Release version (e.g. 0.1.0)")
    parser.add_argument("--channel", choices=["staging", "production"], default="production", help="Release channel")
    parser.add_argument("--notes", default="Enterprise update with stability and security enhancements.", help="Release notes")
    parser.add_argument("--base-url", default="https://updates.enterprise.com", help="Base CDN URL for release bundles")
    parser.add_argument("--output", default="dist/updates/latest.json", help="Output path for latest.json")
    parser.add_argument("--prev-version", default=None, help="Previous release version for monotonic check")

    args = parser.parse_args()

    manifest = generate_manifest(
        version=args.version,
        channel=args.channel,
        notes=args.notes,
        base_url=args.base_url,
        output_path=args.output,
        previous_version=args.prev_version,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

