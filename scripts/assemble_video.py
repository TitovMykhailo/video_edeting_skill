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
A beat whose source aspect already matched the target (common on a landscape 16:9 project pulling
in landscape source clips — beat_plan_from_words.py skips reframing those entirely) keeps its
original library-relative media.path instead of getting rewritten to an absolute generated path;
--media-library resolves those, the same way --sound-library already resolves sfx[]/music_bed
paths.

Does NOT apply a color grade — CDL (slope/offset/power) doesn't have an exact ffmpeg equivalent,
and shipping an approximate translation that LOOKS like the real grade but isn't would be worse
than being upfront that this step is skipped. If the style profile has a real grade_cdl, this
prints a reminder with the numbers to apply by eye (Fairlight/an NLE's basic color tools, or via
Resolve if you import the result there afterward) rather than faking it.

Captions, if --captions is passed, are burned in via ffmpeg's `subtitles` filter (libass) — a
plain, default subtitle look, not this skill's animated word-pop caption style. Good enough for a
draft; swap in a real captioning pass (Tier 2 in code_generated_frames.md, or Resolve's own
Fusion titles) for the final look.

Audio: every beat's optional sfx[] cues (beat_plan_schema.md's existing schema — at/path/gain_db)
are mixed in at their exact absolute time, plus a top-level music_bed if beat_plan.json has one
(looped and ducked under narration for the whole video — see build_music_cues()'s docstring for
why this path doesn't need the Resolve/OTIO path's narration-free "tail" span), then the whole mix
(narration + SFX + music) is two-pass loudness-normalized to -14 LUFS integrated — YouTube's own
normalization target (see references/sound_mixing_techniques.md), so the platform doesn't turn a
hotter mix down unpredictably later. No sound library yet? scripts/generate/synth_sfx.py generates
simple whoosh/impact/riser/click cues with ffmpeg's own audio synthesis — a real sourced SFX pack
will always sound better and stay genre-consistent (see sound_mixing_techniques.md's pack
discipline), this is a fallback for when one doesn't exist yet, not a replacement.

Usage:
    python3 assemble_video.py --beat-plan out/beat_plan.json \
        --narration-audio out/_narration_declicked.wav --width 1080 --height 1920 \
        --out out/assembled.mp4 [--captions out/captions.srt] [--style out/style.merged.json] \
        [--sound-library <path>] [--media-library <path>] [--fps 30]
"""
import argparse
import json
import math
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


def probe_video_codec(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    return out.stdout.strip()


def probe_fps(path):
    """Real average fps as a float — reads avg_frame_rate (a "num/den" string, e.g. "30000/1001")
    rather than r_frame_rate, since r_frame_rate can report a container-level guess that doesn't
    match the stream's actual average timing for anything already variable-frame-rate."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    raw = out.stdout.strip()
    if "/" in raw:
        num, den = raw.split("/")
        den = float(den)
        return float(num) / den if den else 0.0
    return float(raw) if raw else 0.0


def trim_segment(path, src_in, src_out, out_path, target_fps, scale_to=None):
    """Trim [src_in, src_out) from path into out_path, always producing a ProRes 422 output at a
    constant target_fps. Stream-copies only when the SOURCE is already ProRes AND already at
    target_fps (fast, frame-exact only at keyframes — but every frame is a keyframe in ProRes, so
    this is effectively exact); re-encodes otherwise, even when no scaling is needed and
    dimensions already match the target.

    Why every segment must end up the same codec AND the same constant frame rate, not just
    "close enough" on either — both reproduced live on the same real project, back to back:

    1. Codec: assemble_video.py's final concat step (`-f concat -c copy`) requires codec-uniform
       inputs to report a correct duration. This skill's own generated clips
       (beat_plan_from_words.py's kinetic_text/chart/reframed output) are always ProRes, so a
       project built entirely from those was always codec-uniform and this never surfaced. The
       first real project pulling in un-reframed real library clips directly (their source aspect
       already matched the target, so aspect_mismatched() correctly left them alone — see the
       scale_to note below) hit it immediately: those clips kept their ORIGINAL codec (e.g. h264)
       through the old stream-copy-first path, mixed with ProRes segments elsewhere in the concat
       list. The concat succeeded (exit 0, no error) but silently reported the wrong total
       duration — 245s instead of the correct ~212s.
    2. Frame rate: fixing #1 alone (forcing ProRes, but at each source's own native fps) produced
       a *correct-duration* file that still played back with burned-in captions drifting out of
       sync with the narration audio — confirmed by extracting a real frame at t=100s and finding
       the caption for t=125.7s displayed there, a 25+ second drift that grows over the video.
       Root cause: a handful of real library clips (unlike this skill's own always-30fps generated
       output) have their own native frame rate; concatenating segments at inconsistent frame
       rates makes the concatenated file's internal video timeline not correspond to true elapsed
       time, even though its total duration comes out numerically right by coincidence of total
       frame count vs. declared rate. subtitles= burns in against that (silently wrong) internal
       timeline, not against the separately-mixed (correctly-timed) audio track, so the drift is
       invisible in every check except actually reading a rendered frame's captions against the
       script — exactly why this skill insists on reading real frames instead of trusting a
       success exit code (see editor_discipline.md).

    Both problems have the same shape and the same fix: never assume a source clip already
    matches the pipeline's own conventions (codec, fps, resolution) just because this skill's own
    generated output always does — check and normalize explicitly, every time, for any clip that
    didn't come from beat_plan_from_words.py's own reframing/generation.

    scale_to=(width, height), when given, additionally scales while re-encoding — for a beat whose
    source is already the right ASPECT but not the right absolute resolution (e.g. a 480x270 clip
    in a 1920x1080 project: same 16:9, just lower-res). beat_plan_from_words.py's
    aspect_mismatched() only catches a genuine aspect mismatch (the case that needs the blur-fill
    treatment in render_fitted_source()) — same-aspect/wrong-resolution is a different, simpler
    case this script has to handle itself since nothing upstream reframes it. A plain scale is
    correct here specifically because the aspect already matches: nothing gets cropped or padded,
    unlike a real aspect mismatch."""
    duration = round(src_out - src_in, 3)

    def run(codec_args, vf=None):
        cmd = ["ffmpeg", "-y", "-ss", str(src_in), "-i", path, "-t", str(duration)]
        if vf:
            cmd += ["-vf", vf]
        cmd += [*codec_args, out_path]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    prores_args = ["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le", "-r", str(target_fps)]
    scale_vf = f"scale={scale_to[0]}:{scale_to[1]}:flags=lanczos" if scale_to else None

    if not scale_to and probe_video_codec(path) == "prores" and abs(probe_fps(path) - target_fps) < 0.01:
        result = run(["-c", "copy"])
        ok = result.returncode == 0 and os.path.exists(out_path)
        if ok:
            actual = probe_duration_s(out_path)
            ok = abs(actual - duration) < (1.0 / target_fps)
        if ok:
            return

    result = run(prores_args, vf=scale_vf)
    if result.returncode != 0:
        raise RuntimeError(f"Trimming {path} [{src_in}:{src_out}] failed:\n{result.stderr[-2000:]}")


def collect_sfx_cues(beat_plan, sound_library):
    """Every beat's optional sfx[] list -> [(absolute_time_s, abs_path, gain_db), ...]. Schema is
    beat_plan_schema.md's existing sfx[].{at, path, gain_db} — at is relative to the beat's own
    start, path is relative to --sound-library (or already absolute)."""
    cues = []
    for beat in beat_plan["beats"]:
        for sfx in beat.get("sfx", []):
            path = sfx["path"]
            abs_path = path if os.path.isabs(path) else os.path.join(sound_library, path)
            cues.append((beat["start"] + sfx.get("at", 0.0), abs_path, sfx.get("gain_db", 0.0)))
    return cues


def build_music_cues(beat_plan, sound_library, total_duration_s):
    """beat_plan's optional top-level music_bed -> [(absolute_time_s, abs_path, gain_db), ...],
    the exact same shape collect_sfx_cues() returns — deliberately, so a caller can just
    concatenate this onto that list and hand the combined list to mix_and_normalize_audio() as
    one mix, one two-pass loudness measurement, instead of a separate music mixing step (measuring
    loudness on the narration+SFX mix alone and then blending in music afterward would make the
    -14 LUFS target apply to the wrong signal).

    Mirrors scripts/resolve/build_otio.py's build_music_track() (loop a shorter clip to cover the
    span, ducked under narration) but deliberately does NOT implement that function's
    narration-free "tail" span at a louder base_gain_db: build_otio.py needs that because a
    Resolve timeline can be hand-extended past where the narration ends, but this script's
    beat_plan.json has no such concept — every beat's timing is derived directly from
    words_new_timeline (see beat_plan_from_words.py), so the video's total duration IS the
    narration's duration by construction. There is no tail case to cover here.

    Deliberately ducked for the WHOLE video rather than requiring a separate narration-end value
    this script doesn't have any other source for."""
    music_bed = beat_plan.get("music_bed")
    if not music_bed:
        return []
    path = music_bed["path"]
    abs_path = path if os.path.isabs(path) else os.path.join(sound_library, path)
    gain_db = music_bed.get("duck_gain_db", music_bed.get("gain_db", -18.0))
    if not music_bed.get("loop", True):
        return [(0.0, abs_path, gain_db)]
    clip_len_s = probe_duration_s(abs_path)
    if not clip_len_s or clip_len_s <= 0:
        raise RuntimeError(f"Could not probe a usable duration for music bed {abs_path}")
    repeats = math.ceil(total_duration_s / clip_len_s)
    return [(round(i * clip_len_s, 3), abs_path, gain_db) for i in range(repeats)]


def mix_and_normalize_audio(narration_path, sfx_cues, out_path):
    """Mix the narration with every (time, path, gain_db) SFX cue at its absolute time, then
    two-pass loudness-normalize the result to -14 LUFS integrated — YouTube's own normalization
    target (louder gets turned down to match it, quieter is left alone), so mixing to it directly
    avoids leaving level on the table without risking the platform re-normalizing a hotter mix
    down unpredictably. Two-pass (measure, then apply with the measured values) rather than
    single-pass loudnorm: single-pass estimates loudness from a short lookahead window and can
    misjudge a track with a loud transient early or late; two-pass measures the WHOLE file first.
    """
    n_sfx = len(sfx_cues)
    inputs = ["-i", narration_path]
    filter_parts = ["[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono[a0]"]
    mix_labels = ["[a0]"]
    for i, (at_s, path, gain_db) in enumerate(sfx_cues, start=1):
        inputs += ["-i", path]
        delay_ms = max(0, round(at_s * 1000))
        label = f"[a{i}]"
        gain_step = f",volume={gain_db}dB" if gain_db else ""
        filter_parts.append(
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono{gain_step},"
            f"adelay={delay_ms}:all=1{label}"
        )
        mix_labels.append(label)

    mix_filter = f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0[mixed]" if n_sfx else None
    pre_mix = ";".join(filter_parts)
    mixed_label = "[mixed]" if n_sfx else "[a0]"
    graph = f"{pre_mix};{mix_filter}" if n_sfx else pre_mix

    with tempfile.TemporaryDirectory(prefix="loudnorm_") as tmp_dir:
        premix_path = os.path.join(tmp_dir, "premix.wav")
        cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", mixed_label, premix_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Mixing narration with {n_sfx} SFX cue(s) failed:\n{result.stderr[-2000:]}")

        # Pass 1: measure.
        measure = subprocess.run(
            ["ffmpeg", "-i", premix_path, "-af",
             "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        stats_text = measure.stderr[measure.stderr.rfind("{"):measure.stderr.rfind("}") + 1]
        try:
            stats = json.loads(stats_text)
        except (ValueError, json.JSONDecodeError):
            stats = None

        if stats is None:
            # Measurement parse failed — fall back to single-pass rather than fail the whole
            # build over a cosmetic loudness step.
            print("WARNING: loudnorm measurement pass didn't parse; using single-pass normalization.", file=sys.stderr)
            norm_filter = "loudnorm=I=-14:TP=-1.5:LRA=11"
        else:
            norm_filter = (
                f"loudnorm=I=-14:TP=-1.5:LRA=11:"
                f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
                f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
                f"offset={stats['target_offset']}:linear=true"
            )

        # Pass 2: apply.
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", premix_path, "-af", norm_filter, "-ar", "48000", out_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Loudness normalization failed:\n{result.stderr[-2000:]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--beat-plan", required=True)
    parser.add_argument("--narration-audio", required=True, help="the DECLICKED narration — render_narration_audio.py's output, not the raw recording")
    parser.add_argument("--sound-library", help="root that beat_plan.json's sfx[].path entries are relative to — required if any beat has sfx")
    parser.add_argument("--media-library", help="root that a beat's media.path resolves against when it's not already absolute — beat_plan_from_words.py only rewrites a beat's path to absolute when it actually needed reframing (see aspect_mismatched()); a beat whose source aspect already matched the target keeps its original library-relative path, so this is required whenever beat_plan.json has any such beat (landscape source clips in a 16:9 project, the common case — confirmed missing produces a hard, immediate ffprobe FileNotFoundError rather than a silent wrong guess)")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--fps", type=float, default=30.0, help="every segment gets normalized to this constant frame rate before concatenation — must match the fps beat_plan_from_words.py's own generated beats were built at (its own --fps, default 30) or burned-in captions will drift out of sync against real library clips at a different native fps; see trim_segment()'s docstring")
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
            if not os.path.isabs(path):
                if not args.media_library:
                    raise RuntimeError(
                        f"Beat {i}'s media.path ('{path}') is relative but --media-library wasn't given. "
                        "This happens whenever a beat's source aspect already matched the target and "
                        "beat_plan_from_words.py left its original library-relative path untouched — "
                        "pass the same --media-library used to build beat_plan.json."
                    )
                path = os.path.join(args.media_library, path)
            dims = probe_dimensions(path)
            scale_to = None
            if dims != (args.width, args.height):
                src_ar = dims[0] / dims[1]
                target_ar = args.width / args.height
                # 0.1, not a tighter number: must match beat_plan_from_words.py's own
                # aspect_mismatched() tolerance exactly. That function already made the call that
                # anything within 10% doesn't need blur-fill reframing — using a stricter
                # tolerance here would second-guess a decision already made upstream and hard-fail
                # on beats that were deliberately, correctly left unreframed (reproduced live: a
                # 498x264 clip, 6.1% off 16:9, hard-failed under an 0.02 tolerance here despite
                # aspect_mismatched() already having accepted it).
                if abs(src_ar - target_ar) / target_ar <= 0.1:
                    # Same aspect (within rounding — e.g. 480x270 vs 1920x1080, both exactly
                    # 16:9), just the wrong absolute resolution. Not what beat_plan_from_words.py's
                    # aspect_mismatched() (tolerance 0.1) is checking, and not something that needs
                    # blur-fill/cropping — a plain scale is correct. A real aspect mismatch (beyond
                    # this much tighter 0.02 tolerance) still hard-fails below, unchanged: that
                    # indicates a beat that should have gone through render_fitted_source() and
                    # didn't, not something to silently paper over here.
                    scale_to = (args.width, args.height)
                    print(f"Beat {i}: {dims[0]}x{dims[1]} matches target aspect but not resolution — scaling to {args.width}x{args.height}", file=sys.stderr)
                else:
                    raise RuntimeError(
                        f"Beat {i} ('{path}') is {dims[0]}x{dims[1]}, not {args.width}x{args.height}. "
                        "Every beat must already be reframed to the target size before assembly — "
                        "rebuild beat_plan.json with beat_plan_from_words.py's --width/--height "
                        "rather than reframing here."
                    )
            src_in = media.get("src_in", 0.0)
            src_out = media.get("src_out", probe_duration_s(path))
            seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mov")
            trim_segment(path, src_in, src_out, seg_path, args.fps, scale_to=scale_to)
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

        sfx_cues = collect_sfx_cues(beat_plan, args.sound_library or "") if any(b.get("sfx") for b in beat_plan["beats"]) else []
        total_duration_s = beat_plan["beats"][-1]["end"]
        music_cues = build_music_cues(beat_plan, args.sound_library or "", total_duration_s) if beat_plan.get("music_bed") else []
        if (sfx_cues or music_cues) and not args.sound_library:
            raise RuntimeError(
                f"beat_plan.json has {len(sfx_cues)} sfx cue(s) and {'a music_bed' if music_cues else 'no music_bed'} "
                "but --sound-library wasn't given to resolve their paths."
            )
        final_audio_path = os.path.join(tmp_dir, "final_audio.wav")
        print(f"Mixing narration with {len(sfx_cues)} SFX cue(s) and {len(music_cues)} music cue(s), normalizing to -14 LUFS...", file=sys.stderr)
        mix_and_normalize_audio(args.narration_audio, sfx_cues + music_cues, final_audio_path)

        out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
        os.makedirs(out_dir, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", video_only_path, "-i", final_audio_path,
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
