#!/usr/bin/env python3
"""Synthesize a short sound effect with ffmpeg's own audio generators — no sample library needed.

Why this exists: this skill's sound-effect workflow (references/sound_mixing_techniques.md,
--pack in index_media.py) assumes a real SFX library exists to query. When one doesn't yet (a
fresh project, or a genre this skill's own library has no packs for), there's been no automated
way to get SFX at all — "no automated stock source for audio" per README.md. Real sourced SFX
from a proper library/pack will always sound better and stay genre-consistent; this is a fallback
for exactly the gap, not a replacement — see sound_mixing_techniques.md's pack-discipline guidance
before reaching for this on a project that already has a real sound library.

Four --kind values, covering the common fast-cut-edit cues:
  whoosh   A band-passed noise sweep with a rising-then-falling envelope — a swipe/transition
           accent. --duration ~0.25-0.5s is typical.
  impact   A short, pitched-down burst (sine sweep + noise) with a fast attack/decay — a hit/
           thud accent for a hard cut or a reveal. --duration ~0.15-0.3s is typical.
  riser    A rising sine sweep with a slow fade-in — tension-build before a payoff beat.
           --duration ~0.5-2s is typical.
  click    A very short, high-frequency tick — a UI/notification-style accent for a keyword pop.
           --duration ~0.05-0.1s is typical.

These are synthesized, not sampled — they read as clean, simple, slightly digital accents, not
a mixed/mastered SFX pack. Good enough to give a cut real punch; swap in a real library asset
(references/sound_mixing_techniques.md) once one exists for this project's genre.

Usage:
    python3 synth_sfx.py --kind whoosh --duration 0.35 --out out/generated/whoosh_01.wav
    python3 synth_sfx.py --kind impact --duration 0.2 --pitch 90 --out out/generated/impact_01.wav
"""
import argparse
import subprocess
import sys


def build_filter(kind, duration, pitch):
    if kind == "whoosh":
        # Band-passed white noise, the passband sweeping up then down over the duration (a
        # sidechain-style envelope on center frequency isn't directly expressible in one filter,
        # so this approximates it with an amplitude envelope shaped like a swipe: fast attack,
        # slow release) plus a bandpass roughly in the "air"/swoosh range.
        return (
            f"anoisesrc=d={duration}:c=pink:a=0.6,"
            f"bandpass=f=2500:width_type=h:w=3000,"
            f"afade=t=in:d={duration * 0.3}:curve=iqsin,"
            f"afade=t=out:st={duration * 0.4}:d={duration * 0.6}:curve=iqsin"
        )
    elif kind == "impact":
        # A fast pitched-down sine "thump" layered with a short burst of low-passed noise for
        # weight — the standard cheap-impact recipe (a real recorded hit has much richer
        # transient detail than this can fake; this is a clean accent, not a substitute).
        low = max(40, pitch)
        return (
            f"sine=frequency={low * 3}:duration={duration}[tone];"
            f"[tone]afade=t=out:st=0:d={duration},asetrate=44100*0.5,aresample=44100[thump];"
            f"anoisesrc=d={duration}:c=brown:a=0.5,lowpass=f=200,afade=t=out:st=0:d={duration}[rumble];"
            f"[thump][rumble]amix=inputs=2:duration=shortest[out]"
        )
    elif kind == "riser":
        # A sine sweep from a low to a high frequency over the whole duration, fading in — the
        # classic "tension building toward a beat" cue.
        end_freq = max(pitch * 8, 800)
        return (
            f"aevalsrc=0.5*sin(2*PI*t*({pitch}+({end_freq}-{pitch})*t/{duration})):d={duration},"
            f"afade=t=in:d={duration * 0.7}"
        )
    elif kind == "click":
        return f"sine=frequency={max(pitch, 1500)}:duration={duration},afade=t=out:st=0:d={duration}"
    else:
        raise ValueError(f"Unknown kind '{kind}'")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kind", required=True, choices=["whoosh", "impact", "riser", "click"])
    parser.add_argument("--duration", type=float, default=0.3)
    parser.add_argument("--pitch", type=float, default=110, help="base frequency in Hz — meaning varies by --kind, see this module's docstring")
    parser.add_argument("--out", required=True, help="a .wav path")
    args = parser.parse_args()

    is_complex = args.kind in ("impact",)
    filter_str = build_filter(args.kind, args.duration, args.pitch)
    # Source filters (sine=, anoisesrc=, aevalsrc=) generate audio from nothing, so neither form
    # needs a real -i input file — but the two forms are NOT interchangeable syntax: a single
    # generator chain is a -f lavfi -i "..." INPUT, while a graph combining multiple generators
    # (impact's tone+rumble mix) is a -filter_complex GRAPH with no -i needed at all. Building
    # both from one half-shared prefix previously dropped -i entirely from the simple form and
    # fed the literal word "lavfi" to ffmpeg as if it were the complex-form's filter graph —
    # reproduced live, both failed immediately. Kept as two explicit, separate command shapes.
    if is_complex:
        cmd = ["ffmpeg", "-y", "-filter_complex", filter_str, "-map", "[out]"]
    else:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", filter_str]
    cmd += ["-ar", "44100", "-ac", "1", args.out]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"Synthesizing {args.kind} failed:\n{result.stderr[-2000:]}")
    print(f"Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
