#!/usr/bin/env python3
"""Render an arbitrary HTML/CSS/JS animation to a video clip, frame by frame, via headless
Chromium. This is the general-purpose tier of code-generated frames — anything the web's creative-
coding ecosystem can draw (p5.js, GSAP, anime.js, D3.js, Lottie/lottie-web, plain Canvas/SVG/CSS
animation) becomes a beat's `media` clip through this one mechanism. See
references/code_generated_frames.md and assets/generated-templates/example_scene.html for the
convention this depends on.

Usage:
    python3 render_html_motion.py --html assets/generated-templates/example_scene.html \
        --out out/generated/scene.mp4 --duration 3.0 --fps 30 --width 1920 --height 1080

The HTML file MUST define a global `window.seekTo(t)` function that deterministically draws the
scene's state at t seconds — real-time playback can't be captured frame-accurately, so every
frame is captured by explicitly seeking to a timestamp and screenshotting, not by recording
wall-clock animation. Any JS animation library can be wrapped in a few lines to expose this (a
GSAP timeline has `.seek(t)` built in; p5.js needs `noLoop()` + a manual `redraw()` call inside
`seekTo`; plain Canvas/D3 code just needs its draw function parameterized by t instead of driven
by `requestAnimationFrame`).
"""
import argparse
import os
import shutil
import sys
import tempfile

from encode import encode_frames_to_video

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "playwright is required for this tier: pip3 install playwright && playwright install chromium\n"
        "(this is an optional, heavier dependency — kinetic_text.py and chart.py cover the common "
        "cases without it)",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--html", required=True, help="path to a local HTML file implementing window.seekTo(t)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--transparent", action="store_true", help="capture with alpha (page background must be CSS-transparent) into a .mov instead of an opaque .mp4")
    parser.add_argument("--ready-timeout-ms", type=int, default=10000, help="how long to wait for window.sceneReady (if the scene defines it) before giving up")
    parser.add_argument("--frames-only", action="store_true", help="write PNG frames to a temp dir and skip ffmpeg encoding (for testing without ffmpeg installed)")
    args = parser.parse_args()

    if args.transparent and not args.out.lower().endswith(".mov"):
        parser.error("--transparent output must end in .mov")

    html_path = os.path.abspath(args.html)
    if not os.path.exists(html_path):
        print(f"ERROR: {html_path} not found.", file=sys.stderr)
        sys.exit(1)

    total_frames = max(1, round(args.duration * args.fps))
    tmp_dir = tempfile.mkdtemp(prefix="html_motion_")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": args.width, "height": args.height})
            url = f"file://{html_path}"
            if args.transparent:
                # scenes can read this to skip painting their own background fill — see the
                # convention documented in assets/generated-templates/example_scene.html
                url += "?transparent=1"
            page.goto(url)

            has_seek_to = page.evaluate("typeof window.seekTo === 'function'")
            if not has_seek_to:
                print(
                    f"ERROR: {html_path} does not define window.seekTo(t) — see "
                    "references/code_generated_frames.md for the required convention.",
                    file=sys.stderr,
                )
                browser.close()
                sys.exit(1)

            has_ready_flag = page.evaluate("typeof window.sceneReady !== 'undefined'")
            if has_ready_flag:
                try:
                    page.wait_for_function("window.sceneReady === true", timeout=args.ready_timeout_ms)
                except Exception:  # noqa: BLE001 — a timeout here shouldn't be a cryptic Playwright stack trace
                    print(
                        f"WARNING: window.sceneReady never became true within {args.ready_timeout_ms}ms — "
                        "rendering anyway, but frames may show an unloaded/incomplete scene.",
                        file=sys.stderr,
                    )

            for i in range(total_frames):
                t = i / args.fps
                page.evaluate(f"window.seekTo({t})")
                frame_path = os.path.join(tmp_dir, f"frame_{i:05d}.png")
                page.screenshot(path=frame_path, omit_background=args.transparent)

            browser.close()

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
