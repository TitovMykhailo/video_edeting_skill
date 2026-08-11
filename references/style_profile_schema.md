# Style profile schema

A style profile is a small JSON file every pipeline script reads (`--style path.json`). Two
calibrated starting points ship in `assets/style-profiles/`:

- **`nextcore-visual-essay.json`** — fast-cut, faceless visual-essay style: voice-over drives
  everything, the image changes with almost every phrase, typography and metaphor-driven cutaways
  do the emotional work. This is the closer match for a pure-voiceover workflow (no talking head)
  and is the default this skill assumes unless told otherwise.
- **`honeymontana-creator-led.json`** — talking-head + screen-demo style: the presenter is the
  visual anchor, cutaways (screen recordings, memes, reaction inserts) punctuate rather than
  replace them. Use this one for projects that do have a face-to-camera recording.

Both are calibrated off a detailed breakdown of two real channels (Nextcore vs. Honey Montana) —
see the field notes below for what each number is actually modeling. Copy whichever is closer to
a new file per channel/series rather than editing the shipped ones in place, so you can compare
and revert.

```jsonc
{
  "name": "nextcore-visual-essay",
  "description": "free text",

  "aspect_ratios": {
    "16:9": { "width": 1920, "height": 1080, "fps": 30 },
    "9:16": { "width": 1080, "height": 1920, "fps": 30 }
  },

  "narrative_arc": {
    "beats_template": [
      "hook", "visual_contradiction", "thesis", "example",
      "proof", "abstraction", "escalation", "conclusion"
    ],
    "cut_on": "change_of_idea",   // "change_of_idea" | "information_mode_change" — what actually
                                       // triggers a new beat/visual, see composition notes below
    "notes": "free text — read this before beat-planning a specific video, it's the intended arc shape"
  },

  "pacing": {
    "pause_threshold_s": 0.35,
    "keep_pause_s": 0.12,
    "pad_s": 0.04,
    "remove_filler_words": true,
    "filler_words": ["um", "uh", "..."],
    "max_removed_fraction_warning": 0.4,
    "shot_duration_by_intent_s": {
      "pattern_interrupt": [0.4, 1.0],
      "keyword_meme": [0.8, 1.8],
      "kinetic_typography": [1.0, 2.5],
      "illustrative_archival": [1.5, 3.5],
      "diagram_evidence": [2.0, 5.0],
      "emotional_footage": [2.0, 5.0]
    },
    "media_type_variety_rule": "prefer switching the underlying media TYPE (face/text/archive/object/UI) between consecutive beats over reusing the same type with a fancier transition — that's what actually resets attention"
  },

  "composition": {
    "layout": "centered",   // "centered" | "medium_talking_head_plus_screen"
    "hierarchy": ["headline_word", "hero_subject", "supporting_symbols"],
    "rule_of_one": "one dominant idea per frame, readable within about one second — collage is fine, illegibility is not"
  },

  "color": {
    "system": "editorial-contrast",   // "editorial-contrast" | "natural-tech-warm"
    "accent_hex": "#E0212B",
    "accent_usage": "headline words, key highlights, underline/arrow accents — never more than one accent color live on screen at once",
    "grade_cdl": {
      "slope": [1.0, 1.0, 1.0],
      "offset": [0.0, 0.0, 0.0],
      "power": [1.05, 1.05, 1.05],
      "saturation": 0.92
    },
    "notes": "contrast matters more than color count; footage inserts can run slightly desaturated so they read as 'texture' against cleaner graphic frames"
  },

  "camera_motion": {
    "techniques": ["push_in_scale", "position_slide_5_15pct", "mask_reveal", "opacity_reveal", "animated_underline_or_arrow", "parallax_on_stills", "layered_collage_build"],
    "avoid": "flashy 3D transitions that call attention to themselves — motion should sell the content, not the edit"
  },

  "transitions": {
    "backbone": "hard_cut",
    "rule": "the cut itself should be invisible; novelty comes from changing media type, not the transition effect"
  },

  "captions": {
    "enabled": true,
    "max_words_per_chunk": 4,
    "max_chars_per_chunk": 24,
    "max_duration_s": 1.8,
    "break_on_punctuation": true,
    "case": "sentence",
    "semantic_highlighter": true,
    "style_notes": "text is a semantic highlighter, not subtitles-everywhere — one phrase -> one key word -> one typography event, not every word needs to be on screen. See resolve_scripting_api.md for Tier 1/2 implementation."
  },

  "sound_design": {
    "voice": { "style": "dry, front of the mix", "compression": "moderate", "de_essing": "light" },
    "music_bed": { "role": "supports pacing, must never compete with VO", "ducking": "lower under narration, see references/beat_plan_schema.md music_bed field" },
    "sfx_triggers": ["semantic_cut", "new_evidence_reveal", "big_number_reveal", "punchline"],
    "sfx_not_on_every_cut": true
  },

  "media": {
    "meme_frequency_cap_s": 90,
    "beat_min_duration_s": 1.0,
    "beat_max_duration_s": 6.0,
    "filler_categories": ["ambient", "typing", "abstract-motion", "screen-recording"],
    "quality_min_height_px": 720
  },

  "render": {
    "preset": "H.264 Master",
    "format": "mp4"
  }
}
```

## Field notes

### `narrative_arc`
`beats_template` isn't a rigid checklist — it's the shape to check a script against before
beat-planning. Nextcore's is a compressed essay arc (hook → contradiction → thesis → proof →
escalation → conclusion); Honey Montana's (in its own profile) is more like cold-open → context on
camera → screen evidence → return-to-host reaction → deeper walkthrough → summary, repeatable as a
longer loop for interview-length content. `cut_on` documents *why* a cut happens in this style:
`change_of_idea` (Nextcore — cut whenever the sentence's point shifts, not when there's a pause)
vs `information_mode_change` (Honey Montana — cut when the video switches between "host talking",
"proof on screen", and "reaction", not on a fixed rhythm).

### `pacing.shot_duration_by_intent_s`
Replaces a single global pacing number with per-intent ranges — a keyword meme and a diagram
explanation shouldn't share a duration budget. These map loosely onto `beat_plan.json`'s `intent`
field (see `beat_plan_schema.md`); use judgment when an intent doesn't have an exact table entry,
these are calibration anchors, not a lookup table to satisfy mechanically.

### `composition.layout` and `color.system`
These two describe the two reference styles at a glance: `centered` + `editorial-contrast` is
Nextcore (one neutral base + one accent color, symbol/typography-first); `medium_talking_head_plus_screen`
+ `natural-tech-warm` is Honey Montana (a stable on-camera presenter, natural room/skin tones, dark
UI surfaces doing the contrast work instead of a graphic accent color). Don't mix `layout` from one
system with `color.system` from the other without a reason — they're calibrated as pairs.

### `color.grade_cdl`
Applied via DaVinci Resolve's CDL (Color Decision List) controls — `slope`/`offset`/`power` are
per-channel RGB multiplier/lift/gamma the way any color panel exposes them (1.0/0.0/1.0 = no
change), `saturation` is a single global multiplier. These are deliberately conservative starting
numbers (a small contrast push for Nextcore's `editorial-contrast`, a small warm nudge for Honey's
`natural-tech-warm`) meant to be nudged by eye against real footage, not treated as exact science —
see `scripts/resolve/color_grade.py` and `references/resolve_scripting_api.md` for how this gets
applied, and don't be afraid to adjust these per project once you've looked at a render.

### `sound_design`
Free-text guidance rather than machine-parsed numbers, because voice/mix decisions depend on the
actual recording. What *is* machine-consumed is the beat plan's `sfx` and `music_bed` fields (see
`beat_plan_schema.md`) — `sound_design` here is the judgment context for filling those in well:
Nextcore fires a sound effect on a meaningful reveal, not on every cut; Honey Montana keeps the
natural voice high in the mix and uses SFX mostly for UI highlights and meme stingers.

### Everything else
`pacing.pause_threshold_s`/`keep_pause_s`/`pad_s`, `captions.*`, and `media.*` carry over unchanged
from the original schema — see the inline comments above; `pad_s` in particular is still the most
important safety number in the whole pipeline (never let a cut clip a word).
