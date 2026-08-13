#!/usr/bin/env python3
"""Build the DaVinci Resolve project: import media, build tracks, add sound + color, render a draft.

Usage:
    python3 build_project.py --project-name "My Video" \
        --narration-audio project/narration.wav \
        --edit-plan project/out/edit_plan.json \
        --beat-plan project/out/beat_plan.json \
        --captions project/out/captions.srt \
        --style project/style.json \
        --aspect 16:9 \
        --media-library /path/to/media-library \
        [--sound-library /path/to/sound-library] \
        --render-out project/out/render.mp4

`--sound-library` defaults to `--media-library` if omitted — pass it separately only if SFX/music
live in a different folder than visual clips. This is the step that actually talks to a running
local DaVinci Resolve — run scripts/check_environment.py first if you haven't already this
session. It leaves the project open afterward for manual polish; it does not close Resolve or the
project when done.
"""
import argparse
import json
import os
import sys

_RESOLVE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _RESOLVE_DIR)
sys.path.insert(0, os.path.dirname(_RESOLVE_DIR))  # scripts/ root, for render_narration_audio

import audio_design  # noqa: E402
import captions as captions_mod  # noqa: E402
import color_grade  # noqa: E402
import connect  # noqa: E402
import project_setup  # noqa: E402
import render as render_mod  # noqa: E402
import render_narration_audio  # noqa: E402
import timeline_build  # noqa: E402


def resolve_media_path(path, library):
    if os.path.isabs(path) and os.path.exists(path):
        return path
    candidate = os.path.join(library, path)
    if os.path.exists(candidate):
        return candidate
    raise FileNotFoundError(f"Could not resolve media path '{path}' under library '{library}'")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--narration-audio", required=True)
    parser.add_argument("--edit-plan", required=True)
    parser.add_argument("--beat-plan", required=True)
    parser.add_argument("--captions", help="path to captions.srt (omit to skip captions)")
    parser.add_argument("--style", required=True)
    parser.add_argument("--aspect", required=True, choices=["16:9", "9:16"])
    parser.add_argument("--media-library", required=True, help="root the beat plan's visual media paths are relative to")
    parser.add_argument("--sound-library", help="root for sfx/music_bed paths (defaults to --media-library)")
    parser.add_argument("--render-out", help="omit to build the timeline without rendering")
    parser.add_argument("--skip-color-grade", action="store_true", help="build/render without applying color.grade_cdl — for isolating whether the grade step is involved in a rendering problem")
    args = parser.parse_args()

    sound_library = args.sound_library or args.media_library

    with open(args.style, encoding="utf-8") as f:
        style = json.load(f)
    with open(args.edit_plan, encoding="utf-8") as f:
        edit_plan = json.load(f)
    with open(args.beat_plan, encoding="utf-8") as f:
        beat_plan = json.load(f)

    width, height, fps = project_setup.aspect_settings(style, args.aspect)

    print("Connecting to DaVinci Resolve...", file=sys.stderr)
    resolve = connect.get_resolve()
    project_manager = resolve.GetProjectManager()
    project = project_setup.ensure_project(project_manager, args.project_name)
    project_setup.set_timeline_format(project, width, height, fps)
    print(f"Project '{args.project_name}' ready at {width}x{height}@{fps}fps.", file=sys.stderr)

    # Diagnostic-only, written every run: Project.GetSetting() with no key returns a full
    # snapshot of every queryable project setting (documented in Resolve's own shipped README).
    # Written to disk instead of printed — some Resolve versions have hundreds of keys — so it
    # can be read back directly after a run without needing the Console output pasted back in.
    # Investigating a real case: correctly-placed, correctly-graded clips on an enabled track
    # rendering solid black, which points at something project-level (most likely color
    # management/color science) that none of the per-clip checks this build already does can see.
    try:
        settings_dump_path = os.path.join(os.path.dirname(os.path.abspath(args.beat_plan)), "_resolve_project_settings.json")
        with open(settings_dump_path, "w", encoding="utf-8") as f:
            json.dump(project.GetSetting(), f, ensure_ascii=False, indent=2, default=str)
        print(f"Wrote project settings snapshot to {settings_dump_path}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — diagnostic only, never fail the real build over this
        print(f"WARNING: could not write project settings snapshot: {e}", file=sys.stderr)

    media_pool = project.GetMediaPool()
    root_folder = media_pool.GetRootFolder()
    narration_folder = timeline_build.get_or_create_folder(media_pool, root_folder, "Narration")
    broll_folder = timeline_build.get_or_create_folder(media_pool, root_folder, "B-Roll and Memes")
    sound_folder = timeline_build.get_or_create_folder(media_pool, root_folder, "Sound Design")

    import_cache = {}
    narration_abs = os.path.abspath(args.narration_audio)
    declicked_path = os.path.join(os.path.dirname(args.edit_plan), "_narration_declicked.wav")
    print("Rendering declicked narration audio (fades each cut edge — see "
          "scripts/render_narration_audio.py)...", file=sys.stderr)
    render_narration_audio.render_declicked_narration(narration_abs, edit_plan, declicked_path)
    timeline_build.import_into_bin(media_pool, narration_folder, [declicked_path], import_cache)
    narration_item = import_cache[declicked_path]

    beat_media_abs_paths = []
    beat_abs_by_relpath = {}
    for beat in beat_plan["beats"]:
        rel = beat["media"]["path"]
        if rel not in beat_abs_by_relpath:
            abs_path = resolve_media_path(rel, args.media_library)
            beat_abs_by_relpath[rel] = abs_path
            beat_media_abs_paths.append(abs_path)
    timeline_build.import_into_bin(media_pool, broll_folder, beat_media_abs_paths, import_cache)
    media_item_by_relpath = {rel: import_cache[abs_p] for rel, abs_p in beat_abs_by_relpath.items()}

    sound_abs_paths = []
    sound_abs_by_relpath = {}
    for beat in beat_plan["beats"]:
        for sfx in beat.get("sfx", []):
            rel = sfx["path"]
            if rel not in sound_abs_by_relpath:
                abs_path = resolve_media_path(rel, sound_library)
                sound_abs_by_relpath[rel] = abs_path
                sound_abs_paths.append(abs_path)
    music_bed = beat_plan.get("music_bed")
    if music_bed:
        rel = music_bed["path"]
        if rel not in sound_abs_by_relpath:
            abs_path = resolve_media_path(rel, sound_library)
            sound_abs_by_relpath[rel] = abs_path
            sound_abs_paths.append(abs_path)
    if sound_abs_paths:
        timeline_build.import_into_bin(media_pool, sound_folder, sound_abs_paths, import_cache)
    sound_item_by_relpath = {rel: import_cache[abs_p] for rel, abs_p in sound_abs_by_relpath.items()}

    timeline = timeline_build.ensure_empty_timeline(media_pool, project, f"{args.project_name} Timeline")
    project.SetCurrentTimeline(timeline)
    timeline_build.ensure_audio_tracks(timeline, 3)  # 1=narration, 2=SFX, 3=music bed

    print("Placing declicked narration...", file=sys.stderr)
    timeline_build.build_audio_track_declicked(media_pool, timeline, narration_item, edit_plan["total_new_duration_s"], fps, track_index=1)

    print(f"Building video track from {len(beat_plan['beats'])} beats...", file=sys.stderr)
    video_items = timeline_build.build_video_track(media_pool, timeline, beat_plan, media_item_by_relpath, fps, track_index=1)

    # Diagnostic-only, same investigation as the project-settings snapshot above: track-level
    # enable is confirmed True and the clip/grade counts are both correct, yet a real render came
    # out solid black. GetClipEnabled/Opacity/CompositeMode are documented, per-CLIP properties
    # distinct from the track-level one already checked — none of this build's existing checks
    # read any of them. Dumped per clip so a real culprit (a clip disabled, or opacity 0, or an
    # unexpected composite mode) shows up directly instead of being guessed at.
    try:
        clip_diag = []
        for item in video_items:
            entry = {"name": item.GetName(), "start": item.GetStart(), "end": item.GetEnd()}
            try:
                entry["clip_enabled"] = item.GetClipEnabled()
            except Exception as e:  # noqa: BLE001
                entry["clip_enabled"] = f"ERROR: {e}"
            for prop in ("Opacity", "CompositeMode", "Pan", "Tilt", "ZoomX", "ZoomY"):
                try:
                    entry[prop] = item.GetProperty(prop)
                except Exception as e:  # noqa: BLE001
                    entry[prop] = f"ERROR: {e}"
            clip_diag.append(entry)
        clip_diag_path = os.path.join(os.path.dirname(os.path.abspath(args.beat_plan)), "_resolve_clip_diagnostics.json")
        with open(clip_diag_path, "w", encoding="utf-8") as f:
            json.dump(clip_diag, f, ensure_ascii=False, indent=2, default=str)
        print(f"Wrote per-clip diagnostics to {clip_diag_path}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — diagnostic only, never fail the real build over this
        print(f"WARNING: could not write per-clip diagnostics: {e}", file=sys.stderr)

    color_config = style.get("color")
    if args.skip_color_grade:
        print("Skipping color grade (--skip-color-grade).", file=sys.stderr)
    elif color_config and color_config.get("grade_cdl"):
        print("Applying color grade to video clips...", file=sys.stderr)
        applied, _ = color_grade.apply_grade_or_warn(video_items, color_config)
        print(f"Color grade applied to {applied}/{len(video_items)} clips.", file=sys.stderr)

    sfx_count = sum(len(b.get("sfx", [])) for b in beat_plan["beats"])
    if sfx_count:
        print(f"Placing {sfx_count} SFX cue(s)...", file=sys.stderr)
        audio_design.build_sfx_track(media_pool, timeline, beat_plan, sound_item_by_relpath, fps, track_index=2)

    if music_bed:
        print(f"Building music bed from '{music_bed['path']}'...", file=sys.stderr)
        narration_end_s = edit_plan["total_new_duration_s"]
        total_duration_s = max(narration_end_s, max((b["end"] for b in beat_plan["beats"]), default=narration_end_s))
        audio_design.build_music_bed(
            media_pool, timeline, music_bed, sound_item_by_relpath[music_bed["path"]],
            narration_end_s, total_duration_s, fps, track_index=3,
        )

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
