# Style profile schema

A style profile is a small JSON file every pipeline script reads (`--style path.json`). Default:
`assets/style-profiles/fast-explainer.json`. Make a copy per channel/series rather than editing
the default in place, so you can compare/revert.

```jsonc
{
  "name": "fast-explainer",
  "description": "free text, for your own reference",

  "aspect_ratios": {
    "16:9": { "width": 1920, "height": 1080, "fps": 30 },
    "9:16": { "width": 1080, "height": 1920, "fps": 30 }
  },

  "pacing": {
    "pause_threshold_s": 0.35,     // gap between words longer than this counts as cuttable silence
    "keep_pause_s": 0.12,           // shortened pause length actually kept, so speech doesn't feel jump-cut
    "pad_s": 0.04,                     // safety padding kept around every word — never shrink this to 0,
                                          // it's the margin that guarantees a word never gets clipped
    "remove_filler_words": true,
    "filler_words": ["um", "uh", "..."],   // case-insensitive, matched against transcript words
    "max_removed_fraction_warning": 0.4,   // plan_cuts.py warns (doesn't fail) past this
    "min_visual_change_s": 2.5      // guidance for beat planning: don't let one clip run longer
                                          // than this without a cut, zoom, or overlay change
  },

  "captions": {
    "enabled": true,
    "max_words_per_chunk": 4,
    "max_chars_per_chunk": 24,
    "max_duration_s": 1.8,
    "break_on_punctuation": true,
    "case": "sentence",              // "sentence" | "upper"
    "style_notes": "free text describing the visual look, read by you (Claude) when building
                    the Resolve subtitle track style / Tier 2 Fusion captions — not machine-parsed"
  },

  "media": {
    "meme_frequency_cap_s": 90,      // don't reuse the same clip within this many seconds of runtime
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

- **`pacing.pause_threshold_s` vs `keep_pause_s`**: a silence gets *shortened* to `keep_pause_s`,
  not deleted entirely, unless the gap is huge (several seconds — a real dead stop). Deleting every
  pause to zero produces the telltale "auto-edited podcast" clipped-cadence sound; keeping a small
  gap preserves natural breathing rhythm.
- **`pacing.pad_s`**: applied on both sides of every kept word before computing cut points. This
  is the single most important safety number in the whole pipeline — it's what prevents a plosive
  or trailing consonant from getting sliced off. If a rendered edit ever sounds like it clips a
  word, raise this first before touching anything else.
- **`media.meme_frequency_cap_s`** is enforced by *you* during beat planning (tracked via
  `out/recent_uses.json`), not by any script — `index_media.py query` merely deprioritizes recent
  files, it doesn't hard-block them, because sometimes reusing a running-gag clip is the right call.
- **`captions.style_notes`** is intentionally free text. Nothing parses it; it's there so the
  profile document is self-contained when you're deciding how to configure Resolve's subtitle
  track style or a Tier 2 Fusion caption template (see `resolve_scripting_api.md`).
