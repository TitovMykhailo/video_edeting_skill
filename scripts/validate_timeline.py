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

--spec mode (additive, doesn't affect exit code): pass --spec out/beat_spec.json (with --edit-plan,
to get real per-beat timing the same way beat_plan_from_words.py itself computes it) to run three
mechanical checks against the RAW SPEC before a single clip gets rendered — cheaper than catching
the same problem after a full beat_plan.json/render cycle exists (see editor_discipline.md Part
24's "fixing it there is free" framing, which this makes literal instead of just written guidance):
bare text-card beats (kind=="kinetic_text" with no bg_image — Part 8/33), the same media.path
reused within --style's media.meme_frequency_cap_s seconds of itself (falls back to 90s), and any
beat whose media.path is tagged ip_risk in --media-library's _media_index.json (Part 35 — caps
Tier C usage at one per video, never as the hook). These are printed as spec_warnings and never
flip the exit-code/status — they're judgment-adjacent findings (a real one might still be the
right call), not objective breakage the way a timeline gap is. --beat-plan is optional when --spec
is given (a beat_plan.json doesn't exist yet at this point in the workflow).
"""
import argparse
import difflib
import json
import os
import re
import sys

EPS = 1e-6
DEFAULT_MEME_FREQUENCY_CAP_S = 90.0


def compute_spec_beat_times(spec_beats, words, total_duration_s):
    """Mirrors beat_plan_from_words.py's main() start/end computation exactly (end_word is an
    exclusive index into words_new_timeline) so --spec's timing lines up with what the real build
    will use, without needing beat_plan.json to already exist."""
    times = []
    prev_end_word = 0
    prev_end_time = 0.0
    for spec in spec_beats:
        end_word = spec["end_word"]
        start_time = prev_end_time
        end_time = words[end_word]["start"] if end_word < len(words) else total_duration_s
        times.append((start_time, end_time))
        prev_end_word = end_word
        prev_end_time = end_time
    return times


def check_bare_text_cards(spec_beats):
    """editor_discipline.md's already-written rule (SKILL.md step 5, Part 8/33): more than one
    bare text-on-flat-background generated beat in the same video reads as placeholder content."""
    bare = [
        i for i, b in enumerate(spec_beats)
        if (b.get("generate") or {}).get("kind") == "kinetic_text" and not b["generate"].get("bg_image")
    ]
    warnings = []
    if len(bare) > 1:
        warnings.append(
            f"{len(bare)} bare kinetic_text beats with no bg_image (indices {bare}) - "
            "editor_discipline.md's text-card rule: more than one reads as placeholder content."
        )
    return warnings


def check_reuse_density(spec_beats, beat_times, cap_s):
    """Flags the same media.path used twice within cap_s seconds of itself — the mechanical half
    of editor_discipline.md Part 34/beat_plan_schema.md's meme-reuse guidance. Only 'media' beats
    have a reusable path; a 'generate' beat's rendered output is unique per beat by construction."""
    warnings = []
    last_seen = {}
    for i, (spec, (start_s, _)) in enumerate(zip(spec_beats, beat_times)):
        media = spec.get("media")
        if not media:
            continue
        path = media["path"]
        if path in last_seen:
            prev_i, prev_start = last_seen[path]
            gap = start_s - prev_start
            if gap < cap_s:
                warnings.append(
                    f"Beat {prev_i} and beat {i} both use '{path}', only {gap:.1f}s apart "
                    f"(cap: {cap_s}s) - editor_discipline.md Part 34."
                )
        last_seen[path] = (i, start_s)
    return warnings


def check_ip_risk(spec_beats, media_library):
    """Cross-references each 'media' beat's path against _media_index.json's ip_risk tag (see
    media_tagging_schema.md) and applies editor_discipline.md Part 35's concrete rule: at most one
    Tier C (ip_risk=studio_ip) beat per video, never as the hook (beat 0). Tier B
    (ip_risk=recognizable_individual) is surfaced too -- worth seeing -- but does NOT count toward
    that cap: Part 35 is explicit that Tier B is "an established, widely-tolerated meme-culture
    norm," a different, lower risk profile than Tier C's real Content-ID exposure. Counting both
    tiers toward the same limit was a real bug here, caught live: a real rebuild of project 1
    replaced two Tier C clips with Tier B ones specifically to get compliant, and this check still
    flagged it as still over the cap until fixed to only count studio_ip."""
    index_path = os.path.join(media_library, "_media_index.json")
    if not os.path.exists(index_path):
        return []
    with open(index_path, encoding="utf-8") as f:
        files = json.load(f).get("files", {})

    warnings = []
    flagged = []
    for i, spec in enumerate(spec_beats):
        media = spec.get("media")
        if not media:
            continue
        entry = files.get(media["path"])
        if entry and entry.get("ip_risk"):
            flagged.append((i, media["path"], entry["ip_risk"]))
    for i, path, risk in flagged:
        hook_note = " - THIS IS THE HOOK BEAT, Part 35 says never" if i == 0 else ""
        warnings.append(f"Beat {i} ('{path}') tagged ip_risk={risk}{hook_note}.")
    tier_c_count = sum(1 for _, _, risk in flagged if risk == "studio_ip")
    if tier_c_count > 1:
        warnings.append(f"{tier_c_count} studio_ip (Tier C) beats in this video - Part 35 caps this at 1.")
    return warnings


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
    parser.add_argument("--beat-plan", help="required unless only --spec checks are being run")
    parser.add_argument("--edit-plan", help="preferred source of real, audio-derived expected runtime; also required for --spec's per-beat timing")
    parser.add_argument("--expected-duration", type=float, help="manual expected runtime in seconds - only for a provisional-timing pass with no real audio yet")
    parser.add_argument("--script", help="plain-text script file, to check every line got assigned to some beat's text field and nothing got duplicated")
    parser.add_argument("--spec", help="beat_spec.json - runs pre-render structural checks (bare text cards, clip-reuse density, ip_risk) - see this module's docstring")
    parser.add_argument("--media-library", help="needed for --spec's ip_risk check, to resolve media.path against _media_index.json")
    parser.add_argument("--style", help="needed for --spec's meme_frequency_cap_s (falls back to 90s if omitted)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if not args.beat_plan and not args.spec:
        print("ERROR: pass --beat-plan, --spec, or both.", file=sys.stderr)
        sys.exit(2)

    spec_warnings = []
    if args.spec:
        with open(args.spec, encoding="utf-8") as f:
            spec_beats = json.load(f)
        spec_warnings += check_bare_text_cards(spec_beats)
        if args.media_library:
            spec_warnings += check_ip_risk(spec_beats, args.media_library)
        if args.edit_plan:
            with open(args.edit_plan, encoding="utf-8") as f:
                edit_plan = json.load(f)
            words = edit_plan["words_new_timeline"]
            total_duration_s = edit_plan["total_new_duration_s"]
            beat_times = compute_spec_beat_times(spec_beats, words, total_duration_s)
            cap_s = DEFAULT_MEME_FREQUENCY_CAP_S
            if args.style:
                with open(args.style, encoding="utf-8") as f:
                    style = json.load(f)
                cap_s = (style.get("media") or {}).get("meme_frequency_cap_s", cap_s)
            spec_warnings += check_reuse_density(spec_beats, beat_times, cap_s)

    if not args.beat_plan:
        report = {
            "status": "PASS",
            "notes": [],
            "spec_warnings": spec_warnings,
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("Timeline validation: PASS (--spec only, no --beat-plan gap/overlap checks run)", file=sys.stderr)
        for w in spec_warnings:
            print(f"  SPEC WARNING: {w}", file=sys.stderr)
        print(f"Wrote {args.out}", file=sys.stderr)
        sys.exit(0)

    beats = load_beats(args.beat_plan)

    expected_duration = None
    if args.edit_plan:
        with open(args.edit_plan, encoding="utf-8") as f:
            expected_duration = json.load(f)["total_new_duration_s"]
    elif args.expected_duration is not None:
        expected_duration = args.expected_duration

    gaps, overlaps = find_gaps_and_overlaps(beats, expected_duration)
    unassigned = round(sum(g["duration"] for g in gaps), 3)
    # max(), not beats[-1]["end"]: beats is sorted by start, and a beat that starts later doesn't
    # necessarily end later (an overlapping/nested beat breaks that assumption) — using the last
    # element by start would silently under-report the real runtime in exactly the malformed-plan
    # cases this validator exists to catch.
    actual_runtime = round(max(b["end"] for b in beats), 3) if beats else 0.0

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
        "spec_warnings": spec_warnings,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Timeline validation: {status}", file=sys.stderr)
    for n in notes:
        print(f"  - {n}", file=sys.stderr)
    for w in spec_warnings:
        print(f"  SPEC WARNING: {w}", file=sys.stderr)
    print(f"Wrote {args.out}", file=sys.stderr)

    sys.exit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
