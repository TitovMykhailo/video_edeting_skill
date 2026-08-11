#!/usr/bin/env python3
"""Generate a short kinetic-typography clip from a line of text — code-drawn, no stock footage
needed. This is the zero-heavy-dependency tier for "typography frame" / "kinetic_typography" beats
(see the style profiles' shot_duration_by_intent_s) and for any bespoke visual pun that doesn't
exist as a pre-made meme clip — sometimes it's faster to draw it than to find it.

Usage:
    python3 kinetic_text.py --text "SELF EDUCATE" --out out/generated/self_educate.mp4 \
        --duration 1.4 --fps 30 --width 1920 --height 1080 \
        --bg "#0A0A0A" --fg "#FFFFFF" --accent "#E0212B" --accent-words "EDUCATE"

Pull bg/fg/accent from the project's style profile (color.accent_hex, captions.style_notes) so
generated frames match the rest of the video instead of introducing their own palette. Output
feeds back into the normal pipeline exactly like any other clip: drop it in the media library,
run scripts/index_media.py scan/write-tags on it, then reference it from beat_plan.json — see
references/code_generated_frames.md.
"""
import argparse
import math
import os
import shutil
import sys
import tempfile

from encode import encode_frames_to_video

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow is required: pip3 install Pillow", file=sys.stderr)
    sys.exit(1)


FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    # Windows
    r"C:\Windows\Fonts\arialbd.ttf",
]


def resolve_font_path(explicit_path):
    candidates = [explicit_path] if explicit_path else FONT_CANDIDATES
    for path in candidates:
        if path and os.path.exists(path):
            return path
    print(
        "WARNING: no bold system font found (checked common Linux/macOS/Windows paths). "
        "Pass --font-path explicitly for a real typeface — falling back to PIL's tiny default "
        "font, which will look wrong for a hero typography shot.",
        file=sys.stderr,
    )
    return None


def load_font(font_path, size):
    if font_path:
        return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def fit_font_and_wrap(draw, text, font_path, start_size, max_width, min_size=24):
    """Shrink the font until every wrapped line actually fits max_width — a single long word at
    too large a starting size would otherwise overflow the frame (seen while testing this script
    against a small canvas: a large default size overran a narrow test frame)."""
    size = start_size
    while size >= min_size:
        font = load_font(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if all(draw.textbbox((0, 0), line, font=font)[2] <= max_width for line in lines):
            return font, lines
        size = int(size * 0.9)
    font = load_font(font_path, min_size)
    return font, wrap_text(draw, text, font, max_width)


def ease_out_back(t, overshoot=1.4):
    """Standard overshoot-then-settle easing — the 'pop' in a pop-in reveal."""
    t = max(0.0, min(1.0, t))
    c1 = overshoot
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], []
    for word in words:
        trial = " ".join(current + [word])
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def render_frame(width, height, bg, lines, font, fg, accent, accent_words, scale, alpha):
    mode = "RGBA" if bg is None else "RGB"
    base_bg = (0, 0, 0, 0) if bg is None else bg
    img = Image.new(mode, (width, height), base_bg)
    draw = ImageDraw.Draw(img)

    line_heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    total_h = sum(line_heights) + (len(lines) - 1) * int(font.size * 0.25)
    y = (height - total_h) / 2

    for line, lh in zip(lines, line_heights):
        words = line.split()
        widths = [draw.textbbox((0, 0), w + " ", font=font)[2] for w in words]
        line_w = sum(widths) - (draw.textbbox((0, 0), " ", font=font)[2] if words else 0)
        x = (width - line_w) / 2

        for word, w_width in zip(words, widths):
            color = accent if accent and word.strip(".,!?").upper() in accent_words else fg
            color_a = color + (int(255 * alpha),) if len(color) == 3 else color

            if scale != 1.0 or alpha < 1.0:
                # Render the word onto its own layer (padded 2x so nothing clips during
                # upscaling), then paste it back centered on the word's own unscaled center —
                # not anchored to the layer's top-left corner, which would silently drift the
                # word sideways by half its own width for any scale other than exactly 1.0.
                # Also required whenever alpha < 1.0, even at scale == 1.0: Pillow's ImageDraw.text
                # silently ignores the alpha component of `fill` when drawing straight onto an RGB
                # (non-RGBA) canvas — solid glyph pixels come out fully opaque regardless of the
                # requested alpha, verified empirically. Alpha only actually blends when text is
                # drawn onto an RGBA layer and composited via paste(), as done here. (In practice
                # this file's scale and alpha formulas both reach 1.0 on the same frame, so the
                # bug was never visible — but that's a coincidence of the current easing constants,
                # not a guarantee, so both conditions are checked explicitly rather than relying on it.)
                word_bbox = draw.textbbox((0, 0), word, font=font)
                word_w, word_h = word_bbox[2] - word_bbox[0], word_bbox[3] - word_bbox[1]
                layer = Image.new("RGBA", (int(word_w * 2), int(word_h * 2)), (0, 0, 0, 0))
                ldraw = ImageDraw.Draw(layer)
                ldraw.text((word_w / 2, word_h / 2), word, font=font, fill=color_a)
                new_size = (max(1, int(layer.width * scale)), max(1, int(layer.height * scale)))
                layer = layer.resize(new_size, Image.LANCZOS)
                center_x, center_y = x + word_w / 2, y + word_h / 2
                paste_x = int(center_x - new_size[0] / 2)
                paste_y = int(center_y - new_size[1] / 2)
                img.paste(layer, (paste_x, paste_y), layer)
            else:
                draw.text((x, y), word, font=font, fill=color_a)
            x += w_width
        y += lh + int(font.size * 0.25)

    return img


def generate(args):
    width, height, fps = args.width, args.height, args.fps
    bg = None if args.transparent else _hex_to_rgb(args.bg)
    fg = _hex_to_rgb(args.fg)
    accent = _hex_to_rgb(args.accent) if args.accent else None
    accent_words = {w.upper() for w in args.accent_words.split(",")} if args.accent_words else set()

    font_path = resolve_font_path(args.font_path)
    total_frames = max(1, round(args.duration * fps))
    anim_frames = max(1, round(total_frames * args.anim_fraction))

    tmp_dir = tempfile.mkdtemp(prefix="kinetic_text_")
    try:
        probe_img = Image.new("RGB", (10, 10))
        probe_draw = ImageDraw.Draw(probe_img)
        font, lines = fit_font_and_wrap(probe_draw, args.text, font_path, args.font_size, int(width * 0.85))

        for i in range(total_frames):
            if i < anim_frames:
                t = i / max(1, anim_frames - 1) if anim_frames > 1 else 1.0
                scale = 0.6 + 0.4 * ease_out_back(t)
                alpha = min(1.0, t / 0.5)
            else:
                scale, alpha = 1.0, 1.0

            frame = render_frame(width, height, bg, lines, font, fg, accent, accent_words, scale, alpha)
            frame.save(os.path.join(tmp_dir, f"frame_{i:05d}.png"))

        if args.frames_only:
            print(f"Wrote {total_frames} frames to {tmp_dir} (--frames-only, no encode).")
            return

        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        encode_frames_to_video(tmp_dir, args.out, fps, transparent=args.transparent)
        print(f"Wrote {args.out} ({total_frames} frames @ {fps}fps).")
    finally:
        if not args.frames_only:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i : i + 2], 16) for i in (0, 2, 4))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, default=1.5)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--bg", default="#0A0A0A", help="background hex color, ignored if --transparent")
    parser.add_argument("--fg", default="#FFFFFF", help="default text color, hex")
    parser.add_argument("--accent", help="accent color hex for --accent-words")
    parser.add_argument("--accent-words", help="comma-separated words to render in --accent color")
    parser.add_argument("--font-path", help="path to a .ttf/.ttc font; auto-detects a system bold font if omitted")
    parser.add_argument("--font-size", type=int, default=140)
    parser.add_argument("--anim-fraction", type=float, default=0.35, help="fraction of duration spent animating in, rest is a hold")
    parser.add_argument("--transparent", action="store_true", help="render with alpha channel to a .mov (for overlay compositing) instead of an opaque .mp4")
    parser.add_argument("--frames-only", action="store_true", help="write PNG frames to a temp dir and skip ffmpeg encoding (for testing without ffmpeg installed)")
    args = parser.parse_args()

    if args.transparent and not args.out.lower().endswith(".mov"):
        parser.error("--transparent output must end in .mov")

    generate(args)


if __name__ == "__main__":
    main()
