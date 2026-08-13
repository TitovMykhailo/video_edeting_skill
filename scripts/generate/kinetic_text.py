#!/usr/bin/env python3
"""Generate a short kinetic-typography clip from a line of text — code-drawn, no stock footage
needed. This is the zero-heavy-dependency tier for "typography frame" / "kinetic_typography" beats
(see the style profiles' shot_duration_by_intent_s) and for any bespoke visual pun that doesn't
exist as a pre-made meme clip — sometimes it's faster to draw it than to find it.

Usage:
    python3 kinetic_text.py --text "SELF EDUCATE" --out out/generated/self_educate.mov \
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
import random
import shutil
import sys
import tempfile

from encode import encode_frames_to_video

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except ImportError:
    print("Pillow is required: pip3 install Pillow", file=sys.stderr)
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("numpy is required: pip3 install numpy", file=sys.stderr)
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


def build_blurred_background(image_path, width, height, blur_radius=40, darken=0.55):
    """Scale-to-cover + gaussian-blur + darken a real image into a width x height background —
    the same "fit the frame, never show flat color" technique this skill already uses for
    aspect-mismatched clips (see beat_plan_from_words.py's render_fitted_source), applied here so
    a text card isn't just bare color. Darken (0-1, multiplies brightness) keeps white/light text
    readable against a busy photo — a blurred image at full brightness competes with the text for
    attention exactly the way editor_discipline.md's text critic warns against."""
    src = Image.open(image_path).convert("RGB")
    src_ratio = src.width / src.height
    target_ratio = width / height
    if src_ratio > target_ratio:
        new_h = height
        new_w = int(height * src_ratio)
    else:
        new_w = width
        new_h = int(width / src_ratio)
    src = src.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    src = src.crop((left, top, left + width, top + height))
    src = src.filter(ImageFilter.GaussianBlur(blur_radius))
    src = ImageEnhance.Brightness(src).enhance(darken)
    return src


def build_textured_background(width, height, base_hex, seed=None):
    """A structured dark background — a soft diagonal gradient between two close dark tones plus
    fine film grain — instead of a single flat fill color. Built once per clip (like
    build_blurred_background()), not per frame.

    Why this exists: a flat single-color card was flagged directly, on a real project, as reading
    cheap/placeholder once it's the dominant look across most of a video's beats (cinematic_
    principles.md's anti-patterns list already said the same about a flat-black hook/CTA card;
    this generalizes the fix to every kinetic_text beat, not just the highest-visibility ones).
    A textured background is the "no real photo available" fallback for a beat that still
    shouldn't look like a placeholder — reach for --bg-image instead whenever a real photo
    actually fits the beat; this is for the (common, on a fact/typography-heavy channel) case
    where nothing does.

    seed fixes the grain pattern for a given clip so re-running the same beat spec doesn't produce
    a visually-different (if imperceptibly so) background each time — matters for anything that
    diffs/compares rendered output across builds."""
    rng = random.Random(seed)
    base = _hex_to_rgb(base_hex)
    # A lighter tint of the SAME base hue, not the (red) accent color — blending toward accent
    # here made the background read as maroon/wine instead of the intended "structured dark blue,"
    # caught by actually rendering a frame rather than trusting the math. Reserve the accent color
    # for text; the background gradient should stay monochromatic within base_hex's own hue.
    hi = tuple(min(255, int(c * 1.85 + 12)) for c in base)
    # A slightly lighter corner the gradient falls away from — the same "soft off-center light
    # source" idea used for the hook/outro composites elsewhere in this project, generalized into
    # a reusable default rather than a one-off ffmpeg geq expression.
    corner_x = rng.uniform(0.15, 0.35) * width
    corner_y = rng.uniform(0.1, 0.3) * height
    max_dist = math.hypot(width, height)

    # Vectorized (numpy), not a manual per-pixel Python loop — this runs once per generated clip
    # but a 1920x1080 nested Python loop would still add real, noticeable render time across the
    # dozens of kinetic_text beats a typical video has; numpy does the same distance-field math in
    # compiled code instead of ~2M individual Python iterations.
    yy, xx = np.mgrid[0:height, 0:width]
    dist = np.hypot(xx - corner_x, yy - corner_y) / max_dist
    t = np.clip(dist * 1.15, 0.0, 1.0)[..., None]  # (H, W, 1), broadcasts over the 3 channels
    hi_arr = np.array(hi, dtype=np.float64)
    base_arr = np.array(base, dtype=np.float64)
    gradient = hi_arr + (base_arr - hi_arr) * t
    img = Image.fromarray(gradient.astype(np.uint8), mode="RGB")

    # Fine grain, not visible banding-hiding noise at full strength — subtle enough not to fight
    # the text, present enough that the background reads as textured rather than a flat gradient.
    noise = Image.effect_noise((width, height), 18).convert("L")
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    img = Image.blend(img, noise_rgb, 0.035)
    return img


def render_frame(width, height, bg, bg_image, lines, font, fg, accent, accent_words, scale, alpha, glow=True):
    if bg_image is not None:
        img = bg_image.copy()
    else:
        mode = "RGBA" if bg is None else "RGB"
        base_bg = (0, 0, 0, 0) if bg is None else bg
        img = Image.new(mode, (width, height), base_bg)

    # All text draws onto its own transparent layer, composited onto img only at the very end —
    # not straight onto img like before — so a soft glow (a blurred, dimmed copy of this exact
    # layer, composited underneath the sharp text) can be derived from whatever actually got drawn
    # without duplicating the word-layout/accent-color logic a second time. See the two draw calls
    # below (plain vs. the scaled-layer path) — both now target text_layer instead of img.
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)

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
                text_layer.paste(layer, (paste_x, paste_y), layer)
            else:
                draw.text((x, y), word, font=font, fill=color_a)
            x += w_width
        y += lh + int(font.size * 0.25)

    img = img.convert("RGBA") if img.mode != "RGBA" else img.copy()
    if glow:
        # Soft glow behind the text — a blurred, dimmed duplicate of the exact same glyphs,
        # composited underneath the sharp copy. Blur radius/opacity match a real reference
        # breakdown's spec (~15-25px blur, ~30-50% opacity) rather than an arbitrary guess.
        glow_layer = text_layer.filter(ImageFilter.GaussianBlur(20))
        glow_alpha = glow_layer.split()[3].point(lambda a: int(a * 0.4))
        glow_layer.putalpha(glow_alpha)
        img = Image.alpha_composite(img, glow_layer)
    img = Image.alpha_composite(img, text_layer)

    if bg is not None:  # opaque output requested — flatten back down from RGBA
        img = img.convert("RGB")
    return img


def generate(args):
    width, height, fps = args.width, args.height, args.fps
    bg = None if args.transparent else _hex_to_rgb(args.bg)
    bg_image = None
    if args.bg_image:
        bg_image = build_blurred_background(args.bg_image, width, height, args.bg_blur, args.bg_darken)
    elif not args.transparent and not args.flat_bg:
        # Textured (gradient + grain) by default, not a flat color fill — see
        # build_textured_background()'s docstring for why. --flat-bg opts back into the old plain
        # fill for the rare case a completely uniform color is actually wanted (e.g. matching an
        # exact brand color swatch elsewhere in the same shot). seed=args.text keeps the grain
        # pattern stable for a given clip across re-renders.
        bg_image = build_textured_background(width, height, args.bg, seed=args.text)
    fg = _hex_to_rgb(args.fg)
    accent = _hex_to_rgb(args.accent) if args.accent else None
    # Split on whitespace (not comma — "110,000" is a single word that happens to contain a
    # comma, not two words) and strip the same edge punctuation render_frame() strips off each
    # rendered word before comparing, so "--accent-words GARAGE." actually matches the rendered
    # word "GARAGE." instead of silently never matching (the two sides used to strip
    # differently: render_frame() stripped, this didn't — caught by generating a real hook
    # clip and finding the accent word rendered in the default color).
    accent_words = {w.strip(".,!?").upper() for w in args.accent_words.split()} if args.accent_words else set()

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

            frame = render_frame(width, height, bg, bg_image, lines, font, fg, accent, accent_words, scale, alpha, glow=args.glow)
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
    parser.add_argument("--bg", default="#080818", help="base background hex color — dark navy, not flat black (calibrated against a real reference breakdown). By default this is the base tone of a generated gradient+grain texture (build_textured_background()), not a flat fill — pass --flat-bg for the old plain-fill behavior. Ignored entirely if --transparent or --bg-image.")
    parser.add_argument("--no-glow", dest="glow", action="store_false", help="disable the soft glow behind text (on by default — ~20px blur, ~40% opacity, matches a real reference breakdown's spec)")
    parser.add_argument("--bg-image", help="use this image (blurred + darkened to fill the frame — see build_blurred_background()) as the background instead of the default textured one. A real photo reads even less like a placeholder than the generated texture — prefer this whenever a real photo actually fits the beat. Incompatible with --transparent.")
    parser.add_argument("--bg-blur", type=float, default=40, help="--bg-image gaussian blur radius in px")
    parser.add_argument("--bg-darken", type=float, default=0.55, help="--bg-image brightness multiplier (0-1) — keeps text readable against a busy photo")
    parser.add_argument("--flat-bg", action="store_true", help="use a plain flat --bg fill instead of the default generated gradient+grain texture — rare (e.g. matching an exact brand swatch elsewhere in the same shot); a flat card is what editor_discipline.md's anti-patterns list warns against as the default look")
    parser.add_argument("--fg", default="#FFFFFF", help="default text color, hex")
    parser.add_argument("--accent", help="accent color hex for --accent-words")
    parser.add_argument("--accent-words", help="space-separated words to render in --accent color, e.g. \"GARAGE. TRILLION\"")
    parser.add_argument("--font-path", help="path to a .ttf/.ttc font; auto-detects a system bold font if omitted")
    parser.add_argument("--font-size", type=int, default=140)
    parser.add_argument("--anim-fraction", type=float, default=0.35, help="fraction of duration spent animating in, rest is a hold")
    parser.add_argument("--transparent", action="store_true", help="render with an alpha channel (qtrle) for overlay compositing, instead of an opaque ProRes clip — both are .mov")
    parser.add_argument("--frames-only", action="store_true", help="write PNG frames to a temp dir and skip ffmpeg encoding (for testing without ffmpeg installed)")
    args = parser.parse_args()

    if not args.out.lower().endswith(".mov") and not args.frames_only:
        parser.error("--out must end in .mov (ProRes/qtrle output — see encode.py's docstring for why not .mp4)")
    if args.bg_image and args.transparent:
        parser.error("--bg-image and --transparent are incompatible — an overlay clip's whole point is having no background of its own.")

    generate(args)


if __name__ == "__main__":
    main()
