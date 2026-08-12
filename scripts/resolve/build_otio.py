#!/usr/bin/env python3
"""Build a .otio timeline file as a free-edition alternative to build_project.py.

Why this exists: DaVinci Resolve's *external* scripting API (the one build_project.py talks to)
has been Studio-only since v19.1 (Nov 2024) — the free edition only runs scripts from its own
internal Console/Workspace menu, so an outside Python process always gets `None` back from
`scriptapp("Resolve")`, no matter how correctly RESOLVE_SCRIPT_API/RESOLVE_SCRIPT_LIB are set.
See references/resolve_scripting_api.md's "Free edition" section.

OpenTimelineIO sidesteps this entirely: it's a normal file, and Resolve has a native
File > Import Timeline > OpenTimelineIO importer that isn't gated by the scripting restriction.

What this script builds, from the same edit_plan.json / beat_plan.json build_project.py uses:
    - a Narration audio track (from edit_plan.json's keep_segments)
    - one or more B-Roll video tracks (from beat_plan.json's beats — split into extra tracks
      only if beats actually overlap; the common case is a single track)
    - one or more SFX audio tracks (from beat_plan.json's per-beat sfx[] — overlapping cues get
      their own track, same reasoning)
    - a Music Bed audio track (duck span under narration, base span for any narration-free tail)

What it deliberately does NOT do, and why:
    - No gain/ducking levels, CDL color grade, or captions are embedded in the .otio file. OTIO
      clips can technically carry arbitrary `metadata`, but there is no evidence Resolve's OTIO
      importer reads a third-party metadata block back into its own gain/CDL controls, and
      claiming it does without being able to verify against a Studio license would be a guess
      dressed up as a fact. Instead, this script writes a companion `<out>.manual_steps.md` with
      every value you'd need to punch in by hand after import — gain per clip, the CDL numbers,
      and a reminder to import captions.srt via Resolve's own File > Import menu.
    - No render. Free-edition rendering itself is NOT scripting-gated (only automation is) — use
      the Deliver page normally after the timeline is in good shape.

Usage:
    python3 build_otio.py --project-name "My Video" \
        --narration-audio project/narration.wav \
        --edit-plan project/out/edit_plan.json \
        --beat-plan project/out/beat_plan.json \
        --style project/style.json \
        --aspect 16:9 \
        --media-library /path/to/media-library \
        [--sound-library /path/to/sound-library] \
        --out project/out/timeline.otio

Then in Resolve (free or Studio): File > Import Timeline > OpenTimelineIO, pick the .otio file,
and follow project/out/timeline.otio.manual_steps.md for the rest.
"""
import argparse
import json
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/ root
import render_narration_audio  # noqa: E402

try:
    import opentimelineio as otio
except ImportError:
    print(
        "ERROR: opentimelineio is not installed. Run: pip install opentimelineio\n"
        "(It's an optional dependency — only needed for this free-edition OTIO path, not for "
        "build_project.py or the rest of the pipeline.)",
        file=sys.stderr,
    )
    sys.exit(1)


def ffprobe_duration_s(abs_path):
    """Best-effort source duration via ffprobe, for OTIO's required `available_range`.

    Falls back to a generous guess if ffprobe is missing or fails — better to overstate a
    source's available range (harmless) than understate it (which could make Resolve reject a
    clip whose trimmed source_range appears to run past what's "available")."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", abs_path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout)
        return float(data["format"]["duration"])
    except Exception:  # noqa: BLE001 — any ffprobe/parse failure just falls back below
        return None


def frame_exact_span_s(start_s, end_s, rate):
    """Round `start_s`/`end_s` to the nearest frame at `rate` INDEPENDENTLY, then return the gap
    between those two frame numbers, in seconds — not `end_s - start_s` directly.

    Why this matters: beat_plan.json's beat boundaries come straight from Whisper word
    timestamps, which essentially never land exactly on a frame boundary at the project's fps.
    Subtracting the raw seconds first (e.g. 9.94 - 6.42 = 3.52) and comparing that against a
    generated/rendered clip's real duration (e.g. exactly 3.5s, because it was rendered at an
    explicit frame count) makes a clip that's actually frame-exact for this beat look shorter
    than it — every duration TrackBuilder.append_at ultimately writes gets frame-rounded via its
    own _rt() anyway, just too late to prevent this function's caller from already deciding
    (wrongly) that the beat needs a gap or a loop repeat. Reproduced live: a beat computed this
    way as "3.52s" against a clip rendered at exactly 105 frames (3.5s at 30fps) left a real
    1-frame gap in the resulting .otio file between that beat and the next one, invisible to
    validate_timeline.py because it only checks beat_plan.json's own claimed seconds, not the
    OTIO file this function's caller actually produces. Rounding each boundary to its own frame
    first (193 and 298) and taking the frame difference (105 -> 3.5s exactly) matches what
    timeline_build.py's build_video_track already does for the Studio path, and matches what
    TrackBuilder._rt will round each placed clip to regardless — so comparisons made against
    this value stay consistent with what actually lands in the file."""
    return (round(end_s * rate) - round(start_s * rate)) / rate


class TrackBuilder:
    """Appends clips/gaps to an OTIO Track at explicit absolute start times.

    OTIO tracks are strictly sequential (each child starts exactly where the previous one
    ended) — there's no direct "place at this timestamp" call. This keeps a running cursor and
    inserts an explicit Gap whenever the next item's start is later than the cursor, so the
    track ends up positioned correctly without ever emitting an overlap (which OTIO doesn't
    allow within a single track).
    """

    def __init__(self, name, kind, rate):
        self.track = otio.schema.Track(name=name, kind=kind)
        self.rate = rate
        self.cursor_s = 0.0

    def _rt(self, seconds):
        return otio.opentime.RationalTime(round(seconds * self.rate), self.rate)

    def append_at(self, start_s, duration_s, media_ref, source_in_s, clip_name):
        if duration_s <= 0:
            return
        if start_s < self.cursor_s - 1e-6:
            raise ValueError(
                f"'{clip_name}' at {start_s}s overlaps the previous item on track "
                f"'{self.track.name}' (cursor is at {self.cursor_s}s). This track needs lane-"
                "packing — see pack_into_tracks()."
            )
        if start_s > self.cursor_s + 1e-6:
            gap_len = start_s - self.cursor_s
            self.track.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(
                start_time=self._rt(0), duration=self._rt(gap_len),
            )))
        clip = otio.schema.Clip(
            name=clip_name,
            media_reference=media_ref,
            source_range=otio.opentime.TimeRange(
                start_time=self._rt(source_in_s), duration=self._rt(duration_s),
            ),
        )
        self.track.append(clip)
        self.cursor_s = start_s + duration_s


def pack_into_tracks(items):
    """Greedy interval packing: assign each (start_s, end_s, ...) item to the first lane whose
    last item already ends by this item's start, opening a new lane otherwise. Same idea as
    classic "minimum meeting rooms" scheduling. Returns a list of lanes, each a list of items in
    that lane, in start order."""
    lanes_end = []  # end_s of the last item placed in each lane
    lanes_items = []
    for item in sorted(items, key=lambda i: i["start_s"]):
        placed = False
        for i, end_s in enumerate(lanes_end):
            if item["start_s"] >= end_s - 1e-6:
                lanes_items[i].append(item)
                lanes_end[i] = item["end_s"]
                placed = True
                break
        if not placed:
            lanes_items.append([item])
            lanes_end.append(item["end_s"])
    return lanes_items


def external_ref(abs_path, rate, cache):
    """Build (or reuse) an ExternalReference for abs_path. Cached per abs_path so a clip reused
    across many beats (a repeated meme, a looped SFX) only pays the ffprobe cost once — each
    call still returns a *fresh* ExternalReference object, since OTIO expects each Clip to own
    its own media_reference rather than sharing one instance across clips."""
    duration_s = cache.get(abs_path)
    if duration_s is None:
        duration_s = ffprobe_duration_s(abs_path) or 3600.0  # generous fallback, see ffprobe_duration_s
        cache[abs_path] = duration_s
    url = "file:///" + os.path.abspath(abs_path).replace("\\", "/")
    return otio.schema.ExternalReference(
        target_url=url,
        available_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, rate),
            duration=otio.opentime.RationalTime(round(duration_s * rate), rate),
        ),
    )


def resolve_media_path(path, library):
    if os.path.isabs(path) and os.path.exists(path):
        return path
    candidate = os.path.join(library, path)
    if os.path.exists(candidate):
        return candidate
    raise FileNotFoundError(f"Could not resolve media path '{path}' under library '{library}'")


def build_narration_track(edit_plan, declicked_abs, rate, duration_cache):
    """Places the single already-declicked narration file (see
    scripts/render_narration_audio.py) as one clip, rather than one clip per keep_segment cut
    straight out of the original recording — the OTIO/Resolve import path has no fade/crossfade
    control either (same as the scripting API — this isn't Resolve-specific, OTIO itself has no
    fade concept beyond a Transition object crossing two clips, which doesn't apply to a single
    continuous track's internal cuts), so un-declicked segments would click here exactly the way
    they did going through build_project.py before that was fixed."""
    builder = TrackBuilder("Narration", otio.schema.TrackKind.Audio, rate)
    total_duration_s = edit_plan["total_new_duration_s"]
    builder.append_at(0.0, total_duration_s, external_ref(declicked_abs, rate, duration_cache), 0.0, "narration")
    return builder.track


def build_broll_tracks(beat_plan, media_library, rate, duration_cache):
    import math

    items = []
    notes = []
    for beat in beat_plan["beats"]:
        media = beat["media"]
        abs_path = resolve_media_path(media["path"], media_library)
        beat_start_s, beat_end_s = beat["start"], beat["end"]
        # Anchor every item's placement to FRAME NUMBERS derived independently from each
        # boundary, the same way timeline_build.py's build_video_track does for the Studio path
        # — not to beat_start_s + a computed duration. beat_plan_from_words.py guarantees each
        # beat's start equals the previous beat's end AS THE SAME JSON FLOAT, so rounding each
        # boundary to its own frame independently is guaranteed to produce matching frame numbers
        # at a shared boundary; deriving an item's end from start-plus-duration instead doesn't
        # have that guarantee once the duration itself gets frame-rounded, and drifts. Reproduced
        # live: computing end_s as beat_start_s + frame-rounded-duration left consecutive beats
        # off by a fraction of a frame, which pack_into_tracks then read as a genuine overlap and
        # bumped the later beat to a whole new lane — worse than the 1-frame gap it was meant to
        # fix. Anchoring both ends to independently-rounded frame numbers avoids both failure
        # modes at once.
        beat_start_frame = round(beat_start_s * rate)
        beat_end_frame = round(beat_end_s * rate)
        beat_len_frames = beat_end_frame - beat_start_frame
        clip_len_frames = round(media["src_out"] * rate) - round(media["src_in"] * rate)
        if beat_len_frames <= 0 or clip_len_frames <= 0:
            continue

        if media.get("loop") and clip_len_frames < beat_len_frames:
            repeats = math.ceil(beat_len_frames / clip_len_frames)
            for i in range(repeats):
                remaining = beat_len_frames - i * clip_len_frames
                this_len_frames = min(clip_len_frames, remaining)
                start_frame = beat_start_frame + i * clip_len_frames
                items.append({
                    "start_s": start_frame / rate, "end_s": (start_frame + this_len_frames) / rate,
                    "abs_path": abs_path, "source_in_s": media["src_in"], "duration_s": this_len_frames / rate,
                    "name": os.path.basename(media["path"]),
                })
        else:
            if clip_len_frames < beat_len_frames:
                notes.append(
                    f"- Beat at {beat_start_s}s uses `{media['path']}` ({clip_len_frames / rate:.2f}s) which "
                    f"is shorter than the beat ({beat_len_frames / rate:.2f}s) and isn't set to loop — there "
                    "will be a gap on the B-Roll track for the remainder. Set `\"loop\": true`, trim the "
                    "beat, or pick a longer clip."
                )
            this_len_frames = min(clip_len_frames, beat_len_frames)
            items.append({
                "start_s": beat_start_frame / rate, "end_s": (beat_start_frame + this_len_frames) / rate,
                "abs_path": abs_path, "source_in_s": media["src_in"], "duration_s": this_len_frames / rate,
                "name": os.path.basename(media["path"]),
            })

    lanes = pack_into_tracks(items)
    tracks = []
    for i, lane in enumerate(lanes):
        name = "B-Roll and Memes" if len(lanes) == 1 else f"B-Roll and Memes {i + 1}"
        builder = TrackBuilder(name, otio.schema.TrackKind.Video, rate)
        for item in lane:
            builder.append_at(
                item["start_s"], item["duration_s"],
                external_ref(item["abs_path"], rate, duration_cache), item["source_in_s"], item["name"],
            )
        tracks.append(builder.track)
    return tracks, notes


def build_sfx_tracks(beat_plan, sound_library, rate, duration_cache):
    items = []
    gain_notes = []
    for beat in beat_plan["beats"]:
        for sfx in beat.get("sfx", []):
            abs_path = resolve_media_path(sfx["path"], sound_library)
            if abs_path not in duration_cache:
                duration_cache[abs_path] = ffprobe_duration_s(abs_path) or 1.0
            duration_s = duration_cache[abs_path]
            start_s = beat["start"] + sfx["at"]
            items.append({
                "start_s": start_s, "end_s": start_s + duration_s,
                "abs_path": abs_path, "source_in_s": 0.0, "duration_s": duration_s,
                "name": os.path.basename(sfx["path"]),
            })
            if sfx.get("gain_db"):
                gain_notes.append(f"- SFX `{os.path.basename(sfx['path'])}` at {start_s:.2f}s: {sfx['gain_db']} dB")

    lanes = pack_into_tracks(items)
    tracks = []
    for i, lane in enumerate(lanes):
        name = "SFX" if len(lanes) == 1 else f"SFX {i + 1}"
        builder = TrackBuilder(name, otio.schema.TrackKind.Audio, rate)
        for item in lane:
            builder.append_at(
                item["start_s"], item["duration_s"],
                external_ref(item["abs_path"], rate, duration_cache), item["source_in_s"], item["name"],
            )
        tracks.append(builder.track)
    return tracks, gain_notes


def build_music_track(music_bed, sound_library, narration_end_s, total_duration_s, rate, duration_cache):
    import math

    abs_path = resolve_media_path(music_bed["path"], sound_library)
    if abs_path not in duration_cache:
        duration_cache[abs_path] = ffprobe_duration_s(abs_path) or 30.0
    clip_len_s = duration_cache[abs_path]
    builder = TrackBuilder("Music Bed", otio.schema.TrackKind.Audio, rate)
    gain_notes = []

    def place_span(span_start_s, span_end_s, gain_db, label):
        span_len_s = frame_exact_span_s(span_start_s, span_end_s, rate)
        if span_len_s <= 0:
            return
        gain_notes.append(f"- Music bed, {label} span ({span_start_s:.2f}s-{span_end_s:.2f}s): {gain_db} dB")
        if not music_bed.get("loop", True):
            this_len = min(clip_len_s, span_len_s)
            builder.append_at(span_start_s, this_len, external_ref(abs_path, rate, duration_cache), 0.0, f"music ({label})")
        else:
            repeats = math.ceil(span_len_s / clip_len_s)
            for i in range(repeats):
                remaining = span_len_s - i * clip_len_s
                this_len = min(clip_len_s, remaining)
                builder.append_at(span_start_s + i * clip_len_s, this_len, external_ref(abs_path, rate, duration_cache), 0.0, f"music ({label})")

    duck_gain = music_bed.get("duck_gain_db", -18.0)
    base_gain = music_bed.get("base_gain_db", -12.0)
    narration_end_s = min(narration_end_s, total_duration_s)
    place_span(0.0, narration_end_s, duck_gain, "under narration")
    if total_duration_s > narration_end_s:
        place_span(narration_end_s, total_duration_s, base_gain, "tail")

    return builder.track, gain_notes


def write_manual_steps(out_path, style, args, broll_notes, sfx_gain_notes, music_gain_notes):
    color_config = style.get("color") or {}
    cdl = color_config.get("grade_cdl")
    lines = [
        f"# Manual steps after importing {os.path.basename(out_path)}",
        "",
        "This project is on the free edition of DaVinci Resolve, where the external scripting API "
        "is Studio-only (see references/resolve_scripting_api.md). The .otio file carries clip "
        "placement and trims; everything below needs a few minutes by hand after import.",
        "",
        "## 1. Import the timeline",
        f"File > Import Timeline > OpenTimelineIO... and pick `{out_path}`.",
        "",
        "## 2. Import captions",
        f"File > Import > Subtitle... and pick the project's captions.srt "
        "(the exact menu wording varies a bit by Resolve version — look under File > Import).",
        "",
    ]

    if cdl:
        lines += [
            "## 3. Apply the color grade",
            f"Style profile: `{os.path.basename(args.style)}`. In the Color page, select the B-Roll "
            "clips and set CDL values in the primaries wheels (or via the CDL panel):",
            f"- Slope: {cdl.get('slope', [1, 1, 1])}",
            f"- Offset: {cdl.get('offset', [0, 0, 0])}",
            f"- Power: {cdl.get('power', [1, 1, 1])}",
            f"- Saturation: {cdl.get('saturation', 1.0)}",
            "",
        ]

    section_num = 4 if cdl else 3
    if sfx_gain_notes or music_gain_notes:
        lines.append(f"## {section_num}. Set clip gains in Fairlight")
        lines.append(
            "OTIO doesn't carry gain levels, so every clip lands at 0 dB on import. Set these by "
            "hand (select the clip, use the Fairlight page's gain field or the Inspector):"
        )
        lines += sfx_gain_notes
        lines += music_gain_notes
        lines.append("")
        section_num += 1

    if broll_notes:
        lines.append(f"## {section_num}. Gaps to check")
        lines.append("These beats were shorter than their clip and aren't set to loop, so they'll "
                      "leave a gap on the B-Roll track — fill or trim as needed:")
        lines += broll_notes
        lines.append("")

    notes_path = out_path + ".manual_steps.md"
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return notes_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--narration-audio", required=True)
    parser.add_argument("--edit-plan", required=True)
    parser.add_argument("--beat-plan", required=True)
    parser.add_argument("--style", required=True)
    parser.add_argument("--aspect", required=True, choices=["16:9", "9:16"])
    parser.add_argument("--media-library", required=True)
    parser.add_argument("--sound-library", help="defaults to --media-library")
    parser.add_argument("--out", required=True, help="output .otio path")
    args = parser.parse_args()

    sound_library = args.sound_library or args.media_library

    with open(args.style, encoding="utf-8") as f:
        style = json.load(f)
    with open(args.edit_plan, encoding="utf-8") as f:
        edit_plan = json.load(f)
    with open(args.beat_plan, encoding="utf-8") as f:
        beat_plan = json.load(f)

    ratios = style.get("aspect_ratios", {})
    if args.aspect not in ratios:
        raise ValueError(
            f"Aspect ratio '{args.aspect}' isn't defined in this style profile's aspect_ratios "
            f"({list(ratios)}). Add it or pick one of those."
        )
    rate = float(ratios[args.aspect]["fps"])

    narration_abs = os.path.abspath(args.narration_audio)
    declicked_abs = os.path.abspath(os.path.join(os.path.dirname(args.edit_plan), "_narration_declicked.wav"))
    print("Rendering declicked narration audio (fades each cut edge — see "
          "scripts/render_narration_audio.py)...", file=sys.stderr)
    render_narration_audio.render_declicked_narration(narration_abs, edit_plan, declicked_abs)

    timeline = otio.schema.Timeline(name=args.project_name)
    duration_cache = {}  # abs_path -> probed (or fallback) duration_s, shared across all tracks

    broll_tracks, broll_notes = build_broll_tracks(beat_plan, args.media_library, rate, duration_cache)
    for t in broll_tracks:
        timeline.tracks.append(t)

    timeline.tracks.append(build_narration_track(edit_plan, declicked_abs, rate, duration_cache))

    sfx_tracks, sfx_gain_notes = build_sfx_tracks(beat_plan, sound_library, rate, duration_cache)
    for t in sfx_tracks:
        timeline.tracks.append(t)

    music_gain_notes = []
    music_bed = beat_plan.get("music_bed")
    if music_bed:
        narration_end_s = edit_plan["total_new_duration_s"]
        total_duration_s = max(narration_end_s, max((b["end"] for b in beat_plan["beats"]), default=narration_end_s))
        music_track, music_gain_notes = build_music_track(
            music_bed, sound_library, narration_end_s, total_duration_s, rate, duration_cache,
        )
        timeline.tracks.append(music_track)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    otio.adapters.write_to_file(timeline, args.out)
    print(f"Wrote {args.out}", file=sys.stderr)

    notes_path = write_manual_steps(args.out, style, args, broll_notes, sfx_gain_notes, music_gain_notes)
    print(f"Wrote {notes_path} — read it before/after importing.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
