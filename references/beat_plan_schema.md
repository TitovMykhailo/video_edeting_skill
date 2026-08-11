# Transcript, edit plan, and beat plan schemas

These are the data shapes that flow between pipeline stages. `transcript.json` and
`edit_plan.json`/`captions.json` are produced by scripts. `beat_plan.json` is produced by you
(Claude), reasoning over the others — there's no script for it because picking the right clip for
a sentence is a judgment call, not arithmetic.

## `transcript.json` (from `transcribe.py`, or hand-built from an existing SRT/VTT)

```jsonc
{
  "language": "en",
  "duration_s": 187.4,
  "words": [
    { "word": "so", "start": 0.12, "end": 0.34, "prob": 0.98 },
    { "word": "if", "start": 0.40, "end": 0.51, "prob": 0.99 }
  ]
}
```

If converting an existing subtitle file instead of running Whisper, it's fine if you only have
per-line timing rather than per-word — split each line's duration proportionally across its words
as an approximation and note in the run that timing precision will be lower.

## `edit_plan.json` (from `plan_cuts.py`)

```jsonc
{
  "source_duration_s": 187.4,
  "total_new_duration_s": 141.9,
  "removed_fraction": 0.243,
  "keep_segments": [
    { "src_start": 0.0, "src_end": 12.4, "new_start": 0.0, "new_end": 12.4 },
    { "src_start": 12.9, "src_end": 30.1, "new_start": 12.52, "new_end": 29.72 }
  ],
  "words_new_timeline": [
    { "word": "so", "start": 0.12, "end": 0.34 },
    { "word": "if", "start": 0.40, "end": 0.51 }
  ]
}
```

`keep_segments` are ranges *into the original audio file* — that's what `resolve/timeline_build.py`
uses to trim the source clip when appending it to the timeline. `words_new_timeline` are word
timestamps already remapped onto the tightened output — that's what captions and beat timing are
built from. Never mix the two coordinate spaces.

## `captions.json` (from `build_srt.py`)

```jsonc
{
  "chunks": [
    {
      "text": "so if you're",
      "start": 0.12,
      "end": 1.05,
      "words": [
        { "word": "so", "start": 0.12, "end": 0.34 },
        { "word": "if", "start": 0.40, "end": 0.51 },
        { "word": "you're", "start": 0.55, "end": 1.05 }
      ]
    }
  ]
}
```

All timing here is already on the new (post-cut) timeline.

## `beat_plan.json` (you write this, following step 5 in SKILL.md)

```jsonc
{
  "beats": [
    {
      "start": 0.0,
      "end": 3.1,
      "text": "so if you're looking to actually get better at something fast",
      "intent": "keyword_meme",           // "keyword_meme" | "illustrative" | "emotional_beat" | "filler"
      "trigger_word": "looking",             // only for keyword_meme; must exist in this beat's word list, used to time the cutaway to the exact word
      "media": {
        "path": "relative/path/eyes-looking-meme.mp4",
        "src_in": 0.0,
        "src_out": 1.6,
        "loop": false
      },
      "reasoning": "one sentence on why this clip, for your own future reference / debugging"
    },
    {
      "start": 3.1,
      "end": 7.4,
      "text": "...",
      "intent": "illustrative",
      "media": { "path": "...", "src_in": 2.0, "src_out": 6.3, "loop": false },
      "reasoning": "..."
    }
  ]
}
```

Guidance on filling this in:

- **Beat boundaries** don't have to be one per sentence — split long sentences that cover two
  different ideas, and merge short fragments that belong to one visual idea, guided by
  `pacing.min_visual_change_s` and `media.beat_min_duration_s`/`beat_max_duration_s` in the style
  profile.
- **`intent: keyword_meme`** — reserve for a genuinely clean pun/match on a specific word (like
  "looking" → eyes), not every noun that has a vaguely related clip. Overusing this intent is what
  makes an auto-edit feel like a slot machine instead of a joke landing.
- **`intent: illustrative`** — the beat is *about* something concrete (a place, an activity, an
  object) and the clip should just show that thing, literally.
- **`intent: emotional_beat`** — the narration's tone (not its literal content) is what's driving
  the pick: flat/matter-of-fact explanation gets a deadpan or absurdist cutaway, a punchline gets
  a reaction clip, building tension gets something visually tense. This is the intent that needs
  the `mood` field from the media index most.
- **`intent: filler`** — nothing specific fits, or inserting something specific would be
  distracting during a dense explanation the viewer needs to actually follow. Pull from
  `media.filler_categories` in the style profile. This is not a failure case — plenty of good
  explainer edits are mostly filler with meme/illustrative beats punctuating it, not the reverse.
- **`media.src_in`/`src_out`** trim the *source clip*, independent of the beat's own duration —
  if the clip is longer than the beat, pick the best-fitting moment inside it rather than always
  starting at 0; if it's shorter, either loop it (`"loop": true`) or accept it running once and
  holding last frame, per what looks natural for that clip.
- Update `out/recent_uses.json` (a flat list of media paths) as you go, and consult it — a clip
  used in the last `media.meme_frequency_cap_s` seconds of runtime should be deprioritized unless
  it's a deliberate running gag.
