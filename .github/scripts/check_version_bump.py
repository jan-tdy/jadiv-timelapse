#!/usr/bin/env python3
"""Fails if this PR doesn't bump the app version relative to its base branch.

Checked in CI by .github/workflows/version-bump.yml on every pull request.
"""
import json
import re
import subprocess
import sys

METADATA_FILE = "codemaster-metadata.json"
PY_FILE = "jadiv-timelapse_plus.py"
HTML_FILE = "docs/index.html"


def version_tuple(version):
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts) if parts else (0,)


def get_metadata_version(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["apps"][0]["version"]


def get_pattern_version(path, pattern):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    match = re.search(pattern, content)
    if not match:
        sys.exit(f"Could not find a version string in {path}")
    return match.group(1)


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: check_version_bump.py <base-ref>")
    base_ref = sys.argv[1]

    head_metadata_version = get_metadata_version(METADATA_FILE)
    head_py_version = get_pattern_version(PY_FILE, r'APP_VERSION\s*=\s*"([^"]+)"')
    head_html_version = get_pattern_version(HTML_FILE, r"APP_VERSION\s*=\s*'([^']+)'")

    if not (head_metadata_version == head_py_version == head_html_version):
        sys.exit(
            "Version mismatch between files - all three must be bumped to the same version:\n"
            f"  {METADATA_FILE}: {head_metadata_version}\n"
            f"  {PY_FILE}: {head_py_version}\n"
            f"  {HTML_FILE}: {head_html_version}\n"
        )

    base_content = subprocess.run(
        ["git", "show", f"origin/{base_ref}:{METADATA_FILE}"],
        capture_output=True, text=True, check=True,
    ).stdout
    base_version = json.loads(base_content)["apps"][0]["version"]

    if version_tuple(head_metadata_version) <= version_tuple(base_version):
        sys.exit(
            f"Version was not bumped: base branch '{base_ref}' has {base_version}, this PR "
            f"still has {head_metadata_version}. Bump the version in {METADATA_FILE}, "
            f"{PY_FILE} (APP_VERSION) and {HTML_FILE} (APP_VERSION)."
        )

    print(f"Version bump OK: {base_version} -> {head_metadata_version}")


if __name__ == "__main__":
    main()
