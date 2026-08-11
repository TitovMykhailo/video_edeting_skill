#!/usr/bin/env python3
"""Generate an animated bar or line chart clip for a "diagram/evidence" beat — code-drawn, so it
can show the exact numbers a script mentions instead of hunting for a generic stock chart. See
the style profiles' shot_duration_by_intent_s ("diagram_evidence": ~2-5s) for how long this
should typically run.

Usage:
    python3 chart.py --type bar --data '{"Reading":10,"Doing":25,"Teaching":90}' \
        --out out/generated/retention_chart.mp4 --duration 3.0 --title "Retention by method" \
        --bg "#0A0A0A" --fg "#FFFFFF" --accent "#E0212B"

The bars/line animate in (fixed axis limits throughout, so nothing jitters or rescales frame to
frame) then hold — pass --static to skip the animation and just hold the finished chart for the
whole duration. Output feeds into the pipeline like any other clip — see
references/code_generated_frames.md.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

from encode import encode_frames_to_video

try:
    import matplotlib

    matplotlib.use("Agg")  # headless — no display/X server required
    import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib is required: pip3 install matplotlib", file=sys.stderr)
    sys.exit(1)


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def style_axes(ax, fig, bg, fg, transparent):
    if not transparent:
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(fg)
    ax.tick_params(colors=fg, labelsize=13)
    ax.yaxis.label.set_color(fg)
    ax.xaxis.label.set_color(fg)


def render_bar_frame(path, categories, amounts, t, width_in, height_in, dpi, bg, fg, accent, title, transparent):
    eased = ease_out_cubic(t)
    heights = [a * eased for a in amounts]
    max_val = max(amounts) if amounts else 1

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    style_axes(ax, fig, bg, fg, transparent)
    ax.bar(categories, heights, color=accent, width=0.6)
    ax.set_ylim(0, max_val * 1.15 if max_val > 0 else 1)
    if title:
        ax.set_title(title, color=fg, fontsize=18, fontweight="bold", pad=16)
    fig.tight_layout()
    fig.savefig(path, transparent=transparent)
    plt.close(fig)


def render_line_frame(path, x_labels, amounts, t, width_in, height_in, dpi, bg, fg, accent, title, transparent):
    n = len(amounts)
    eased = ease_out_cubic(t)
    reveal = eased * (n - 1) if n > 1 else 0
    full_idx = int(reveal)
    partial = reveal - full_idx

    xs = list(range(full_idx + 1))
    ys = amounts[: full_idx + 1]
    if full_idx + 1 < n:
        next_y = amounts[full_idx] + (amounts[full_idx + 1] - amounts[full_idx]) * partial
        xs.append(full_idx + partial)
        ys.append(next_y)

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    style_axes(ax, fig, bg, fg, transparent)
    ax.plot(xs, ys, color=accent, linewidth=4, marker="o", markersize=8, markevery=[-1] if xs else [])
    ax.set_xlim(-0.2, max(1, n - 1) + 0.2)
    y_min, y_max = min(amounts), max(amounts)
    pad = (y_max - y_min) * 0.15 or 1
    ax.set_ylim(y_min - pad, y_max + pad)
    ax.set_xticks(range(n))
    ax.set_xticklabels(x_labels, fontsize=12)
    if title:
        ax.set_title(title, color=fg, fontsize=18, fontweight="bold", pad=16)
    fig.tight_layout()
    fig.savefig(path, transparent=transparent)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--type", choices=["bar", "line"], required=True)
    parser.add_argument("--data", required=True, help='JSON object, e.g. \'{"A": 10, "B": 25}\' — key order is preserved as category/x order')
    parser.add_argument("--out", required=True)
    parser.add_argument("--title")
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--dpi", type=int, default=100)
    parser.add_argument("--bg", default="#0A0A0A")
    parser.add_argument("--fg", default="#FFFFFF")
    parser.add_argument("--accent", default="#E0212B")
    parser.add_argument("--anim-fraction", type=float, default=0.5, help="fraction of duration spent animating in, rest is a hold")
    parser.add_argument("--static", action="store_true", help="skip the animation, hold the finished chart for the whole duration")
    parser.add_argument("--transparent", action="store_true", help="render with alpha channel to a .mov (for overlay compositing) instead of an opaque .mp4")
    parser.add_argument("--frames-only", action="store_true", help="write PNG frames to a temp dir and skip ffmpeg encoding (for testing without ffmpeg installed)")
    args = parser.parse_args()

    if args.transparent and not args.out.lower().endswith(".mov"):
        parser.error("--transparent output must end in .mov")

    data = json.loads(args.data)
    labels = list(data.keys())
    amounts = list(data.values())

    width_in, height_in = args.width / args.dpi, args.height / args.dpi
    total_frames = max(1, round(args.duration * args.fps))
    anim_frames = 0 if args.static else max(1, round(total_frames * args.anim_fraction))

    tmp_dir = tempfile.mkdtemp(prefix="chart_")
    try:
        for i in range(total_frames):
            t = 1.0 if i >= anim_frames or anim_frames <= 1 else i / (anim_frames - 1)
            frame_path = os.path.join(tmp_dir, f"frame_{i:05d}.png")
            if args.type == "bar":
                render_bar_frame(frame_path, labels, amounts, t, width_in, height_in, args.dpi, args.bg, args.fg, args.accent, args.title, args.transparent)
            else:
                render_line_frame(frame_path, labels, amounts, t, width_in, height_in, args.dpi, args.bg, args.fg, args.accent, args.title, args.transparent)

        if args.frames_only:
            print(f"Wrote {total_frames} frames to {tmp_dir} (--frames-only, no encode).")
            return

        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        encode_frames_to_video(tmp_dir, args.out, args.fps, transparent=args.transparent)
        print(f"Wrote {args.out} ({total_frames} frames @ {args.fps}fps).")
    finally:
        if not args.frames_only:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
