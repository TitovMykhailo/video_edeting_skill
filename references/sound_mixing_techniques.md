# Sound mixing techniques: layering, frequency space, and music transitions

`cinematic_principles.md`'s six-layer audio system and `editor_discipline.md`'s sound guidance
cover *when* and *why* to reach for a sound. This file is *how* — concrete post-production
mixing/editing techniques, the kind a working sound editor actually applies by hand. Some of these
this skill's scripts genuinely automate; others are real techniques with no safe, honest way to
script against Resolve's API, so they're documented as **manual steps to hand off to the human
editor** rather than faked as automated. Each section says explicitly which it is — don't assume
something here is scripted just because it's documented here.

## Frequency layering — automated by this pipeline

A single sound effect, even a good one, often reads as thin for a genuinely big moment — a lone
whoosh under a large dramatic movement lacks weight no matter how loud it's pushed. The fix isn't
volume, it's **frequency layering**: stack two or three sounds that occupy *different* parts of the
spectrum (a low sub-heavy layer for weight, a high airy layer for speed/detail, maybe a mid layer
for body) so the combined sound fills more of the audible range than any single layer could —
think of it as a cake with distinct flavor layers, not one flavor turned up louder.

This is directly supported by `beat_plan.json`'s per-beat `sfx` array — just add more than one
entry at the same (or a slightly offset) `at` timestamp, and tag each one's `frequency_layer`
(`"low"` / `"mid"` / `"high"`) so it's a deliberate choice, not an accident of whichever two clips
happened to get picked:

```jsonc
"sfx": [
  { "at": 0.0, "path": "sfx/whoosh-low-01.wav", "frequency_layer": "low", "gain_db": -3.0 },
  { "at": 0.0, "path": "sfx/whoosh-high-01.wav", "frequency_layer": "high", "gain_db": -6.0 }
]
```

`scripts/resolve/audio_design.py` places every entry in the list independently — no change needed
to use this, it already supports arbitrary layering, the only thing this adds is the *habit* of
picking complementary registers instead of two similar-sounding whooshes that mask each other.
Reserve this for beats that actually need the weight (an escalation/hero moment), not routinely —
see `editor_discipline.md` Part 12 on novelty control; three layered whooshes on every cut is just
a louder version of the same "SFX on everything" mistake, not a fix for it.

**The same idea applies beyond SFX.** Dialogue and music benefit from being thought of as
occupying their own frequency lanes too — which is exactly what the next technique does formally.

## Frequency-carve ducking — manual, not automated

The style profile's `music_bed.duck_gain_db` (see `beat_plan_schema.md`) is a blunt, whole-track
volume drop under narration — simple, reliable, and exactly what `audio_design.py` scripts. A more
refined technique some editors use goes further: instead of (or in addition to) lowering the
music's overall volume, use a **De-esser effect on the music track, not for its intended purpose**
— set it to target the mid-frequency range where dialogue/narration naturally sits, and it will
duck *specifically that frequency band* of the music rather than the whole track. This carves a
"pocket" for the voice in the frequency domain, not just the amplitude domain — the voice sits in
a spectral gap instead of just being loud enough to sit on top of the music. Combine with a normal
EQ cut on the dialogue's own low and high ends to help it sit cleanly in that pocket.

**This is a manual Fairlight technique, not something this skill's scripts apply.** Resolve's
scripting API doesn't offer a safe, verified way to add/configure an audio effect plugin
(De-esser, EQ, or otherwise) on a track — unlike the property-based calls (`SetProperty`, `SetCDL`)
this codebase already uses, effect-chain manipulation isn't something confirmed to work reliably
from a script without a live Resolve instance to test against, so it isn't attempted. When a
project's music bed genuinely needs this level of polish (dense music, dialogue-heavy narration
that still feels crowded after the normal duck), leave a note for it — see
`beat_plan_schema.md`'s `music_bed.manual_polish_notes` field — and apply it by hand in the
Fairlight page: a De-esser on the music bus keyed to the vocal's mid-range, then EQ the narration's
low/high ends to taste.

## Sound-pack / genre consistency — a tagging discipline

The single biggest lever for a coherent-sounding video isn't finding better individual sound
effects, it's **not mixing sound effects across genres**. Gritty bass-heavy hits that work for an
athletic/street promo will read as wrong on a wedding or corporate video, and vice versa — a broad,
general-purpose SFX library is great for range across many different projects, but pulling from it
indiscriminately *within one project* is what makes an edit feel generic instead of intentional.

`references/media_tagging_schema.md` has a `pack` field for exactly this — tag every asset with
which pack/library it came from (`"happy-editing-transitions"`, `"artlist-corporate"`, whatever the
source actually is), and query with `index_media.py query --pack <name>` to stay inside one
consistent sonic palette for a given project instead of free-mixing across every tagged asset in
the library. Pick the pack (or a small deliberate combination) once, early in a project, the same
way you'd lock a visual accent color — not asset by asset as beats come up.

## Emotional realism — a creative option for `emotional_beat` sound

Most sound design is diegetic-adjacent: a whoosh for movement, a click for a UI interaction, sounds
that plausibly belong to what's on screen. **Emotional realism** is the deliberate alternative:
replace the literal sound of what's happening with sounds from a completely different (but
thematically resonant) category, chosen for what the moment *means* rather than what it *is* —
coffee grounds breaking replaced with the crackling of ice, a coffee pour replaced with an ocean
crash, because the video's actual subject is something the literal kitchen sounds don't carry.

This is a real option to reach for on an `emotional_beat` beat in `beat_plan.json` (see
`beat_plan_schema.md`) when the beat's point is thematic/emotional rather than informational —
document the substitution logic in that beat's `reasoning` field so it's clear it's a deliberate
mismatch, not a mistagged sound effect. Use sparingly and commit fully when used: swapping in one
mismatched sound reads as an error, a whole passage built consistently on one substitute sound
category (e.g. "nature sounds standing in for every kitchen sound in this sequence") reads as a
choice. Don't reach for this by default — most `illustrative`/`emotional_beat` moments are better
served by sound that actually matches, per `cinematic_principles.md` system 6; this is a specific,
occasional tool, not a general replacement for sound correspondence.

## Music transitions — manual editing techniques

Fitting a full-length track into a short video's runtime by just cutting it off tends to feel like
slamming the brakes rather than arriving somewhere. Two real techniques for a smoother lead-in and
lead-out — both manual Edit/Fairlight-page work, not scripted by this pipeline:

**Lead-in, when the track has no natural intro:** take the track's own opening beat (or, if that
doesn't work rhythmically, its closing beat instead), reverse it, and use the reversed audio as a
riser leading into the track's actual start. Because it's built from the track's own material, it
blends in as if it were always part of the mix rather than an added effect. Also useful mid-video
for re-entering a track after a bridge or a quiet passage, not just at the very start.

**Lead-out, to end a track gracefully instead of an abrupt cut:** cut right before the beat that
would otherwise land after your intended out-point, take that final beat, and process it with
reverb (a long, spacious preset — "Great Hall" or equivalent is a reasonable starting point) played
underneath a fade of the original track. In Resolve terms: nest the final section into its own
timeline, duplicate and disable the duplicate (so it isn't heard twice), move the duplicate later
if needed to avoid overlap, then apply a Reverb plugin to the piece that plays — the wet reverb
tail becomes the transition-out instead of a hard stop.

**Cheat code — layer transition SFX on top of both techniques.** Risers, swells, and "suckback"
sounds layered under a lead-in make it read as more intentional; impacts, slams, or hits layered
under a lead-out give the ending more weight. This is the frequency-layering idea from the top of
this file applied specifically to music transitions rather than to a single cutaway's SFX — the
same principle, a different use case.

Since none of this is automated, write what a project's music bed actually needs into
`music_bed.manual_polish_notes` (`beat_plan_schema.md`) when planning — e.g. `"lead-in: reverse the
track's opening beat as a riser; lead-out: nest+reverb the final beat (Great Hall preset), layer a
soft impact under the last hit"` — so the intent survives from planning to the actual Fairlight
session even though the plan itself can't execute it.
