#!/usr/bin/env python3
"""Verify the local machine is ready to run the video-editor pipeline.

Checks: DaVinci Resolve is running and reachable via its scripting API,
ffmpeg/ffprobe are on PATH, faster-whisper is importable. Prints a plain-text
report with copy-pasteable fixes, and a machine-readable summary as JSON on
stdout when --json is passed. Exits non-zero if any critical check fails.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys


def check_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    ok = bool(ffmpeg and ffprobe)
    fix = None
    if not ok:
        system = platform.system()
        if system == "Darwin":
            fix = "brew install ffmpeg"
        elif system == "Linux":
            fix = "sudo apt install ffmpeg   # or your distro's equivalent"
        else:
            fix = "Download a build from https://ffmpeg.org/download.html and add it to PATH"
    return {"name": "ffmpeg/ffprobe", "ok": ok, "fix": fix}


def check_faster_whisper():
    try:
        import faster_whisper  # noqa: F401

        return {"name": "faster-whisper", "ok": True, "fix": None}
    except ImportError:
        return {
            "name": "faster-whisper",
            "ok": False,
            "fix": "pip3 install faster-whisper",
        }


def _resolve_script_api_candidates():
    system = platform.system()
    if system == "Darwin":
        return [
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
        ]
    if system == "Windows":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return [
            os.path.join(
                program_data,
                "Blackmagic Design",
                "DaVinci Resolve",
                "Support",
                "Developer",
                "Scripting",
            )
        ]
    # Linux
    return [
        "/opt/resolve/Developer/Scripting",
        "/home/resolve/Developer/Scripting",
    ]


def check_resolve():
    api_path = os.environ.get("RESOLVE_SCRIPT_API")
    candidates = [api_path] if api_path else _resolve_script_api_candidates()
    found_path = next((p for p in candidates if p and os.path.isdir(p)), None)

    if not found_path:
        return {
            "name": "DaVinci Resolve scripting API",
            "ok": False,
            "fix": (
                "Could not find the Resolve scripting API folder. Install DaVinci Resolve, "
                "then set RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB / PYTHONPATH — see "
                "references/resolve_scripting_api.md for the exact values for your OS."
            ),
        }

    modules_path = os.path.join(found_path, "Modules")
    if modules_path not in sys.path:
        sys.path.append(modules_path)

    try:
        import DaVinciResolveScript as dvr_script  # noqa: N813
    except ImportError as e:
        return {
            "name": "DaVinci Resolve scripting API",
            "ok": False,
            "fix": (
                f"Found the API folder at {found_path} but couldn't import the module "
                f"({e}). Check RESOLVE_SCRIPT_LIB is also set — see "
                "references/resolve_scripting_api.md."
            ),
        }

    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        return {
            "name": "DaVinci Resolve scripting API",
            "ok": False,
            "fix": (
                "The API module loaded but couldn't reach a running Resolve instance. "
                "Make sure DaVinci Resolve is open, and Preferences > General > "
                "'External scripting using' is set to 'Local' (restart Resolve after "
                "changing this)."
            ),
        }

    version = None
    try:
        version = resolve.GetVersionString()
    except Exception:
        pass

    return {
        "name": "DaVinci Resolve scripting API",
        "ok": True,
        "fix": None,
        "detail": f"connected, version {version}" if version else "connected",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON only")
    args = parser.parse_args()

    checks = [check_resolve(), check_ffmpeg(), check_faster_whisper()]
    all_ok = all(c["ok"] for c in checks)

    if args.json:
        print(json.dumps({"ok": all_ok, "checks": checks}, indent=2))
    else:
        for c in checks:
            status = "OK" if c["ok"] else "MISSING"
            line = f"[{status}] {c['name']}"
            if c.get("detail"):
                line += f" ({c['detail']})"
            print(line)
            if not c["ok"] and c.get("fix"):
                print(f"        fix: {c['fix']}")
        print()
        print("All checks passed." if all_ok else "Fix the items above before continuing.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
