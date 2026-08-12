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
    {"end_word": <int>, "intent": "...", "media": {"path": ..., "src_in"?, "src_out"?, "loop"?}, "reasoning": "...", "sfx"?: [...]}
or
    {"end_word": <int>, "intent": "...", "generate": {"kind": "kinetic_text"|"chart", ...}, "reasoning": "..."}

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
    accent_words, accent, font_size, transparent, bg, fg).
generate.kind == "chart": pass through fields matching chart.py's CLI (chart_type -> --type,
    data, title, transparent, bg, fg, accent).

Usage:
    python3 beat_plan_from_words.py --edit-plan out/edit_plan.json --spec beat_spec.json \
        --generated-dir out/generated --media-library <path> --out out/beat_plan.json \
        [--fps 30] [--music-bed '{"path": "music.wav", "loop": true}']

--fps must match the fps the style profile's aspect_ratios entry will actually build at — see
why below.
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


def load_index_durations(media_library):
    index_path = os.path.join(media_library, "_media_index.json")
    durations = {}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        for rel_path, entry in index.get("files", {}).items():
            probe = entry.get("probe") or {}
            if probe.get("duration_s"):
                durations[rel_path] = probe["duration_s"]
    return durations


def render_generated(gen, out_path, duration_s, fps):
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
            cmd += ["--accent-words", gen["accent_words"], "--accent", gen.get("accent", "#E0212B")]
        if gen.get("font_size"):
            cmd += ["--font-size", str(gen["font_size"])]
        if gen.get("bg"):
            cmd += ["--bg", gen["bg"]]
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
    parser.add_argument("--music-bed", help="JSON object for the beat_plan.json music_bed field, if any")
    args = parser.parse_args()

    with open(args.edit_plan, encoding="utf-8") as f:
        edit_plan = json.load(f)
    words = edit_plan["words_new_timeline"]
    total_duration_s = edit_plan["total_new_duration_s"]

    with open(args.spec, encoding="utf-8") as f:
        spec_list = json.load(f)

    durations = load_index_durations(args.media_library)
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
            ext = ".mov" if gen.get("transparent") else ".mp4"
            out_path = os.path.join(args.generated_dir, f"{i:03d}_{gen['kind']}{ext}")
            render_generated(gen, out_path, duration_s, args.fps)
            media = {"path": os.path.abspath(out_path), "src_in": 0.0, "src_out": duration_s, "loop": False}
        elif "media" in spec:
            media = dict(spec["media"])
            rel_path = media["path"]
            clip_duration = durations.get(rel_path)
            if "src_in" not in media:
                media["src_in"] = 0.0
            if "src_out" not in media:
                if clip_duration is not None:
                    media["src_out"] = round(min(media["src_in"] + duration_s, clip_duration), 3)
                else:
                    media["src_out"] = round(media["src_in"] + duration_s, 3)
            if "loop" not in media:
                media["loop"] = (media["src_out"] - media["src_in"]) < duration_s
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


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, ValueError, KeyError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
