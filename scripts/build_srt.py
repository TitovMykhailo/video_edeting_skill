#!/usr/bin/env python3
"""Chunk the post-cut word timeline into short on-screen captions.

Usage:
    python3 build_srt.py --edit-plan out/edit_plan.json --out out/captions.srt \
        --captions-json out/captions.json --style style.json

Reads `words_new_timeline` from edit_plan.json (already on the tightened,
post-cut timeline — see references/beat_plan_schema.md) and groups words into
short bursts per the style profile's caption rules, writing both a standard
.srt (for DaVinci Resolve's subtitle-track import) and a captions.json that
keeps per-word timing for beat planning / a future word-pop caption upgrade.
"""
import argparse
import json


DEFAULT_CAPTIONS = {
    "enabled": True,
    "max_words_per_chunk": 4,
    "max_chars_per_chunk": 24,
    "max_duration_s": 1.8,
    "break_on_punctuation": True,
    "case": "sentence",
}

SENTENCE_END = (".", "!", "?")


def load_caption_rules(style_path):
    rules = dict(DEFAULT_CAPTIONS)
    if style_path:
        with open(style_path, encoding="utf-8") as f:
            style = json.load(f)
        rules.update(style.get("captions", {}))
    return rules


def chunk_words(words, rules):
    chunks = []
    current = []

    def current_text_len(extra_word=None):
        ws = current + ([extra_word] if extra_word else [])
        return len(" ".join(w["word"] for w in ws))

    for w in words:
        if not current:
            current = [w]
            continue

        would_exceed_words = len(current) + 1 > rules["max_words_per_chunk"]
        would_exceed_chars = current_text_len(w) > rules["max_chars_per_chunk"]
        would_exceed_duration = (w["end"] - current[0]["start"]) > rules["max_duration_s"]

        if would_exceed_words or would_exceed_chars or would_exceed_duration:
            chunks.append(current)
            current = [w]
            continue

        current.append(w)

        prev_word_text = current[-1]["word"]
        if rules["break_on_punctuation"] and prev_word_text.endswith(SENTENCE_END):
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)

    return chunks


def apply_case(text, case):
    if case == "upper":
        return text.upper()
    return text  # "sentence" — leave as transcribed


def format_timestamp(seconds):
    ms_total = round(seconds * 1000)
    hours, rem = divmod(ms_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_srt(chunks, case):
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        text = apply_case(" ".join(w["word"] for w in chunk), case)
        start = format_timestamp(chunk[0]["start"])
        end = format_timestamp(chunk[-1]["end"])
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def build_captions_json(chunks, case):
    out = {"chunks": []}
    for chunk in chunks:
        out["chunks"].append(
            {
                "text": apply_case(" ".join(w["word"] for w in chunk), case),
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "words": [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in chunk],
            }
        )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edit-plan", required=True)
    parser.add_argument("--out", required=True, help="path to write the .srt file")
    parser.add_argument("--captions-json", required=True, help="path to write captions.json")
    parser.add_argument("--style", help="style profile JSON (uses built-in defaults if omitted)")
    args = parser.parse_args()

    with open(args.edit_plan, encoding="utf-8") as f:
        edit_plan = json.load(f)

    rules = load_caption_rules(args.style)
    words = edit_plan["words_new_timeline"]

    if not rules.get("enabled", True):
        print("captions.enabled is false in the style profile — skipping caption generation.")
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("")
        with open(args.captions_json, "w", encoding="utf-8") as f:
            json.dump({"chunks": []}, f)
        return

    chunks = chunk_words(words, rules)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_srt(chunks, rules["case"]))

    with open(args.captions_json, "w", encoding="utf-8") as f:
        json.dump(build_captions_json(chunks, rules["case"]), f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(chunks)} caption chunks from {len(words)} words.")


if __name__ == "__main__":
    main()
