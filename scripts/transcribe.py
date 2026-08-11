#!/usr/bin/env python3
"""Transcribe narration audio to word-level timestamps using local faster-whisper.

Usage:
    python3 transcribe.py --audio narration.wav --out out/transcript.json \
        [--model small] [--language auto]

Output matches the transcript.json schema in references/beat_plan_schema.md.
No API key, no network access needed after the model's first download.
"""
import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, help="path to narration audio file")
    parser.add_argument("--out", required=True, help="path to write transcript.json")
    parser.add_argument(
        "--model",
        default="small",
        help="faster-whisper model size: tiny/base/small/medium/large-v3 (default: small)",
    )
    parser.add_argument(
        "--language",
        default="auto",
        help="language code (e.g. en, ru) or 'auto' to detect (default: auto)",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="'cpu', 'cuda', or 'auto' (default: auto — faster-whisper picks the best available)",
    )
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(
            "faster-whisper isn't installed. Run: pip3 install faster-whisper\n"
            "(or run scripts/check_environment.py for the full dependency report)",
            file=sys.stderr,
        )
        sys.exit(1)

    language = None if args.language == "auto" else args.language

    print(f"Loading faster-whisper model '{args.model}' (first run downloads it)...", file=sys.stderr)
    model = WhisperModel(args.model, device=args.device, compute_type="auto" if args.device == "auto" else None)

    print(f"Transcribing {args.audio} ...", file=sys.stderr)
    segments, info = model.transcribe(args.audio, language=language, word_timestamps=True)

    words = []
    for segment in segments:
        if not segment.words:
            continue
        for w in segment.words:
            words.append(
                {
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "prob": round(w.probability, 3) if w.probability is not None else None,
                }
            )

    duration = words[-1]["end"] if words else 0.0
    output = {
        "language": info.language,
        "duration_s": round(duration, 3),
        "words": words,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(words)} words ({duration:.1f}s) to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
