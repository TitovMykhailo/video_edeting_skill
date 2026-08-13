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
import build_project_via_otio_import  # noqa: E402


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

    # "build_mode": "otio_import" (default) uses build_project_via_otio_import.py — builds an
    # .otio file and imports it via MediaPool.ImportTimelineFromFile instead of AppendToTimeline.
    # Why this is the default now: on a real project, AppendToTimeline reported complete success
    # for the video track (correct count, correct per-clip properties, a post-save re-read all
    # confirmed durable) while the placed items were never real/interactive — invisible and
    # unselectable in the Edit page, and both a direct frame export and the final render came back
    # solid black throughout. The exact same narration audio, placed via AppendToTimeline WITHOUT
    # an explicit recordFrame, worked fine — only explicit-recordFrame video placement showed
    # this. Importing the identical beats via OTIO instead (a different code path entirely)
    # produced a real, visible, editable timeline on the same installation. Set
    # "build_mode": "append_to_timeline" to use the original path if a future Resolve
    # update fixes the underlying AppendToTimeline issue and direct placement is preferred again
    # (it doesn't need the extra OTIO round-trip, and it's the only path that also places SFX/
    # music gain levels automatically — see build_project_via_otio_import.py's docstring).
    build_mode = job.get("build_mode", "otio_import")

    if build_mode == "otio_import":
        argv = [
            "build_project_via_otio_import.py",
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
            build_project_via_otio_import.main()
        except (RuntimeError, FileNotFoundError, ValueError, KeyError) as e:
            print(f"\nERROR: {e}", file=sys.stderr)
        return

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
    if job.get("skip_color_grade"):
        argv += ["--skip-color-grade"]

    sys.argv = argv
    try:
        build_project.main()
    except (RuntimeError, FileNotFoundError, ValueError, KeyError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)


main()
