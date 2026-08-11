#!/usr/bin/env python3
"""Apply one or more style-profile overlays on top of a base profile, producing a normal
style.json that every other script's `--style` flag already understands unchanged.

An overlay is a small JSON file containing only the fields that differ from the base — a format
variant (Shorts vs. long-form), a one-off episode tweak, a client-specific palette change — without
forking the whole profile. This is how the pipeline gets refined mid-project: the base profile
stays untouched and reusable, the overlay captures just the delta, and it's disposable or reusable
on its own. See references/style_profile_schema.md's "Overlays" section for the full rationale and
when to reach for an overlay instead of copying a whole new profile.

Usage:
    python3 merge_style_profile.py --base assets/style-profiles/nextcore-visual-essay.json \
        --overlay assets/style-profiles/overlays/shorts.json \
        --out out/style.merged.json

Multiple --overlay flags apply in the order given, each on top of the previous result — so
--overlay shorts.json --overlay this-episode.json lets a per-episode tweak win over the shared
Shorts overlay without duplicating either one.

Merge rule, deliberately simple and worth remembering: dicts merge key-by-key, recursively.
Everything else (lists, strings, numbers, booleans, null) is replaced outright by the overlay's
value when the key is present in the overlay — a list is never concatenated or diffed, only
swapped. If an overlay wants to "add one filler word," it needs to restate the whole list with
that word included, not just the new one.
"""
import argparse
import json
import sys


def deep_merge(base, overlay):
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, overlay_value in overlay.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], overlay_value)
            else:
                merged[key] = overlay_value
        return merged
    # anything else (list, scalar, or a dict/non-dict type mismatch) — overlay wins outright
    return overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="the base style profile to start from")
    parser.add_argument("--overlay", action="append", default=[], help="an overlay JSON file; repeat for multiple, applied in order")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.base, encoding="utf-8") as f:
        result = json.load(f)

    if not args.overlay:
        print("WARNING: no --overlay given — output is just a copy of --base.", file=sys.stderr)

    applied = []
    for overlay_path in args.overlay:
        with open(overlay_path, encoding="utf-8") as f:
            overlay = json.load(f)
        result = deep_merge(result, overlay)
        applied.append(overlay_path)

    # leave a breadcrumb in the merged file itself so it's traceable later — not read by any
    # other script, purely for a human (or Claude) re-opening this file to know where it came from
    result["_merged_from"] = {"base": args.base, "overlays": applied}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Merged {args.base} + {len(applied)} overlay(s) -> {args.out}", file=sys.stderr)
    for p in applied:
        print(f"  + {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
