#!/usr/bin/env python3
"""Plan silence + filler-word cuts from a word-level transcript.

Pure arithmetic on timestamps — no audio decoding needed here, ffmpeg only
touches the actual audio later, in DaVinci Resolve. That keeps this stage
fast, dependency-free, and easy to rerun after tweaking a style profile.

Usage:
    python3 plan_cuts.py --transcript out/transcript.json --out out/edit_plan.json \
        --style style.json [--audio-duration 187.6]

Output matches edit_plan.json in references/beat_plan_schema.md.

Core idea: every kept word gets a small safety pad (style.pacing.pad_s) so a
cut never lands inside a word. Gaps between (padded) words longer than
style.pacing.pause_threshold_s are "cuttable silence" — instead of deleting
them outright (which sounds like a jump cut with no room tone) we keep a
short real slice of that same silence, style.pacing.keep_pause_s long, taken
from the source audio itself.
"""
import argparse
import json
import re
import sys


DEFAULT_PACING = {
    "pause_threshold_s": 0.35,
    "keep_pause_s": 0.12,
    "pad_s": 0.04,
    "remove_filler_words": True,
    "filler_words": ["um", "uh", "umm", "erm"],
    "max_removed_fraction_warning": 0.4,
}


def load_pacing(style_path):
    if not style_path:
        return dict(DEFAULT_PACING)
    with open(style_path, encoding="utf-8") as f:
        style = json.load(f)
    pacing = dict(DEFAULT_PACING)
    pacing.update(style.get("pacing", {}))
    return pacing


def _normalize(word):
    return re.sub(r"[^\w]", "", word, flags=re.UNICODE).lower()


def is_filler(word, filler_set):
    return _normalize(word) in filler_set


def merge_regions(regions):
    """Merge overlapping/touching (start, end, word) regions -> list of [start, end, [words]]."""
    if not regions:
        return []
    regions = sorted(regions, key=lambda r: r[0])
    merged = [[regions[0][0], regions[0][1], [regions[0][2]]]]
    for start, end, word in regions[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
            last[2].append(word)
        else:
            merged.append([start, end, [word]])
    return merged


def plan_cuts(words, pacing, duration_hint=None):
    filler_set = {_normalize(w) for w in pacing.get("filler_words", [])}
    remove_fillers = pacing.get("remove_filler_words", True)
    pad = pacing["pad_s"]
    threshold = pacing["pause_threshold_s"]
    keep_pause = min(pacing["keep_pause_s"], threshold)

    kept_words = [
        w for w in words if not (remove_fillers and is_filler(w["word"], filler_set))
    ]
    kept_words.sort(key=lambda w: w["start"])

    if not kept_words:
        raise ValueError("No words left after filler removal — check the transcript/filler list")

    source_duration = duration_hint if duration_hint is not None else kept_words[-1]["end"]

    # Step 1: padded regions per kept word, merged where they overlap.
    raw_regions = [(max(0.0, w["start"] - pad), min(source_duration, w["end"] + pad), w) for w in kept_words]
    merged = merge_regions(raw_regions)

    # Step 2: decide what to keep between merged word-regions (and at the head/tail).
    segments = []  # list of [src_start, src_end]

    def maybe_bridge(prev_end, next_start, side):
        """Return a (src_start, src_end) slice to keep between prev_end and next_start, or None
        if the whole gap should just be kept (it's short) — signalled via side='keep_all'."""
        gap = next_start - prev_end
        if gap <= 0:
            return None
        if gap <= threshold:
            return ("keep_all", prev_end, next_start)
        # long gap: keep a short slice near the "next" side, so silence-before-speech feels natural
        if side == "head":
            slice_end = next_start
            slice_start = max(prev_end, slice_end - keep_pause)
        elif side == "tail":
            slice_start = prev_end
            slice_end = min(next_start, slice_start + keep_pause)
        else:  # between two words — center it
            mid = (prev_end + next_start) / 2
            slice_start = mid - keep_pause / 2
            slice_end = mid + keep_pause / 2
        return ("slice", slice_start, slice_end)

    # Head (before first word region)
    head = maybe_bridge(0.0, merged[0][0], "head")
    if head and head[0] == "slice":
        segments.append([head[1], head[2]])

    # Body
    for i, region in enumerate(merged):
        if head and head[0] == "keep_all" and i == 0:
            segments.append([0.0, region[1]])
        elif segments and segments[-1][1] >= region[0]:
            # touches/overlaps previous kept segment (e.g. short gap was kept whole) -> extend
            segments[-1][1] = max(segments[-1][1], region[1])
        else:
            segments.append([region[0], region[1]])

        if i + 1 < len(merged):
            bridge = maybe_bridge(region[1], merged[i + 1][0], "between")
            if bridge and bridge[0] == "keep_all":
                # extend the current segment up through the (short) gap; the next region will
                # touch it exactly and get merged in on the next loop iteration
                segments[-1][1] = bridge[2]
            elif bridge and bridge[0] == "slice":
                segments.append([bridge[1], bridge[2]])

    # Tail (after last word region)
    tail = maybe_bridge(merged[-1][1], source_duration, "tail")
    if tail and tail[0] == "keep_all":
        segments[-1][1] = source_duration
    elif tail and tail[0] == "slice":
        segments.append([tail[1], tail[2]])

    # Clean up: merge any accidental overlaps/touches from the loop above, drop zero-length.
    segments = [s for s in segments if s[1] - s[0] > 1e-6]
    segments.sort(key=lambda s: s[0])
    clean = []
    for s in segments:
        if clean and s[0] <= clean[-1][1] + 1e-6:
            clean[-1][1] = max(clean[-1][1], s[1])
        else:
            clean.append(list(s))
    segments = clean

    # Step 3: assign new-timeline positions, cumulative.
    keep_segments = []
    cursor = 0.0
    for src_start, src_end in segments:
        dur = src_end - src_start
        keep_segments.append(
            {
                "src_start": round(src_start, 4),
                "src_end": round(src_end, 4),
                "new_start": round(cursor, 4),
                "new_end": round(cursor + dur, 4),
            }
        )
        cursor += dur
    total_new_duration = cursor

    def old_to_new(t):
        for seg in keep_segments:
            if seg["src_start"] - 1e-6 <= t <= seg["src_end"] + 1e-6:
                return seg["new_start"] + (t - seg["src_start"])
        return None  # word fell inside a removed region — shouldn't happen for kept words

    words_new_timeline = []
    for w in kept_words:
        new_start = old_to_new(w["start"])
        new_end = old_to_new(w["end"])
        if new_start is None or new_end is None:
            continue  # defensive: skip anything we can't map rather than emit bad timing
        words_new_timeline.append({"word": w["word"], "start": round(new_start, 4), "end": round(new_end, 4)})

    removed_fraction = 0.0 if source_duration <= 0 else round(1 - (total_new_duration / source_duration), 4)

    return {
        "source_duration_s": round(source_duration, 4),
        "total_new_duration_s": round(total_new_duration, 4),
        "removed_fraction": removed_fraction,
        "keep_segments": keep_segments,
        "words_new_timeline": words_new_timeline,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--style", help="style profile JSON (uses built-in defaults if omitted)")
    parser.add_argument(
        "--audio-duration",
        type=float,
        default=None,
        help="override total source duration in seconds (defaults to the transcript's own duration_s)",
    )
    args = parser.parse_args()

    with open(args.transcript, encoding="utf-8") as f:
        transcript = json.load(f)

    pacing = load_pacing(args.style)
    duration_hint = args.audio_duration if args.audio_duration is not None else transcript.get("duration_s")

    result = plan_cuts(transcript["words"], pacing, duration_hint)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"Kept {result['total_new_duration_s']:.1f}s of {result['source_duration_s']:.1f}s "
        f"({result['removed_fraction']*100:.1f}% removed), {len(result['words_new_timeline'])} words.",
        file=sys.stderr,
    )
    if result["removed_fraction"] > pacing["max_removed_fraction_warning"]:
        print(
            f"WARNING: removed_fraction {result['removed_fraction']} exceeds "
            f"max_removed_fraction_warning {pacing['max_removed_fraction_warning']} — "
            "pause_threshold_s in the style profile is probably too aggressive for this "
            "recording. Consider raising it and rerunning before building the timeline.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
