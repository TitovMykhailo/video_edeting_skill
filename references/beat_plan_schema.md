# Transcript, edit plan, and beat plan schemas

These are the data shapes that flow between pipeline stages. `transcript.json` and
`edit_plan.json`/`captions.json` are produced by scripts. `beat_plan.json` is produced by you
(Claude), reasoning over the others — there's no script for it because picking the right clip for
a sentence is a judgment call, not arithmetic. `references/editor_discipline.md` is the judgment
framework behind the fields marked "Layer B" below (eye targets, motion continuity, cut function,
novelty, confidence) — read it before filling those in for a project where that level of rigor
actually matters, and always run `scripts/validate_timeline.py` against the finished beat plan
before treating it as final (see "Timeline validation" below).

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
  "timing_basis": "audio_derived",   // "audio_derived" | "provisional" — see references/editor_discipline.md Part 1.
                                          // "provisional" means no real narration audio exists yet; every start/end
                                          // below is an estimate, not a measurement, and must be treated as such.
  "music_bed": {
    "path": "music/lofi-bed-01.mp3",
    "loop": true,
    "base_gain_db": -18.0,
    "duck_gain_db": -26.0,
    "manual_polish_notes": "lead-in: reverse the track's opening beat as a riser; lead-out: nest+reverb the final beat (Great Hall preset). Not automated — see references/sound_mixing_techniques.md."
  },
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
      "sfx": [
        { "at": 0.0, "path": "sfx/whoosh-01.wav", "gain_db": -6.0, "frequency_layer": "high" }
        // add a second entry at the same `at` with "frequency_layer": "low" for a beat that
        // needs real weight — see "Sound design fields" below and references/sound_mixing_techniques.md
      ],
      "shot_size": "close_up",              // optional, see "Richer shot design fields" below
      "attention_note": "eyes are the sole focal point, nothing else competes",   // optional
      "eye_target": {                          // optional Layer B field — see editor_discipline.md Part 2
        "primary": { "x": 0.5, "y": 0.45 },
        "secondary": null
      },
      "motion": {                                // optional — Part 3
        "direction": "static",
        "continuity": "n/a",                       // "continue" | "break" | "static" | "n/a"
        "note": "held shot, no motion to continue or break"
      },
      "cut_function": "comedy",                // optional — Part 19: information|energy|comedy|emotion|continuity|surprise|relief|beauty|orientation
      "novelty_score": 8,                        // optional, 1-10 relative to the previous shot — Part 12
      "confidence": 78,                          // optional, 0-100 — Part 27. Below 60, add a `candidates` array.
      "reasoning": "one sentence on why this clip, for your own future reference / debugging"
    },
    {
      "start": 3.1,
      "end": 7.4,
      "text": "...",
      "intent": "illustrative",
      "media": { "path": "...", "src_in": 2.0, "src_out": 6.3, "loop": false },
      "sfx": [],
      "candidates": [                          // optional — only for beats worth trying multiple approaches (Part 23)
        { "label": "A - restrained", "media": { "path": "...", "src_in": 0.0, "src_out": 3.0 }, "confidence": 74 },
        { "label": "B - aggressive", "media": { "path": "...", "src_in": 0.0, "src_out": 3.0 }, "confidence": 55 },
        { "label": "C - unconventional", "media": null, "note": "no visual — let the music drop out instead", "confidence": 62 }
      ],
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
  the `mood` field from the media index most. The sound side has an equivalent move available:
  "emotional realism" — deliberately scoring the beat with a thematically-resonant but literally
  mismatched sound category instead of a diegetic one (see `references/sound_mixing_techniques.md`)
  — occasional and only when the beat's point is genuinely thematic, not a default.
- **`intent: filler`** — nothing specific fits, or inserting something specific would be
  distracting during a dense explanation the viewer needs to actually follow. Pull from
  `media.filler_categories` in the style profile. This is not a failure case — plenty of good
  explainer edits are mostly filler with meme/illustrative beats punctuating it, not the reverse.
- **`media.src_in`/`src_out`** trim the *source clip*, independent of the beat's own duration —
  if the clip is longer than the beat, pick the best-fitting moment inside it rather than always
  starting at 0; if it's shorter, set `"loop": true` to repeat it for the rest of the beat.
  `resolve/timeline_build.py` does not freeze-frame a clip's last frame to fill the remainder —
  a shorter clip left without `loop: true` plays once and leaves the rest of the beat as an empty
  gap on the video track (the build script prints a warning when this happens). Loop, trim the
  beat's own `end` down to the clip's actual length, or pick a longer clip — don't rely on a hold
  that isn't actually implemented.
- Update `out/recent_uses.json` (a flat list of media paths) as you go, and consult it — a clip
  used in the last `media.meme_frequency_cap_s` seconds of runtime should be deprioritized unless
  it's a deliberate running gag. Track sound picks in the same file, alongside visual ones, so a
  sting doesn't get reused every time the narration hits a similar beat either.

### Sound design fields

- **Top-level `music_bed`** (optional — omit entirely if the video should run without one) is a
  single background track for the whole video, queried from the sound library with
  `index_media.py query --kind audio --pack <name> --tags "..." --mood ...` guided by the style
  profile's `sound_design.music_bed` notes and the overall tone of the script (pass `--pack` once a
  project has settled on one sound pack — see `references/sound_mixing_techniques.md`'s
  genre-consistency guidance). `base_gain_db` is its normal level; `duck_gain_db` is the lower
  level it should sit at under narration (a real, if crude, substitute for sidechain compression —
  see `resolve/audio_design.py` and `resolve_scripting_api.md` for how gain gets applied
  per-version-dependent Resolve APIs). Pick `loop: true` for anything shorter than the total
  runtime. **`manual_polish_notes`** (optional, free text, not read by any script) is where to
  write down a reversed-beat riser lead-in, a nested+reverb lead-out, or a De-esser frequency-carve
  duck — real techniques `references/sound_mixing_techniques.md` documents in detail, none of them
  scriptable against Resolve's API, so the intent gets handed to the human editor as a note instead
  of silently dropped.
- **Per-beat `sfx`** is a list (usually empty, sometimes one item, rarely more) of one-shot sounds
  timed to a specific moment *within* the beat — `at` is seconds from the beat's own `start`, not
  the timeline's start. Don't reach for "add a sound to this object" — the actual rule (see
  `references/cinematic_principles.md` system 6, "sound the change of state") is to sound the
  *moment something changes*: a cut, a reveal, an impact, an object entering or leaving frame.
  Reserve these for the moments the style profile's `sound_design.sfx_triggers` actually names —
  per `sound_design.sfx_not_on_every_cut`, a sound effect on every single beat reads as noisy and
  cheap rather than punchy. Query the sound library the same way as visuals:
  `index_media.py query --kind audio --tags "whoosh,transition" --limit 5`. For a beat that
  genuinely needs weight (an escalation/hero moment), stack two or three entries at the same `at`
  with complementary `frequency_layer` values (`"low"` / `"mid"` / `"high"`) instead of one loud
  sound — see `references/sound_mixing_techniques.md`'s frequency-layering technique; this is an
  optional annotation, `audio_design.py` already places every entry in the list independently, it
  doesn't need `frequency_layer` to do so — the field exists to make the layering a deliberate
  choice of complementary sounds while picking them, not an accident.
- Silence is a valid choice for both fields. Not every project needs a music bed, and most beats
  should have an empty `sfx` list — the goal is a few well-placed sounds, not constant coverage.
  Deliberately reserving a beat with no SFX and a lower music bed right before a big reveal (an
  energy-curve "breath," see `style_profile_schema.md`'s `energy_curve` field and
  `cinematic_principles.md`'s energy-curve section) is what makes the next loud beat land.

### Richer shot design fields (optional)

`shot_size`, `attention_note`, and similar fields (`depth_note`, `camera_motion_note`,
`ambience_override`) are optional per-beat annotations, not required for a routine auto-cut edit.
Fill them in when a project's visual craft actually matters — a hero shot, a video where the user
asked for cinematic quality specifically, or when you're using this schema for a from-scratch
design/storyboard deliverable rather than the automated pipeline (see `cinematic_principles.md`'s
shot-by-shot analysis format, which these fields are a lightweight version of). For a routine
fast-turnaround edit, `intent`/`media`/`reasoning` are enough — don't pad every beat with fields
that don't change the outcome.

### Machine-readable execution fields ("Layer B" — optional, for full editor-discipline rigor)

`eye_target`, `motion`, `cut_function`, `novelty_score`, `confidence`, and `candidates` exist so a
beat plan can eventually drive a real timeline (Premiere/Resolve/ffmpeg) without an executor having
to re-derive intent from prose — see `references/editor_discipline.md` Part 31. Same rule as the
richer shot-design fields above: fill these in when the project actually warrants full rigor (a
hero-moment-dense piece, anything going through the critique loop, anything the user explicitly
wants at "full production treatment" depth), not as a mandatory checklist for every routine cut.

- **`eye_target`** — normalized `x`/`y` (0–1, origin top-left) for where the shot's primary (and
  optionally secondary) focal point sits. Comparing consecutive beats' `eye_target` values is what
  turns "continuity vs. pattern interruption" from a vibe into a checkable decision — see
  `editor_discipline.md` Part 2.
- **`motion`** — `direction` (e.g. `"left_to_right"`, `"push_in"`, `"static"`), `continuity`
  (does the *next* beat continue this motion, deliberately break/reverse it, or is it not
  applicable), and a one-line `note` on why. Part 3.
- **`cut_function`** — one of `information | energy | comedy | emotion | continuity | surprise |
  relief | beauty | orientation`. If a beat's cut doesn't fit any of these, that's a signal to
  reconsider whether the beat needs to exist — Part 19.
- **`novelty_score`** — 1–10, relative to the *previous* beat, not an absolute rating. Used to spot
  a flatline (constant 9s) or check that a deliberate lull before a hero moment actually reads as
  low-novelty. Part 12.
- **`confidence`** — 0–100 on the beat's creative call (not on whether the JSON is well-formed).
  82+ ships as-is; 60–81 gets flagged for a render check; below 60 should come with a `candidates`
  array instead of a single unhedged choice. Part 27.
- **`candidates`** — an array of alternative approaches for a beat worth trying multiple ideas on
  (typically hero moments or anything below the 60-confidence threshold), each with its own `label`
  (e.g. `"A - restrained"`), its own media/approach, and its own `confidence`. Part 23. Picking
  between them is still your judgment call — the array records that the alternatives were actually
  considered, not just the winner.

### Timing validation

Before treating any `beat_plan.json` as final, run:

```bash
python3 scripts/validate_timeline.py --beat-plan out/beat_plan.json \
  --edit-plan out/edit_plan.json --script script.txt --out out/timeline_validation.json
```

(Swap `--edit-plan` for `--expected-duration <seconds>` on a `"provisional"` timing-basis project
that has no real `edit_plan.json` yet.) This checks the beat plan actually has full, non-overlapping
temporal ownership of the narration — no gaps, no overlaps, no script segments left unassigned or
covered twice. `expected_runtime_s`, `unassigned_vo_duration_s`, `timeline_gaps`, and
`unintentional_overlaps` should all come back empty/zero; `status` should read `PASS`. If it
doesn't, fix the beat plan and rerun rather than shipping a plan you know has a hole in it — see
`references/editor_discipline.md`'s "timeline integrity is non-negotiable" framing.
