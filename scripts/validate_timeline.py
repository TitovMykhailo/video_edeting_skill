#!/usr/bin/env python3
"""Validate that a beat_plan.json has full, non-overlapping temporal ownership of the narration —
the mechanical half of references/editor_discipline.md's "timeline integrity is non-negotiable"
rule. This is deterministic arithmetic (like plan_cuts.py), not judgment — run it before treating
any beat_plan.json as final, and again after every revision.

Usage:
    python3 validate_timeline.py --beat-plan out/beat_plan.json \
        [--edit-plan out/edit_plan.json] [--expected-duration 260.0] [--script script.txt] \
        --out out/timeline_validation.json

Runtime source, in priority order:
    1. --edit-plan's total_new_duration_s (real, audio-derived — use whenever real narration exists)
    2. --expected-duration (manual figure — for a provisional-timing pass with no audio yet;
       tag it as such in your own notes, this script has no way to know it's an estimate)
    3. omitted entirely — the report still checks internal gaps/overlaps, just can't report
       unassigned duration at the head/tail since there's nothing to compare against

Exit code is non-zero if the report's status is FAIL, so this is safe to use as a gate in a
larger script.
"""
import argparse
import difflib
import json
import re
import sys

EPS = 1e-6


def load_beats(beat_plan_path):
    with open(beat_plan_path, encoding="utf-8") as f:
        data = json.load(f)
    beats = sorted(data["beats"], key=lambda b: b["start"])
    return beats


def find_gaps_and_overlaps(beats, expected_duration=None):
    gaps = []
    overlaps = []

    if beats and beats[0]["start"] > EPS:
        gaps.append({"start": 0.0, "end": beats[0]["start"], "duration": round(beats[0]["start"], 3)})

    for prev, cur in zip(beats, beats[1:]):
        if cur["start"] > prev["end"] + EPS:
            gap_len = cur["start"] - prev["end"]
            gaps.append({"start": round(prev["end"], 3), "end": round(cur["start"], 3), "duration": round(gap_len, 3)})
        elif cur["start"] < prev["end"] - EPS:
            overlap_len = prev["end"] - cur["start"]
            overlaps.append(
                {
                    "beat_a_start": prev["start"],
                    "beat_b_start": cur["start"],
                    "overlap_s": round(overlap_len, 3),
                }
            )

    if beats and expected_duration is not None and beats[-1]["end"] < expected_duration - EPS:
        trailing = expected_duration - beats[-1]["end"]
        gaps.append({"start": round(beats[-1]["end"], 3), "end": round(expected_duration, 3), "duration": round(trailing, 3)})

    return gaps, overlaps


def normalize_words(text):
    return re.findall(r"[a-zA-Zа-яА-ЯёЁ']+", text.lower())


def check_script_coverage(beats, script_path):
    with open(script_path, encoding="utf-8") as f:
        script_words = normalize_words(f.read())

    beat_words = []
    for b in beats:
        beat_words.extend(normalize_words(b.get("text", "")))

    matcher = difflib.SequenceMatcher(None, script_words, beat_words, autojunk=False)
    missing, duplicated = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            missing.append(" ".join(script_words[i1:i2]))
        elif tag == "insert":
            duplicated.append(" ".join(beat_words[j1:j2]))
        elif tag == "replace":
            missing.append(" ".join(script_words[i1:i2]))
            duplicated.append(" ".join(beat_words[j1:j2]))

    # opcodes fragment on single-word drift constantly; only surface runs worth a human's attention
    missing = [m for m in missing if len(m.split()) >= 2]
    duplicated = [d for d in duplicated if len(d.split()) >= 2]
    return missing, duplicated


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--beat-plan", required=True)
    parser.add_argument("--edit-plan", help="preferred source of real, audio-derived expected runtime")
    parser.add_argument("--expected-duration", type=float, help="manual expected runtime in seconds — only for a provisional-timing pass with no real audio yet")
    parser.add_argument("--script", help="plain-text script file, to check every line got assigned to some beat's text field and nothing got duplicated")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    beats = load_beats(args.beat_plan)

    expected_duration = None
    if args.edit_plan:
        with open(args.edit_plan, encoding="utf-8") as f:
            expected_duration = json.load(f)["total_new_duration_s"]
    elif args.expected_duration is not None:
        expected_duration = args.expected_duration

    gaps, overlaps = find_gaps_and_overlaps(beats, expected_duration)
    unassigned = round(sum(g["duration"] for g in gaps), 3)
    actual_runtime = round(beats[-1]["end"], 3) if beats else 0.0

    missing_segments, duplicated_segments = ([], [])
    if args.script:
        missing_segments, duplicated_segments = check_script_coverage(beats, args.script)

    status = "PASS"
    notes = []
    if not beats:
        status = "FAIL"
        notes.append("beat_plan.json has no beats.")
    if gaps:
        status = "FAIL"
        notes.append(f"{len(gaps)} timeline gap(s) — see timeline_gaps. A gap is not automatically wrong (an intentional held/black frame is still a beat), but every one must be a beat you meant to write, not an accident.")
    if overlaps:
        status = "FAIL"
        notes.append(f"{len(overlaps)} unintentional overlap(s) — see unintentional_overlaps.")
    if missing_segments:
        status = "FAIL"
        notes.append(f"{len(missing_segments)} script segment(s) with no matching beat text — see missing_script_segments.")
    if duplicated_segments:
        status = "FAIL"
        notes.append(f"{len(duplicated_segments)} segment(s) appear to be covered by more than one beat — see duplicated_script_segments.")
    if expected_duration is not None and abs(actual_runtime - expected_duration) > 0.5 and not gaps:
        # gaps already explain a shorter actual_runtime; this catches the case where beats overrun
        # the expected runtime without technically overlapping each other
        status = "FAIL"
        notes.append(f"actual_runtime ({actual_runtime}s) diverges from expected_runtime ({expected_duration}s) by more than 0.5s.")

    report = {
        "status": status,
        "expected_runtime_s": expected_duration,
        "actual_runtime_s": actual_runtime,
        "unassigned_vo_duration_s": unassigned,
        "timeline_gaps": gaps,
        "unintentional_overlaps": overlaps,
        "missing_script_segments": missing_segments,
        "duplicated_script_segments": duplicated_segments,
        "notes": notes,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Timeline validation: {status}", file=sys.stderr)
    for n in notes:
        print(f"  - {n}", file=sys.stderr)
    print(f"Wrote {args.out}", file=sys.stderr)

    sys.exit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
