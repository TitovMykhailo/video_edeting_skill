#!/usr/bin/env python3
"""Build beat_plan.json with exact, gap-free timing derived from edit_plan.json's real transcript.

Why this exists: hand-computing beat start/end times against a real transcript is exactly the
kind of arithmetic that produced real timeline gaps in this skill's own earlier demo work (see
references/editor_discipline.md's "timeline integrity is non-negotiable" framing — that demo's
beat_plan_BEFORE.json had two multi-second gaps from act-duration budgets never being
cross-checked against actual word timing). This script removes that failure mode by construction
instead of catching it after the fact: each beat's start is always the previous beat's end, the
first beat always starts at 0.0, and the last beat always ends at total_new_duration_s. There is
no arithmetic step where a gap or overlap could be introduced. validate_timeline.py is still
worth running afterward — it also checks script-word coverage (missing/duplicated text), which
this script doesn't verify — but the gap/overlap class of bug specifically can't happen here.

Beats are specified in a spec file: a JSON list of objects, each either
    {"end_word": <int>, "intent": "...", "media": {"path": ..., "src_in"?, "src_out"?, "loop"?, "zoom_rate"?, "pan_x"?, "pan_y"?}, "reasoning": "...", "sfx"?: [...]}
or
    {"end_word": <int>, "intent": "...", "generate": {"kind": "kinetic_text"|"chart", ...}, "reasoning": "..."}

media.zoom_rate/pan_x/pan_y (only apply when the beat actually goes through render_fitted_source/
render_held_image — i.e. an image beat, or a video beat whose aspect doesn't match the target —
see aspect_mismatched()): override the default gentle Ken Burns push-in (see
render_fitted_source()'s docstring). Every such beat gets zoom_rate=0.025/pan centered by
default even with no override — leave it alone for an ordinary beat, raise zoom_rate (e.g.
0.05-0.09) and set pan_x/pan_y toward the beat's actual subject for a hook or payoff beat that
should read as more charged than the beats around it, or set zoom_rate=0 to disable entirely.

"end_word" is a 0-based, EXCLUSIVE index into edit_plan.json's words_new_timeline — the beat
covers from the previous entry's end_word up to (not including) this one. The list must end with
end_word == len(words_new_timeline), or the plan doesn't cover the whole transcript and this
script refuses to write it.

For "media" beats, src_in/src_out/loop are auto-filled from the beat's own duration and the
asset's probed length (from the media library's _media_index.json) if omitted — pass them
explicitly to override.

For "generate" beats, this actually renders the clip via scripts/generate/kinetic_text.py or
chart.py at the beat's exact computed duration into --generated-dir, then references the
rendered file — so generated-text/chart timing always matches the beat instead of being guessed
separately and hoping it lines up.

generate.kind == "kinetic_text": pass through fields matching kinetic_text.py's CLI (text,
    accent_words, accent, font_size, transparent, bg, fg, bg_image, bg_blur, bg_darken).
    accent_words may be a JSON list (["GARAGE.", "TRILLION"]) or a single space-separated string
    — either is joined into the one space-separated string kinetic_text.py's --accent-words
    actually expects. bg_image is a real photo to blur+darken as the background instead of flat
    --bg color (see kinetic_text.py's build_blurred_background()) — a real image reads far less
    like placeholder content than flat color; prefer it for any hook/CTA/emphasis text card where
    a suitable image exists. Path is relative to --media-library, same convention as a "media"
    beat's path. Incompatible with transparent:true.
generate.kind == "chart": pass through fields matching chart.py's CLI (chart_type -> --type,
    data, title, transparent, bg, fg, accent). `data` must be a JSON OBJECT of label -> number,
    e.g. {"1998": 1, "Now": 100} — key order is preserved as category/x order. NOT a list of
    {"label", "value"} objects; chart.py does data.keys()/data.values() directly on what --data
    parses to.

Usage:
    python3 beat_plan_from_words.py --edit-plan out/edit_plan.json --spec beat_spec.json \
        --generated-dir out/generated --media-library <path> --out out/beat_plan.json \
        [--fps 30] [--width 1080] [--height 1920] \
        [--music-bed '{"path": "music.wav", "loop": true}']

--fps must match the fps the style profile's aspect_ratios entry will actually build at — see
why below. --width/--height must match that same aspect_ratios entry too (e.g. 1080x1920 for
9:16) and are only used for "generate" beats — kinetic_text.py/chart.py both default to their
own 16:9 resolution if these are omitted, which silently puts a landscape clip in a portrait
Shorts timeline. Omit only if every "generate" beat in the spec sets its own width/height.
"""
import argparse
import json
import os
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATE_DIR = os.path.join(THIS_DIR, "generate")


def to_frame(seconds, fps):
    """Same rounding as scripts/resolve/timeline_build.py's to_frame() — duplicated rather than
    imported because that module isn't meant to be used outside a live Resolve session. Beat
    durations here MUST be computed this same way (round each endpoint to a frame, then
    subtract) rather than by rounding the raw (end - start) duration directly: the two can
    differ by a frame (e.g. start=44.78s, end=46.06s, fps=30 → round(44.78*30)=1343,
    round(46.06*30)=1382, so build_video_track's actual beat_len_frames is 39 — but
    round((46.06-44.78)*30) = round(38.4) = 38, one frame short). That one-frame gap is exactly
    what made nearly every generated clip in this skill's first real production run come out a
    frame short of its beat, all flagged by build_video_track's own "isn't set to loop" warning
    — and for at least one non-generated clip trimmed right up against its own source duration,
    the same off-by-one made AppendToTimeline reject the whole video track outright. Rendering
    generated clips and sizing default src_out at the *exact* frame count build_video_track will
    independently compute removes the mismatch instead of leaving it to chance."""
    return round(seconds * fps)


def load_index_info(media_library):
    """Returns (durations, kinds) — both keyed by the index's relative path."""
    index_path = os.path.join(media_library, "_media_index.json")
    durations = {}
    kinds = {}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        for rel_path, entry in index.get("files", {}).items():
            kinds[rel_path] = entry.get("kind")
            probe = entry.get("probe") or {}
            if probe.get("duration_s"):
                durations[rel_path] = probe["duration_s"]
    return durations, kinds


def probe_dimensions(path):
    """Native (width, height) of any image or video file, via ffprobe. Returns None on failure —
    callers treat that as "can't tell, don't reframe" rather than guessing."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
        w, h = out.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except Exception:  # noqa: BLE001 — any probe failure just means "skip reframing"
        return None


def probe_duration_s(path):
    """Live ffprobe fallback for a clip's real duration when the media index doesn't have one
    (probe: null — the actual state of this skill's own media_index.json in real use, apparently
    from a tagging pass that ran without ffprobe on PATH). Without this, the caller used to just
    ASSUME an unknown-duration clip was exactly as long as its beat needed (src_out = src_in +
    duration_s), which is silently wrong whenever it's shorter — reproduced live: a 2.3s gif got
    treated as if it covered a 2.64s beat, the loop-needed check compared the assumed length
    against itself and always came back "long enough," and the beat rendered 0.34s short instead
    of looping to fill it. Returns None (not a guess) on failure — the caller falls back to the
    old assume-long-enough behavior only when even this can't tell."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
        return round(float(out.stdout.strip()), 3)
    except Exception:  # noqa: BLE001
        return None


def aspect_mismatched(src_w, src_h, target_w, target_h, tolerance=0.1):
    """True when a straight scale-and-crop to (target_w, target_h) would need to cut away more
    than `tolerance` of the source's shorter dimension — the point past which a crop stops being
    a minor reframe and starts cutting off the actual subject. A 9:16 target against typical
    landscape/square meme footage (the common case for this skill's own library) is always past
    this, by design — that's exactly the case that needs fitting instead of cropping."""
    if not target_w or not target_h:
        return False
    src_ar = src_w / src_h
    target_ar = target_w / target_h
    return abs(src_ar - target_ar) / target_ar > tolerance


def render_fitted_source(source_path, out_path, duration_s, fps, width, height, src_in_s=0.0, is_image=False, loop_source=False, zoom_rate=0.025, pan_x=0.5, pan_y=0.5):
    """Render `duration_s` of `source_path` into an exact width x height clip, fitting the WHOLE
    source in frame (never cropping into it) via a blurred, darkened, filled copy of the same
    source behind it — the standard "reel-ify" technique, not plain letterbox bars. Used whenever
    a source's aspect ratio doesn't reasonably match the target (see aspect_mismatched()).

    Why not a plain scale-and-crop to fill: tried it first, on this skill's own real meme library
    going into a 9:16 project. A nearly-square 736x670 source cropped to 1080x1916 pushed the
    subject's face almost entirely out of frame with a wall filling most of it; a landscape
    close-up face shot cropped the same way zoomed in so far the face became unrecognizable
    skin texture — the exact opposite of what a reaction meme needs, since the whole point is the
    face being legible. Confirmed on rendered preview frames, not just reasoned about. Fitting the
    full source in frame guarantees the subject is never cut off, at the cost of a filled border
    instead of the frame being 100% sharp source pixels — a real tradeoff, but a far smaller one.

    Encodes ProRes 422 (prores_ks), not H.264 — see encode.py's docstring for the full story:
    a JPEG-sourced image used to get muxed as yuvj420p/pc/bt470bg (an H.264-specific pixel-format
    quirk, now moot) and separately, EVERY ffmpeg-generated H.264 clip on a real project — correct
    per every data-level Resolve check (placement count, a post-save re-read, per-clip properties)
    — rendered as solid black in both Resolve's Edit-page canvas and the final render, while
    decoding perfectly cleanly in ffmpeg itself. That combination pointed at Resolve's own media
    engine (not ffmpeg) failing to decode these specific H.264 files. ProRes sidesteps the whole
    question instead of chasing more H.264 flags.

    zoom_rate/pan_x/pan_y add a slow Ken Burns push-in on top of the fit — a fractional
    growth-per-second (0.025 = the frame is ~2.5% larger per second of clip) cropped back down to
    exactly width x height every frame, panning toward (pan_x, pan_y) in [0,1]x[0,1] (0.5/0.5 =
    zoom centered in place; e.g. pan_x=0.8 drifts the crop window toward the right side of the
    frame as it zooms). Added directly in response to a dispatched critique agent's real finding
    on this skill's own first real project (see editor_discipline.md Part 24's critique-loop
    process): 5 of the agent's 16 sampled frames were near-duplicates of their neighbor because a
    held image/gif/short clip render was perfectly static — "if you pulled the captions off, you
    couldn't tell these apart." A continuous zoom means no two frames of a held beat are ever
    pixel-identical, and a stronger zoom_rate/off-center pan on a hook or payoff beat doubles as
    the "escalate the energy on the important beats" fix the same critique asked for, instead of
    every beat reading at the same flat visual weight. zoom_rate=0 reproduces the old static
    behavior exactly (the scale/crop step is skipped entirely, not just a no-op zoom=1 pass).
    Implemented as scale(eval=frame, growing with `t`) + crop back to size — not the zoompan
    filter — specifically to keep frame count exact: this codebase's to_frame()/beat-timing
    discipline (see this module's own to_frame() docstring) depends on every render landing on
    the exact requested frame count, and zoompan has a known history of off-by-some-frames /
    stutter quirks under exactly that kind of scrutiny; scale+crop never adds, drops, or freezes a
    frame since it runs once per input frame like any other filter in this chain."""
    vf = (
        f"split=2[bg][fg];"
        f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
        f"gblur=sigma=30,eq=brightness=-0.2[bgb];"
        f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
    )
    if zoom_rate:
        zoom_expr = f"1+{zoom_rate}*t"
        vf += (
            f"[flat];[flat]scale=w='iw*({zoom_expr})':h='ih*({zoom_expr})':eval=frame,"
            f"crop={width}:{height}:x='(iw-{width})*{pan_x}':y='(ih-{height})*{pan_y}'"
        )
    codec_args = ["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le"]
    if is_image:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", source_path,
            "-t", str(duration_s), "-r", str(int(fps)), "-filter_complex", vf, *codec_args, out_path,
        ]
    else:
        # -stream_loop -1 (before -i, so it's an input option) repeats the source indefinitely;
        # -t downstream still cuts the OUTPUT to exactly duration_s. Needed whenever the source
        # is shorter than the beat wants — same case build_video_track's own `loop` flag exists
        # for, just applied before Resolve ever sees the file instead of via repeated AppendToTimeline
        # placements, since this path already commits to a single pre-rendered clip per beat.
        loop_args = ["-stream_loop", "-1"] if loop_source else []
        cmd = [
            "ffmpeg", "-y", *loop_args, "-ss", str(src_in_s), "-i", source_path,
            "-t", str(duration_s), "-r", str(int(fps)), "-filter_complex", vf, *codec_args, "-an", out_path,
        ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Rendering fitted clip {source_path} -> {out_path} failed:\n{result.stderr[-2000:]}")


def render_held_image(image_path, duration_s, fps, out_path, width=None, height=None, zoom_rate=0.025, pan_x=0.5, pan_y=0.5):
    """Render a still image to a short video clip holding it for exactly duration_s.

    Why: a still image handed to Resolve's AppendToTimeline with an explicit startFrame/endFrame
    trim did not reliably end up at the requested length on a real build — the timeline showed
    a same-image clip placed far longer than requested (Resolve's own log reported ~100 extra
    frames on several image beats, all flagged as "Trimming item on V1 because it overlaps
    previous items" against the next beat, cascading into ~400 overlap warnings across the whole
    build). Root cause not confirmed (a still-image default-duration behavior in Resolve is the
    leading theory, but unverified without deeper access) — sidestepped instead of chased: an
    image beat becomes an ordinary short video clip with an unambiguous, ffprobe-verifiable frame
    count, the same tier this skill already uses for generated kinetic-text/chart clips, removing
    any Resolve-specific still-image handling from the equation entirely.

    width/height matter just as much here as for the generated-text tier: without them this used
    to just round the SOURCE IMAGE's own native pixel dimensions to even numbers, so a still
    handed to a 9:16 project came out at whatever arbitrary resolution the JPG happened to be
    instead of 1080x1920. Fixed once already with a scale-and-crop-to-fill — then found on a real
    rendered frame that the crop was cutting the actual subject's face out of frame on anything
    not already close to the target aspect. Now delegates to render_fitted_source(), which fits
    the whole image in frame instead of cropping into it — see that function's docstring."""
    if width and height:
        render_fitted_source(image_path, out_path, duration_s, fps, width, height, is_image=True, zoom_rate=zoom_rate, pan_x=pan_x, pan_y=pan_y)
        return
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path,
            "-t", str(duration_s), "-r", str(int(fps)),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le",
            out_path,
        ],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Rendering held image {image_path} -> {out_path} failed:\n{result.stderr[-2000:]}")


def render_generated(gen, out_path, duration_s, fps, width=None, height=None, media_library=None):
    # --fps must be passed through explicitly: kinetic_text.py/chart.py each round
    # (duration * their own --fps) to a frame count independently, defaulting to 30 if not told
    # otherwise. duration_s here was back-computed from a frame count at *this* script's --fps
    # (see to_frame()'s docstring) — if the two fps values ever disagreed, that exact-frame-count
    # guarantee would quietly stop holding again.
    # kinetic_text.py/chart.py both declare --fps as type=int — pass an int-formatted string
    # (str(30.0) is "30.0", which argparse's int() rejects outright) even though this script's
    # own --fps is a float to allow fractional rates like 29.97 in principle; those two
    # generators don't support fractional fps yet regardless, so truncating here doesn't lose
    # anything they could have used.
    fps_arg = str(int(fps))
    kind = gen["kind"]
    if kind == "kinetic_text":
        cmd = [
            sys.executable, os.path.join(GENERATE_DIR, "kinetic_text.py"),
            "--text", gen["text"], "--out", out_path, "--duration", str(duration_s), "--fps", fps_arg,
        ]
        if gen.get("accent_words"):
            # kinetic_text.py's --accent-words is one space-separated string (it does
            # args.accent_words.split() internally) — but "accent_words" reads as a list, and a
            # JSON list is what a spec author naturally reaches for. A list value used to be
            # handed straight to subprocess.run() as one of its argv elements, which isn't a
            # string and made subprocess.run's own list2cmdline() crash with a confusing
            # "expected str, bytes or os.PathLike object, not list" — reproduced live. Accept
            # both shapes.
            aw = gen["accent_words"]
            aw_str = " ".join(aw) if isinstance(aw, list) else aw
            cmd += ["--accent-words", aw_str, "--accent", gen.get("accent", "#E0212B")]
        if gen.get("font_size"):
            cmd += ["--font-size", str(gen["font_size"])]
        if gen.get("bg"):
            cmd += ["--bg", gen["bg"]]
        if gen.get("bg_image"):
            # Same convention as a "media" beat's path: relative to --media-library, or already
            # absolute.
            bg_image = gen["bg_image"]
            abs_bg_image = bg_image if os.path.isabs(bg_image) else os.path.join(media_library or "", bg_image)
            cmd += ["--bg-image", abs_bg_image]
            if gen.get("bg_blur") is not None:
                cmd += ["--bg-blur", str(gen["bg_blur"])]
            if gen.get("bg_darken") is not None:
                cmd += ["--bg-darken", str(gen["bg_darken"])]
        if gen.get("fg"):
            cmd += ["--fg", gen["fg"]]
    elif kind == "chart":
        cmd = [
            sys.executable, os.path.join(GENERATE_DIR, "chart.py"),
            "--fps", fps_arg,
            "--type", gen.get("chart_type", "bar"), "--data", json.dumps(gen["data"]),
            "--out", out_path, "--duration", str(duration_s),
        ]
        if gen.get("title"):
            cmd += ["--title", gen["title"]]
        if gen.get("accent"):
            cmd += ["--accent", gen["accent"]]
    else:
        raise ValueError(f"Unknown generate.kind '{kind}' — expected 'kinetic_text' or 'chart'")

    if gen.get("transparent"):
        cmd.append("--transparent")
    # Both generators default to their own hardcoded 16:9 resolution if --width/--height are
    # omitted — reproduced live on a 9:16 Shorts project: the hook/CTA kinetic_text cards came
    # out 1920x1080 with nothing here ever telling them otherwise, landscape clips silently
    # heading into a portrait timeline. --width/--height must come from the SAME aspect_ratios
    # entry --fps already does; a per-beat override (gen["width"]/gen["height"]) is still
    # honored for the rare beat that genuinely wants a different frame size.
    if gen.get("width") or width:
        cmd += ["--width", str(gen.get("width") or width)]
    if gen.get("height") or height:
        cmd += ["--height", str(gen.get("height") or height)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Generating {out_path} failed:\n{result.stderr}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--edit-plan", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--generated-dir", required=True)
    parser.add_argument("--media-library", required=True, help="used to look up probed durations for media beats")
    parser.add_argument("--out", required=True)
    parser.add_argument("--fps", type=float, default=30.0, help="must match the style profile's aspect_ratios fps used for the actual Resolve build — see the module docstring's to_frame() note")
    parser.add_argument("--width", type=int, help="frame width for generated (kinetic_text/chart) beats — must match the style profile's aspect_ratios entry, e.g. 1080 for 9:16. Omit only if every 'generate' beat sets its own width.")
    parser.add_argument("--height", type=int, help="frame height for generated beats, e.g. 1920 for 9:16 — see --width")
    parser.add_argument("--music-bed", help="JSON object for the beat_plan.json music_bed field, if any")
    args = parser.parse_args()

    with open(args.edit_plan, encoding="utf-8") as f:
        edit_plan = json.load(f)
    words = edit_plan["words_new_timeline"]
    total_duration_s = edit_plan["total_new_duration_s"]

    with open(args.spec, encoding="utf-8") as f:
        spec_list = json.load(f)

    durations, kinds = load_index_info(args.media_library)
    os.makedirs(args.generated_dir, exist_ok=True)

    beats = []
    prev_end_word = 0
    prev_end_time = 0.0
    for i, spec in enumerate(spec_list):
        end_word = spec["end_word"]
        if end_word <= prev_end_word:
            raise ValueError(f"Beat {i}: end_word {end_word} must be greater than the previous end_word {prev_end_word}")
        if end_word > len(words):
            raise ValueError(f"Beat {i}: end_word {end_word} is past the transcript's {len(words)} words")

        start_time = prev_end_time
        end_time = words[end_word]["start"] if end_word < len(words) else total_duration_s
        if end_time <= start_time:
            raise ValueError(f"Beat {i}: computed end {end_time} <= start {start_time} — check for a duplicate end_word")

        beat_text = " ".join(w["word"] for w in words[prev_end_word:end_word])
        # Frame-accurate, not round(end_time - start_time, 3) — see to_frame()'s docstring note.
        beat_frames = to_frame(end_time, args.fps) - to_frame(start_time, args.fps)
        if beat_frames <= 0:
            raise ValueError(f"Beat {i}: rounds to {beat_frames} frames at {args.fps}fps — too short to place")
        duration_s = beat_frames / args.fps

        if "generate" in spec:
            gen = spec["generate"]
            out_path = os.path.join(args.generated_dir, f"{i:03d}_{gen['kind']}.mov")
            render_generated(gen, out_path, duration_s, args.fps, width=args.width, height=args.height, media_library=args.media_library)
            media = {"path": os.path.abspath(out_path), "src_in": 0.0, "src_out": duration_s, "loop": False}
        elif "media" in spec:
            media = dict(spec["media"])
            rel_path = media["path"]

            if kinds.get(rel_path) == "image":
                # See render_held_image()'s docstring: images go through a real render instead
                # of an in-place trim, sidestepping whatever Resolve does with still durations.
                abs_image = rel_path if os.path.isabs(rel_path) else os.path.join(args.media_library, rel_path)
                out_path = os.path.join(args.generated_dir, f"{i:03d}_held_image.mov")
                render_held_image(
                    abs_image, duration_s, args.fps, out_path, width=args.width, height=args.height,
                    zoom_rate=media.get("zoom_rate", 0.025), pan_x=media.get("pan_x", 0.5), pan_y=media.get("pan_y", 0.5),
                )
                media = {"path": os.path.abspath(out_path), "src_in": 0.0, "src_out": duration_s, "loop": False}
            else:
                abs_media = rel_path if os.path.isabs(rel_path) else os.path.join(args.media_library, rel_path)
                clip_duration = durations.get(rel_path)
                if clip_duration is None:
                    clip_duration = probe_duration_s(abs_media)
                if "src_in" not in media:
                    media["src_in"] = 0.0
                if "src_out" not in media:
                    if clip_duration is not None:
                        media["src_out"] = round(min(media["src_in"] + duration_s, clip_duration), 3)
                    else:
                        media["src_out"] = round(media["src_in"] + duration_s, 3)
                if "loop" not in media:
                    # Frame-accurate (matches build_video_track's own to_frame()-based check),
                    # not a raw float compare: src_out/src_in get rounded to 3 decimals above,
                    # so e.g. a true clip length of 1.53333...s can round down to a stored 1.533
                    # — comparing that rounded value against the unrounded duration_s spuriously
                    # says the clip is shorter than the beat by a fraction of a frame, setting
                    # loop=true for a clip that actually fits exactly. Caught via a real Resolve
                    # build's "Trimming item on V1 because it overlaps" warnings tracing back to
                    # a handful of reused clips this affected.
                    clip_frames = to_frame(media["src_out"], args.fps) - to_frame(media["src_in"], args.fps)
                    media["loop"] = clip_frames < beat_frames

                # A real video/gif library clip handed straight to Resolve gets whatever "Input
                # Sizing" behavior the project/clip defaults to — undocumented and not something
                # this skill sets, and not something ffmpeg preprocessing can see or control
                # either way. Pre-reframe it ourselves, the same way image/generate beats already
                # are, whenever its native aspect doesn't reasonably match the target: fitting the
                # whole clip in frame (see render_fitted_source's docstring) instead of leaving the
                # crop/fit decision to an unknown default. Confirmed live: every clip in this
                # skill's own real meme library is landscape or square, so this fires for
                # essentially every beat on a 9:16 (Shorts) project — that's expected, not a bug.
                if args.width and args.height:
                    dims = probe_dimensions(abs_media)
                    if dims and aspect_mismatched(dims[0], dims[1], args.width, args.height):
                        out_path = os.path.join(args.generated_dir, f"{i:03d}_reframed.mov")
                        render_fitted_source(
                            abs_media, out_path, duration_s, args.fps, args.width, args.height,
                            src_in_s=media["src_in"], is_image=False, loop_source=media.get("loop", False),
                            zoom_rate=media.get("zoom_rate", 0.025), pan_x=media.get("pan_x", 0.5), pan_y=media.get("pan_y", 0.5),
                        )
                        media = {"path": os.path.abspath(out_path), "src_in": 0.0, "src_out": duration_s, "loop": False}
        else:
            raise ValueError(f"Beat {i}: needs either 'media' or 'generate'")

        beat = {
            "start": round(start_time, 3),
            "end": round(end_time, 3),
            "text": beat_text,
            "intent": spec["intent"],
            "media": media,
            "reasoning": spec.get("reasoning", ""),
        }
        if spec.get("sfx"):
            beat["sfx"] = spec["sfx"]
        beats.append(beat)

        prev_end_word = end_word
        prev_end_time = end_time

    if prev_end_word != len(words):
        raise ValueError(
            f"Spec only covers {prev_end_word}/{len(words)} words — add beats for the rest of "
            "the transcript. A partial plan would leave real narration with no visual assigned."
        )

    beat_plan = {"timing_basis": "audio_derived", "beats": beats}
    if args.music_bed:
        beat_plan["music_bed"] = json.loads(args.music_bed)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(beat_plan, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(beats)} beats covering 0.0-{prev_end_time}s to {args.out}", file=sys.stderr)
    print(
        "\nBefore treating this plan as final: run validate_timeline.py --spec against the beat "
        "spec (bare text cards / clip-reuse density / ip_risk - mechanical, catches a subset "
        "cheaply, see editor_discipline.md Part 24's docstring note), then a real critique pass "
        "against the rendered beats, named per editor_discipline.md Part 24: humor critic, text "
        "critic, beauty critic, video critic (general). A written beat_spec.json is a draft, not "
        "a finished plan.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, ValueError, KeyError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
