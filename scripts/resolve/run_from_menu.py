#!/usr/bin/env python
"""Menu-runnable entry point for build_project.py — this is the TEMPLATE; the installed copy
inside Resolve's Scripts folder is generated from it by install_menu_script.py and should not be
hand-edited there. Edit this repo copy and re-run the installer instead.

Why this exists: DaVinci Resolve Free blocks requesting a *fresh* scripting connection
(`scriptapp("Resolve")`) — confirmed this is true even for a script Resolve itself runs via
Workspace > Scripts, not just an external terminal process (both got `None` in testing). What
Free does allow is *using* a connection Resolve hands you: when it launches a script via the
Scripts menu (same as the F6 Console), it pre-injects an already-connected `resolve` object as a
global into that script's `__main__` — confirmed by a direct diagnostic script dumping its own
globals on a real Free install, which showed a live `Resolve (0x...) [App: 'Resolve' on
127.0.0.1, ...]` object sitting there before any of our code ran. `connect.get_resolve()` checks
for that pre-injected global first and only falls back to requesting a fresh connection if it's
missing — which is what makes it work here. This wrapper is what lets the full build_project.py
pipeline (timeline build, color grade, clip gains, render) run on Free, triggered by one click in
the menu, instead of only the more limited scripts/resolve/build_otio.py structural-import path.

Each run reads its parameters from a job JSON file, since Resolve's Scripts menu doesn't pass CLI
args the way a terminal invocation would — see references/resolve_scripting_api.md's "Running
from the menu" section for the schema.
"""
import json
import os
import sys

SKILL_SCRIPTS_ROOT = __SKILL_SCRIPTS_ROOT__
JOB_FILE = __JOB_FILE__

if SKILL_SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS_ROOT)

import build_project  # noqa: E402


def main():
    if not os.path.exists(JOB_FILE):
        print(
            f"ERROR: no job file at {JOB_FILE}. Ask Claude Code to write one (schema in "
            'references/resolve_scripting_api.md\'s "Running from the menu" section), then run '
            "this again.",
            file=sys.stderr,
        )
        return

    with open(JOB_FILE, encoding="utf-8") as f:
        job = json.load(f)

    argv = [
        "build_project.py",
        "--project-name", job["project_name"],
        "--narration-audio", job["narration_audio"],
        "--edit-plan", job["edit_plan"],
        "--beat-plan", job["beat_plan"],
        "--style", job["style"],
        "--aspect", job["aspect"],
        "--media-library", job["media_library"],
    ]
    if job.get("sound_library"):
        argv += ["--sound-library", job["sound_library"]]
    if job.get("captions"):
        argv += ["--captions", job["captions"]]
    if job.get("render_out"):
        argv += ["--render-out", job["render_out"]]

    sys.argv = argv
    try:
        build_project.main()
    except (RuntimeError, FileNotFoundError, ValueError, KeyError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)


main()
