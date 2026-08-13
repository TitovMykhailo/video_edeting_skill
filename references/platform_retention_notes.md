# Platform retention notes: what actually pushes a Short to more viewers

This is different in kind from `cinematic_principles.md`/`editor_discipline.md` — those are craft
principles that hold regardless of platform; this is specifically about how YouTube's own
distribution system decides whether to show a Short to more people. **Source honesty**: YouTube
does not publish its exact ranking algorithm. What follows is the consistent, cross-referenced
consensus from creator-community testing and reporting (multiple independent sources, current as
of writing) plus one YouTube-documented technical spec (loudness). Treat the mechanism claims as
well-supported inference, not documented fact — and treat every one of them as a reason to make
the *video* better, never as license for manipulative/clickbait tactics (see
`cinematic_principles.md`'s Hook design: "virality is a side effect of design working, not a
separate objective to chase").

## How distribution actually works

Reported as a staged process: a new Short first goes to a small sample audience (order of
hundreds of impressions), weighted heavily on **early hook retention** — if that sample doesn't
hold attention, distribution stops there. A Short that holds the sample keeps escalating to wider
audiences based on completion rate and swipe-through behavior, eventually reaching cross-surface
placement (home feed, inside long-form watch pages). The practical implication: there is no
"it'll pick up later" — the first few hundred viewers' behavior decides almost everything, which
is exactly why `editor_discipline.md`'s hook-design guidance and this project's own hook-beat fix
(replacing a flat title card with a real attention-grabbing visual) matter more than almost any
other single decision.

## Concrete signals reported to matter, heaviest first

1. **Early retention** (do viewers bail in the first 1-3 seconds).
2. **Full completion rate** — reported retention thresholds of roughly 65% completion for
   sub-30-second Shorts and 50% for 30-60-second Shorts as a rough bar for wider distribution.
   Below this, a Short is reported to plateau regardless of other quality.
3. **Re-watches** — a Short someone watches twice signals stronger satisfaction than one long
   watch of the same duration.
4. **Shares and comments** — stronger signals than likes.
5. **Likes.**
6. **Viewer satisfaction surveys** — YouTube has been adding 1-5 star pop-up surveys after some
   Shorts, feeding directly into ranking alongside behavioral signals. This is a real shift worth
   internalizing: it's no longer purely "did they keep watching," it's "did they actually like
   it" — a fast-but-hollow edit that holds attention through sheer cut speed without earning it
   (see `editor_discipline.md` Part 25, "retention engines, not just cut speed") is exactly the
   kind of content this signal is positioned to catch.

## What this means for how a Short should actually be built

- **The opening frame IS the hook, not an introduction to one.** No logo, no "hey guys," no
  context-setting before the hook lands — start on the most attention-grabbing visual/idea this
  script has. Reported creator testing: cutting the first several seconds of a "normal" edit and
  starting where the real hook already was measurably improved retention. This is the same
  principle behind this project's own hook-beat fix (see `editor_discipline.md`'s hook design —
  a bare text card is not a hook).
- **Design for rewatchability, not just one clean watch-through** — `editor_discipline.md` Part
  17 already covers this (plant a second layer of detail that rewards a second watch); it's not
  just a craft nicety, it's a direct, reported ranking signal (re-watches).
- **A loop-quality ending** (the last beat flows naturally back into how the video opened) is
  reported to specifically encourage the rewatch behavior above. Worth considering explicitly
  when planning a video's final beat, not just its first.
- **Completion rate rewards a video that's exactly as long as its idea needs and no longer** —
  padding a Short past where the idea actually ends to hit a "good" duration works against this
  signal, not for it.

## Audio: the one platform number that IS documented

YouTube normalizes uploaded audio toward **-14 LUFS integrated**. Content mixed louder than that
gets turned down automatically to match; content mixed quieter is left alone (no boost). Practical
targets:
- Mix to around **-14 LUFS integrated** as a safe baseline — this is what `assemble_video.py`
  targets via two-pass `loudnorm`.
  Some sources suggest sitting slightly hotter (-11 to -13 LUFS) to land just above the
  normalization threshold for a perceptually louder result post-normalization — untested by this
  skill, and pushing this without checking true-peak/dynamics could just as easily read as
  over-compressed; -14 is the documented-safe choice.
- Inconsistent or poorly-leveled audio (not just "too quiet") is reported to directly cost
  retention independent of loudness normalization — a clean, evenly-leveled mix at -14 LUFS beats
  an over-limited one hitting the same integrated number. See `sound_mixing_techniques.md` for
  the mixing-quality side of this; this file is about the delivery target, not how to get there.

## What NOT to do with any of this

Do not use any of the above to justify manipulative mechanics — misleading thumbnails/hooks,
fake cliffhangers with no payoff, forcing a rewatch through confusion rather than genuine replay
value. `cinematic_principles.md`'s originality rule and anti-patterns list still govern: design
the video to actually be worth those signals, don't reverse-engineer the signals instead of the
video.
