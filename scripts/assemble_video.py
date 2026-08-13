#!/usr/bin/env python3
"""Assemble beat_plan.json's video track directly with ffmpeg — no DaVinci Resolve involved.

Why this exists: on a real project, placing multiple clips onto a Resolve video track via
AppendToTimeline with explicit recordFrame values reported success at every data-level check
this skill's Resolve scripts run (item count, per-clip properties, a post-save durability
re-read) while the placement never became real — invisible and unselectable in the Edit page,
and both a direct frame export and the final render came back solid black throughout. Importing
the same beats via OTIO instead worked (see build_project_via_otio_import.py). This script is a
further, Resolve-independent option: assemble the finished video directly with ffmpeg — the same
tool this skill already uses to pre-render every generated/reframed clip (see
beat_plan_from_words.py), so it's not a new dependency — and produce one finished file. Resolve
becomes entirely optional: import the result as a single clip for manual polish/color work if you
want one, or ship the file as-is.

Requires every beat's media to already be exactly --width x --height: beat_plan_from_words.py
guarantees this for every beat it builds (see that module's aspect_mismatched()/
render_fitted_source()). This script checks each beat's real dimensions with ffprobe and refuses
to guess/distort a mismatched one rather than silently stretching or cropping it wrong.

Does NOT apply a color grade — CDL (slope/offset/power) doesn't have an exact ffmpeg equivalent,
and shipping an approximate translation that LOOKS like the real grade but isn't would be worse
than being upfront that this step is skipped. If the style profile has a real grade_cdl, this
prints a reminder with the numbers to apply by eye (Fairlight/an NLE's basic color tools, or via
Resolve if you import the result there afterward) rather than faking it.

Captions, if --captions is passed, are burned in via ffmpeg's `subtitles` filter (libass) — a
plain, default subtitle look, not this skill's animated word-pop caption style. Good enough for a
draft; swap in a real captioning pass (Tier 2 in code_generated_frames.md, or Resolve's own
Fusion titles) for the final look.

Usage:
    python3 assemble_video.py --beat-plan out/beat_plan.json \
        --narration-audio out/_narration_declicked.wav --width 1080 --height 1920 --fps 30 \
        --out out/assembled.mp4 [--captions out/captions.srt] [--style out/style.merged.json]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile


def probe_dimensions(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"ffprobe couldn't read {path}: {out.stderr[-500:]}")
    w, h = out.stdout.strip().split(",")[:2]
    return int(w), int(h)


def probe_duration_s(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    return round(float(out.stdout.strip()), 3)


def trim_segment(path, src_in, src_out, out_path):
    """Trim [src_in, src_out) from path into out_path. Stream-copy first (fast, frame-exact only
    at keyframes); falls back to a re-encode if the copy doesn't land on the requested duration
    (common for GOP-based codecs cut mid-GOP) or fails outright."""
    duration = round(src_out - src_in, 3)

    def run(codec_args):
        cmd = ["ffmpeg", "-y", "-ss", str(src_in), "-i", path, "-t", str(duration), *codec_args, out_path]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    result = run(["-c", "copy"])
    ok = result.returncode == 0 and os.path.exists(out_path)
    if ok:
        actual = probe_duration_s(out_path)
        ok = abs(actual - duration) < (1.0 / 30)  # within one frame at a conservative 30fps
    if not ok:
        result = run(["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le"])
        if result.returncode != 0:
            raise RuntimeError(f"Trimming {path} [{src_in}:{src_out}] failed:\n{result.stderr[-2000:]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--beat-plan", required=True)
    parser.add_argument("--narration-audio", required=True, help="the DECLICKED narration — render_narration_audio.py's output, not the raw recording")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--captions", help="burn in captions.srt (plain libass style, not the animated word-pop look — see this module's docstring)")
    parser.add_argument("--style", help="style profile — only used to print a manual color-grade reminder, not applied")
    args = parser.parse_args()

    with open(args.beat_plan, encoding="utf-8") as f:
        beat_plan = json.load(f)

    if args.style:
        with open(args.style, encoding="utf-8") as f:
            style = json.load(f)
        grade = (style.get("color") or {}).get("grade_cdl")
        if grade:
            print(
                f"NOTE: this script does not apply the style profile's color grade "
                f"(slope={grade.get('slope')}, offset={grade.get('offset')}, "
                f"power={grade.get('power')}, saturation={grade.get('saturation')}) — see this "
                "module's docstring for why. Apply it by eye if it matters for this draft.",
                file=sys.stderr,
            )

    with tempfile.TemporaryDirectory(prefix="assemble_video_") as tmp_dir:
        concat_lines = []
        for i, beat in enumerate(beat_plan["beats"]):
            media = beat["media"]
            path = media["path"]
            dims = probe_dimensions(path)
            if dims != (args.width, args.height):
                raise RuntimeError(
                    f"Beat {i} ('{path}') is {dims[0]}x{dims[1]}, not {args.width}x{args.height}. "
                    "Every beat must already be reframed to the target size before assembly — "
                    "rebuild beat_plan.json with beat_plan_from_words.py's --width/--height "
                    "rather than reframing here."
                )
            src_in = media.get("src_in", 0.0)
            src_out = media.get("src_out", probe_duration_s(path))
            seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mov")
            trim_segment(path, src_in, src_out, seg_path)
            concat_lines.append(f"file '{seg_path}'")
            print(f"Beat {i}: trimmed {path} [{src_in}:{src_out}] -> {os.path.basename(seg_path)}", file=sys.stderr)

        concat_list_path = os.path.join(tmp_dir, "concat_list.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            f.write("\n".join(concat_lines))

        video_only_path = os.path.join(tmp_dir, "video_only.mov")
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", video_only_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Concatenating {len(concat_lines)} beats failed:\n{result.stderr[-2000:]}")
        print(f"Concatenated {len(concat_lines)} beats -> {probe_duration_s(video_only_path)}s", file=sys.stderr)

        vf_args = []
        if args.captions:
            # ffmpeg's subtitles filter parses its argument with its own mini-syntax where both
            # backslash and colon are special — an ordinary Windows absolute path breaks it
            # otherwise (both "C:" and every "\" need escaping).
            srt_escaped = os.path.abspath(args.captions).replace("\\", "/").replace(":", r"\:")
            vf_args = ["-vf", f"subtitles='{srt_escaped}'"]

        out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
        os.makedirs(out_dir, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", video_only_path, "-i", args.narration_audio,
            *vf_args,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            args.out,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Final mux failed:\n{result.stderr[-2000:]}")

    print(f"Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
