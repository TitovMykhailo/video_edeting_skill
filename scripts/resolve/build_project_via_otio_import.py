#!/usr/bin/env python3
"""Build the DaVinci Resolve project by importing an OTIO file instead of AppendToTimeline.

Why this exists: on a real project, MediaPool.AppendToTimeline reported complete success —
correct item count, correct per-clip name/start/end/enabled/opacity/composite-mode properties,
even a post-save re-read via GetItemListInTrack confirming the placement was durable — while the
placed items never became real, interactive timeline items. The video track was empty in the
Edit page (not selectable, not splittable), a direct ExportCurrentFrameAsStill grab (bypassing
the render/deliver pipeline entirely) came back solid black at every point on the timeline, and
the final render was black too. The SAME narration audio, placed via AppendToTimeline WITHOUT an
explicit `recordFrame` (append-sequentially, since it's a single clip), worked fine and rendered
with correct, audible levels — only explicit-recordFrame VIDEO placement showed this failure, on
this installation. Root cause in AppendToTimeline itself was not pinned down further; this works
around it instead of chasing it more. Confirmed live: importing the exact same beats via OTIO
(MediaPool.ImportTimelineFromFile — the same underlying mechanism as Resolve's own File > Import
Timeline > OpenTimelineIO menu item, a completely different code path from AppendToTimeline)
produced a real, visible, editable timeline on the same installation, same project, same clips.

Builds the .otio file with build_otio.py's own logic (identical track/frame-exact math — see
that module for the OTIO construction itself), imports it into the live project via
ImportTimelineFromFile, then does what build_project.py normally does after building the
timeline: apply the color grade via SetCDL, print the manual caption-import instruction, and
render. SFX/music clips DO get placed on real timeline audio tracks at their correct times
(build_otio.py's build_sfx_tracks()/build_music_track()) — only the per-clip gain_db value isn't
applied automatically (OTIO has no reliable clip-gain carrier to round-trip through Resolve's
importer), so build_otio.py's manual_steps.md lists every gain value to punch in by hand. Remember
--sound-library here is a separate root from --media-library, same convention as
assemble_video.py's --sound-library — it needs to point at wherever the project's actual sfx/
folder lives (often the project directory itself), not the shared meme/video library root; passing
the wrong one fails fast with "Could not resolve media path" for the first sfx cue rather than
silently placing nothing.

Usage: same arguments as build_project.py.
"""
import argparse
import json
import os
import sys

_RESOLVE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _RESOLVE_DIR)

import build_otio  # noqa: E402
import captions as captions_mod  # noqa: E402
import color_grade  # noqa: E402
import connect  # noqa: E402
import project_setup  # noqa: E402
import render as render_mod  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--narration-audio", required=True)
    parser.add_argument("--edit-plan", required=True)
    parser.add_argument("--beat-plan", required=True)
    parser.add_argument("--captions", help="path to captions.srt (omit to skip captions)")
    parser.add_argument("--style", required=True)
    parser.add_argument("--aspect", required=True, choices=["16:9", "9:16"])
    parser.add_argument("--media-library", required=True)
    parser.add_argument("--sound-library", help="defaults to --media-library")
    parser.add_argument("--render-out", help="omit to build the timeline without rendering")
    args = parser.parse_args()

    with open(args.style, encoding="utf-8") as f:
        style = json.load(f)

    out_dir = os.path.dirname(os.path.abspath(args.beat_plan))
    otio_path = os.path.join(out_dir, "_timeline_via_import.otio")

    print("Building .otio timeline file (build_otio.py's own logic)...", file=sys.stderr)
    otio_argv = [
        "build_otio.py",
        "--project-name", args.project_name,
        "--narration-audio", args.narration_audio,
        "--edit-plan", args.edit_plan,
        "--beat-plan", args.beat_plan,
        "--style", args.style,
        "--aspect", args.aspect,
        "--media-library", args.media_library,
        "--out", otio_path,
    ]
    if args.sound_library:
        otio_argv += ["--sound-library", args.sound_library]
    saved_argv = sys.argv
    sys.argv = otio_argv
    try:
        build_otio.main()
    finally:
        sys.argv = saved_argv

    width, height, fps = project_setup.aspect_settings(style, args.aspect)

    print("Connecting to DaVinci Resolve...", file=sys.stderr)
    resolve = connect.get_resolve()
    project_manager = resolve.GetProjectManager()
    project = project_setup.ensure_project(project_manager, args.project_name)
    project_setup.set_timeline_format(project, width, height, fps)
    print(f"Project '{args.project_name}' ready at {width}x{height}@{fps}fps.", file=sys.stderr)

    media_pool = project.GetMediaPool()
    timeline_name = f"{args.project_name} Timeline (OTIO import)"

    # Same "delete any leftover same-named timeline first" discipline as
    # timeline_build.ensure_empty_timeline, so re-running this after any failure is safe to just
    # retry rather than requiring manual cleanup in Resolve's UI first.
    existing = None
    for i in range(1, project.GetTimelineCount() + 1):
        tl = project.GetTimelineByIndex(i)
        if tl and tl.GetName() == timeline_name:
            existing = tl
            break
    if existing is not None:
        media_pool.DeleteTimelines([existing])

    print(f"Importing {otio_path} via MediaPool.ImportTimelineFromFile...", file=sys.stderr)
    new_timeline = media_pool.ImportTimelineFromFile(
        os.path.abspath(otio_path),
        {"timelineName": timeline_name, "importSourceClips": True, "sourceClipsPath": args.media_library},
    )
    if new_timeline is None:
        raise RuntimeError(
            f"ImportTimelineFromFile returned None for {otio_path}. Resolve gives no error message "
            "for this call — common causes: a timeline named "
            f"'{timeline_name}' already existed (this run's own cleanup should have removed it — "
            "check the Media Pool by hand if it didn't), or the .otio file itself failed to parse."
        )
    project.SetCurrentTimeline(new_timeline)
    video_track_count = new_timeline.GetTrackCount("video")
    print(f"Imported timeline '{new_timeline.GetName()}' with {video_track_count} video track(s).", file=sys.stderr)

    video_items = []
    for t_idx in range(1, video_track_count + 1):
        items = new_timeline.GetItemListInTrack("video", t_idx)
        if items:
            video_items.extend(items)
    print(f"Found {len(video_items)} video item(s) on the imported timeline.", file=sys.stderr)

    color_config = style.get("color")
    if color_config and color_config.get("grade_cdl") and video_items:
        print("Applying color grade to video clips...", file=sys.stderr)
        applied, _ = color_grade.apply_grade_or_warn(video_items, color_config)
        print(f"Color grade applied to {applied}/{len(video_items)} clips.", file=sys.stderr)

    if args.captions and style.get("captions", {}).get("enabled", True):
        print(captions_mod.manual_import_message(os.path.abspath(args.captions)), file=sys.stderr)

    if args.render_out:
        print(f"Rendering draft to {args.render_out}...", file=sys.stderr)
        result = render_mod.render_timeline(project, args.render_out, style.get("render", {}).get("preset"))
        print(f"Render complete: {result}", file=sys.stderr)
    else:
        print("No --render-out given, skipping render. Project timeline is built and open in Resolve.", file=sys.stderr)

    print("Done. The project is left open in Resolve for review/manual polish.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
