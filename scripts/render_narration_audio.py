#!/usr/bin/env python3
"""Render edit_plan.json's cuts into ONE continuous, declicked narration WAV via ffmpeg.

Why this exists: neither build_project.py nor build_otio.py used to do this — they placed each
of edit_plan.json's keep_segments as a separate clip directly on the Resolve/OTIO timeline, cut
straight out of the original recording with no fade at the edges. Every one of those cuts is a
hard amplitude discontinuity, and DaVinci Resolve's scripting API has no fade/crossfade control
at all (confirmed by grepping the whole shipped README.txt for "fade" — nothing). With a
few-hundred-word narration this produced *hundreds* of hard splices, which is exactly what
sounds like clicking/crackling on playback — reported from a real render, not a guess.

The fix has to happen before the audio ever reaches Resolve, in the file itself. This script
applies a very short (default 8ms) fade-in/fade-out at the edges of every kept segment — INSIDE
each segment's own existing boundaries, never overlapping into the next one — then concatenates
them back to back. That means:
    - Total duration is unchanged (fades trim into existing audio, they don't add or remove
      time), so every timestamp in beat_plan.json/captions.srt/words_new_timeline stays valid
      against the rendered file exactly as it was against the plan.
    - The result is one continuous file. build_project.py/build_otio.py place it as a SINGLE
      clip spanning 0..total_new_duration_s instead of iterating keep_segments — simpler than
      the old per-segment placement and only one Resolve/OTIO timeline item instead of hundreds.

Each segment is rendered to its own small temp file (atrim + afade), then joined with ffmpeg's
concat *demuxer* (a plain text file listing the pieces) rather than a single big
-filter_complex graph — a few hundred segments' worth of inline filtergraph text risks the OS
command-line length limit, and not every ffmpeg build actually has -filter_complex_script
(confirmed absent from a real Windows build's -h full output despite being commonly assumed
available). Many small, simple ffmpeg calls is slower but has no such ceiling.

A segment shorter than 2x the requested fade gets a proportionally shorter fade (down to 1ms)
rather than the fades overlapping each other inside a single very short segment (some kept
pause-slices are as short as ~0.12s).

Usage:
    python3 render_narration_audio.py --narration-audio narration.wav \
        --edit-plan out/edit_plan.json --out out/narration_declicked.wav [--fade-ms 8]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile


def have_ffmpeg():
    from shutil import which

    return which("ffmpeg") is not None and which("ffprobe") is not None


def probe_duration_s(path):
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(out.stdout)
    return float(data["format"]["duration"])


def render_segment(narration_audio, start, end, fade_s, out_path):
    dur = end - start
    this_fade = min(fade_s, max(0.001, dur * 0.4))
    out_start = max(0.0, dur - this_fade)
    af = (
        f"afade=t=in:st=0:d={this_fade:.6f},"
        f"afade=t=out:st={out_start:.6f}:d={this_fade:.6f}"
    )
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{start:.6f}", "-to", f"{end:.6f}", "-i", narration_audio,
            "-af", af, out_path,
        ],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed rendering segment {start}-{end}:\n{result.stderr[-2000:]}")


def render_declicked_narration(narration_audio, edit_plan, out_path, fade_ms=8.0):
    """edit_plan is the already-loaded dict (not a path). Returns (actual_duration_s, drift_s).
    Importable so build_project.py / build_otio.py can call this directly instead of shelling
    out — see the module docstring for why this step exists at all."""
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH — required to render declicked audio.")

    keep_segments = [s for s in edit_plan["keep_segments"] if s["src_end"] - s["src_start"] > 0]
    expected_duration = edit_plan["total_new_duration_s"]
    if not keep_segments:
        raise RuntimeError("edit_plan has no usable keep_segments to render.")

    fade_s = fade_ms / 1000.0
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="declick_") as tmp_dir:
        list_path = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as list_file:
            for i, seg in enumerate(keep_segments):
                piece_path = os.path.join(tmp_dir, f"seg_{i:05d}.wav")
                render_segment(narration_audio, seg["src_start"], seg["src_end"], fade_s, piece_path)
                escaped = piece_path.replace("'", "'\\''")
                list_file.write(f"file '{escaped}'\n")

        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr[-3000:]}")

    actual_duration = probe_duration_s(out_path)
    drift = abs(actual_duration - expected_duration)
    if drift > 0.05:
        print(
            f"WARNING: rendered duration drifted {drift:.3f}s from edit_plan's expected "
            f"{expected_duration}s — beat_plan.json timing may no longer line up. This shouldn't "
            "happen (fades don't change segment length); check for a codec padding/frame-size issue.",
            file=sys.stderr,
        )
    return actual_duration, drift


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--narration-audio", required=True)
    parser.add_argument("--edit-plan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fade-ms", type=float, default=8.0, help="fade in/out at each cut edge, in milliseconds (default 8)")
    args = parser.parse_args()

    with open(args.edit_plan, encoding="utf-8") as f:
        edit_plan = json.load(f)

    actual_duration, drift = render_declicked_narration(args.narration_audio, edit_plan, args.out, args.fade_ms)
    print(f"Wrote {args.out} ({actual_duration:.3f}s, drift {drift:.3f}s)", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, KeyError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
