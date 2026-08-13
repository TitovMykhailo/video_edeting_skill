#!/usr/bin/env python3
"""Composite one clip on top of another with ffmpeg — chroma-key (green screen), alpha, or a
screen/add blend (flashes, impacts, "explosion" overlays) — and place the result at a specific
point on a base video.

Three --mode values, because "put one video over another" means a different filter chain
depending on what makes the overlay's background disappear:

  chromakey   The overlay has a solid key color (green screen footage: reaction clips shot in
              front of a green/blue backdrop). Removes --key-color (with --key-similarity/
              --key-blend controlling edge softness) via ffmpeg's `chromakey` filter, then
              composites with `overlay`. This is the right mode for this skill's own
              "video green screen/" library clips — none of them are pre-keyed (see
              references/media_tagging_schema.md's quality_notes on those files).
  alpha       The overlay already carries a real alpha channel (this skill's own generated
              --transparent kinetic_text.py/chart.py output, qtrle-encoded .mov). No color to
              remove — just composites the existing transparency with `overlay`.
  screen      The overlay is effects footage on a BLACK background (flashes, explosions, impact
              frames, light leaks — the common shape of free VFX-overlay stock footage) with no
              real alpha and no clean key color. ffmpeg's `blend=all_mode=screen` makes black
              transparent and lets bright content punch through, which is the standard technique
              for this kind of overlay (screen blending is how it's done in every NLE). --mode add
              is available too (blend=all_mode=addition) for a hotter, more saturated result on
              the brightest content — try screen first, it's the more broadly correct default.

The overlay is scaled (--scale, relative to its own native size) and positioned (--x/--y, ffmpeg
overlay-filter expressions — default centered) within the base frame, then placed starting at
--start seconds into the base video, running for --overlay-duration seconds (default: the
overlay's own natural length, trimmed if the base doesn't have that much room left).

Output resolution/fps always matches the BASE clip — this is meant to slot into this skill's
usual pipeline, where the base is already at the project's target size (e.g. a beat clip from
beat_plan_from_words.py, or assemble_video.py's assembled output).

Usage:
    python3 overlay_clip.py --base beat_004.mov --overlay "video green screen/Patrick Bateman.mp4" \
        --mode chromakey --key-color 0x00B140 --start 1.0 --out beat_004_composited.mov

    python3 overlay_clip.py --base assembled.mp4 --overlay explosion_fx.mp4 --mode screen \
        --start 12.5 --scale 1.0 --out assembled_with_explosion.mp4

    python3 overlay_clip.py --base beat_000.mov --overlay generated/hook_text.mov --mode alpha \
        --start 0.0 --out beat_000_with_text.mov
"""
import argparse
import subprocess
import sys


def probe_duration_s(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"ffprobe couldn't read {path}: {out.stderr[-500:]}")
    return round(float(out.stdout.strip()), 3)


def probe_dimensions(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"ffprobe couldn't read dimensions of {path}: {out.stderr[-500:]}")
    w, h = out.stdout.strip().split(",")[:2]
    return int(w), int(h)


def build_filter_complex(mode, key_color, key_similarity, key_blend, scale, x_expr, y_expr, start_s,
                          base_wh=None, overlay_wh=None):
    scale_step = f"[1:v]scale=iw*{scale}:ih*{scale}[ov_scaled];" if scale != 1.0 else "[1:v]copy[ov_scaled];"

    if mode == "chromakey":
        key_step = f"[ov_scaled]chromakey={key_color}:{key_similarity}:{key_blend},format=yuva420p[ov_keyed];"
        overlay_step = f"[0:v][ov_keyed]overlay=x={x_expr}:y={y_expr}:enable='gte(t,{start_s})'[out]"
        return scale_step + key_step + overlay_step
    elif mode == "alpha":
        overlay_step = f"[0:v][ov_scaled]overlay=x={x_expr}:y={y_expr}:enable='gte(t,{start_s})'[out]"
        return scale_step + overlay_step
    elif mode in ("screen", "add"):
        blend_mode = "screen" if mode == "screen" else "addition"
        # blend (unlike overlay) needs both inputs the exact same pixel size to line up, and has
        # no x/y positioning of its own — pad the scaled overlay onto a base-sized canvas at the
        # requested position first. pad's expression variables (iw/ih/ow/oh) are NOT the same
        # ones overlay uses (W/H/w/h) — reproduced live: reusing overlay-style default expressions
        # here made ffmpeg fail immediately ("Undefined constant... in 'W'"). Compute literal
        # pixel positions in Python instead of trying to share one expression syntax across both
        # filter types.
        base_w, base_h = base_wh
        ov_w, ov_h = overlay_wh
        scaled_w, scaled_h = round(ov_w * scale), round(ov_h * scale)
        pad_x = (base_w - scaled_w) // 2 if x_expr is None else int(x_expr)
        pad_y = (base_h - scaled_h) // 2 if y_expr is None else int(y_expr)
        pad_step = f"[ov_scaled]pad={base_w}:{base_h}:{pad_x}:{pad_y}:color=black@0[ov_padded];"
        blend_step = f"[0:v][ov_padded]blend=all_mode={blend_mode}:all_opacity=1:enable='gte(t,{start_s})'[out]"
        return scale_step + pad_step + blend_step
    else:
        raise ValueError(f"Unknown mode '{mode}'")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True)
    parser.add_argument("--overlay", required=True)
    parser.add_argument("--mode", required=True, choices=["chromakey", "alpha", "screen", "add"])
    parser.add_argument("--key-color", default="0x00B140", help="chromakey only: hex color to remove, e.g. 0x00B140 for a typical green screen")
    parser.add_argument("--key-similarity", type=float, default=0.22, help="chromakey only: how close a pixel must be to --key-color to be removed (0-1)")
    parser.add_argument("--key-blend", type=float, default=0.08, help="chromakey only: edge softness (0-1)")
    parser.add_argument("--scale", type=float, default=1.0, help="overlay scale relative to its own native size")
    parser.add_argument("--x", help="position, default centered. chromakey/alpha: an ffmpeg overlay-filter expression (e.g. '(W-w)/2'). screen/add: a literal pixel integer — pad's expression variables aren't the same ones, see this module's docstring")
    parser.add_argument("--y", help="see --x")
    parser.add_argument("--start", type=float, default=0.0, help="seconds into --base where the overlay begins")
    parser.add_argument("--overlay-duration", type=float, help="trim/hold the overlay to this many seconds (default: the overlay's own natural length)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.mode in ("chromakey", "alpha") and args.x is None:
        args.x = "(W-w)/2"
    if args.mode in ("chromakey", "alpha") and args.y is None:
        args.y = "(H-h)/2"

    base_duration = probe_duration_s(args.base)
    if args.start >= base_duration:
        raise ValueError(f"--start {args.start}s is at or past the base clip's own duration ({base_duration}s).")
    # The output must never run longer than the base clip — reproduced live: a 14s overlay
    # dropped onto a 3s base with no clamp made ffmpeg's overlay/blend filter extend the WHOLE
    # output to the overlay's length (holding the base's last frame frozen for the remainder)
    # instead of stopping where the base actually ends. Clamp to whatever room is actually left.
    overlay_duration = min(args.overlay_duration or probe_duration_s(args.overlay), base_duration - args.start)

    base_wh = probe_dimensions(args.base) if args.mode in ("screen", "add") else None
    overlay_wh = probe_dimensions(args.overlay) if args.mode in ("screen", "add") else None
    filter_complex = build_filter_complex(
        args.mode, args.key_color, args.key_similarity, args.key_blend,
        args.scale, args.x, args.y, args.start,
        base_wh=base_wh, overlay_wh=overlay_wh,
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", args.base,
        "-itsoffset", str(args.start), "-t", str(overlay_duration), "-i", args.overlay,
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "0:a?",
        # -t here (on the OUTPUT, not an input) matters even though the base input is never
        # trimmed on its own — reproduced live: compositing a base probed at 3.2333s produced a
        # 98-frame/3.2667s output, one frame longer than the base's own real length, because the
        # base's container-reported duration and its actual decoded/re-encoded frame count don't
        # agree to sub-frame precision, and nothing downstream of the filter graph was clamping to
        # the shorter of the two. A one-frame overhang is exactly the class of bug this skill's own
        # to_frame() discipline exists to prevent elsewhere — matters here too, since this output
        # is meant to slot into that same frame-exact pipeline.
        "-t", str(base_duration),
        "-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le",
        "-c:a", "copy",
        args.out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"Compositing failed:\n{result.stderr[-2500:]}")
    print(f"Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
