#!/usr/bin/env python3
"""Install run_from_menu.py into DaVinci Resolve's Scripts menu (Workspace > Scripts > Comp).

Run this once per machine (and again if this skill's folder ever moves). It copies
run_from_menu.py into Resolve's per-user Scripts/Comp folder, substituting in this repo's
absolute path via repr() (not a naive string replace — a raw Windows path like
C:\\Users\\titov\\... pasted directly between quotes would corrupt itself the moment it hit a
backslash-letter pair Python treats as an escape, e.g. \\t in "titov") so the installed copy can
still import build_project.py and its sibling modules as if running from here.

Usage:
    python3 install_menu_script.py

Then in Resolve: Workspace > Scripts > Comp > build_video_project (restart Resolve first if it
was already running when you installed this — it only scans the Scripts folder at startup).

See references/resolve_scripting_api.md's "Running from the menu" section for what this buys you
on DaVinci Resolve Free (the full build_project.py pipeline via one click in Resolve, instead of
the more limited scripts/resolve/build_otio.py structural-import path).
"""
import argparse
import os
import platform
import sys


def scripts_comp_folder():
    system = platform.system()
    if system == "Darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp"
        )
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("%APPDATA% isn't set — can't locate Resolve's Scripts folder.")
        return os.path.join(
            appdata, "Blackmagic Design", "DaVinci Resolve", "Support", "Fusion", "Scripts", "Comp"
        )
    return os.path.expanduser("~/.local/share/DaVinciResolve/Fusion/Scripts/Comp")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--name", default="build_video_project",
        help="menu entry name, also the installed filename minus .py (default: build_video_project)",
    )
    parser.add_argument(
        "--job-file",
        help="path to the job JSON this menu entry will read each run (default: <skill root>/.resolve_job.json)",
    )
    args = parser.parse_args()

    scripts_root = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(os.path.dirname(scripts_root))
    job_file = os.path.abspath(args.job_file) if args.job_file else os.path.join(skill_root, ".resolve_job.json")

    template_path = os.path.join(scripts_root, "run_from_menu.py")
    if not os.path.exists(template_path):
        raise RuntimeError(f"Template not found at {template_path} — is this repo intact?")
    with open(template_path, encoding="utf-8") as f:
        content = f.read()

    content = content.replace("__SKILL_SCRIPTS_ROOT__", repr(scripts_root))
    content = content.replace("__JOB_FILE__", repr(job_file))

    dest_folder = scripts_comp_folder()
    os.makedirs(dest_folder, exist_ok=True)
    dest_path = os.path.join(dest_folder, f"{args.name}.py")
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Installed: {dest_path}", file=sys.stderr)
    print(f"Reads its job from: {job_file}", file=sys.stderr)
    print(
        f"In Resolve: Workspace > Scripts > Comp > {args.name} "
        "(restart Resolve first if it was already running when you installed this).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
