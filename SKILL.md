---
name: video-editor
description: Automates turning a raw voiceover recording (plus an optional script) into a fully edited, styled video inside DaVinci Resolve — trims dead air and filler words without ever cutting a word in half, writes punchy animated captions, and fills the visual track with emotionally-matched b-roll, memes, and reaction clips pulled from the user's own media library or free stock APIs. Use this skill whenever the user asks to edit, cut, assemble, or automate a video with DaVinci Resolve, mentions turning a voiceover/narration/script into a finished video, wants auto-captions synced to speech, wants meme/b-roll insertion driven by what's being said, or references "the style" of a fast-cut explainer/video-essay (e.g. word-triggered memes, cartoon/sitcom cutaways matching the topic, low-key filler shots for neutral moments). Also use it to build or update a media-library tagging index, fetch stock b-roll, or create/edit a style profile for this pipeline.
compatibility: Requires a local machine with DaVinci Resolve installed and running (Free or Studio) — the Resolve scripting API only talks to a running local instance, so this skill cannot do the actual edit from a cloud/remote session. Also needs Python 3.9+, ffmpeg/ffprobe, and faster-whisper installed locally.
---

# Video Editor (voiceover → styled DaVinci Resolve edit)

## What this skill actually does

The user records narration (a voiceover, no talking head), optionally has a script text file,
and wants a finished, fast-paced, meme/b-roll-driven edit built automatically — the kind of
edit where every sentence has *something* happening on screen: a literal illustration, an
emotional-beat cutaway, a keyword-triggered meme, or (when nothing better fits) an unobtrusive
filler clip. The narration itself gets tightened — long pauses and filler words removed — but
**never mid-word**, because that's the one mistake that makes an auto-edit unusable.

This is a multi-stage pipeline. Some stages are deterministic scripts (transcription, silence
math, caption chunking). One stage — deciding *which clip goes with which sentence* — is a
judgment call that only you (Claude, reading the transcript with real comprehension) can make
well; don't try to reduce that to a keyword-matching script. Do the semantic work yourself, use
the scripts as tools for everything mechanical.

## Before anything else: confirm the environment

DaVinci Resolve's scripting API only works against a **running, local** copy of Resolve. If you
are executing in a cloud/remote/sandboxed session with no access to the user's machine, say so
plainly and stop — offer to prepare the project files (transcript, edit plan, captions, media
index) so the user can run the DaVinci Resolve stages themselves, or continue once you're
confirmed to be running locally (e.g. as Claude Code CLI on their machine).

When running locally, always start with:

```bash
python3 scripts/check_environment.py
```

This checks: Resolve is running and its scripting API is reachable, `ffmpeg`/`ffprobe` are on
PATH, `faster-whisper` is importable, and prints copy-pasteable fixes for anything missing
(including the per-OS environment variables Resolve's API needs — see
`references/resolve_scripting_api.md` if you need the details). Don't proceed past a red check;
walk the user through the fix first.

## Project layout

Each video is one project folder. There's no fixed required layout — find the audio/video and
script by asking the user or looking in the folder — but a typical one looks like:

```
my-project/
├── narration.wav          # or .mp3/.m4a — the raw voiceover recording
├── script.txt              # optional — intended text; transcript is ground truth for timing
├── style.json               # optional — defaults to assets/style-profiles/fast-explainer.json
└── out/                      # everything this skill generates lands here
    ├── transcript.json
    ├── edit_plan.json
    ├── beat_plan.json
    ├── captions.srt / captions.json
    └── render.mp4
```

A user's **media library** (their own folder of pre-collected clips/memes/show clips, plus a
`_stock_cache/` subfolder this skill manages for downloaded stock footage) is a separate,
long-lived folder reused across projects — not per-project. Ask for its path once and remember
it (e.g. suggest the user keep it in `config.json`, see `config.example.json`).

## The pipeline

Run these roughly in order. Steps 1–3 and 6 are scripts; steps 4–5 are you, reasoning.

### 1. Transcribe the narration

```bash
python3 scripts/transcribe.py --audio narration.wav --out out/transcript.json
```

Produces word-level timestamps via local `faster-whisper` (free, no API key, first run downloads
a model). If the user already has an SRT/VTT transcript from elsewhere, that's fine too — ask,
and skip this step, converting their file into the same `transcript.json` word-list shape
described in `references/beat_plan_schema.md` instead of re-transcribing.

### 2. Plan the cuts (silence + filler-word removal)

```bash
python3 scripts/plan_cuts.py --transcript out/transcript.json --out out/edit_plan.json \
  --style style.json
```

This is pure arithmetic on word timestamps — it finds gaps between words longer than the style
profile's `pause_threshold_s`, and (if `remove_filler_words` is on) filler words like "um"/"uh",
and marks them for removal, **snapped to word boundaries with a small pad** so a word is never
clipped. It outputs the segments of the original audio to keep, plus every word's timestamp
remapped onto the new, tightened timeline. Everything downstream (captions, beat timing) uses
this *new* timeline, not the original recording's.

Read the output once — check `total_new_duration` vs the original to sanity-check nothing
absurd happened (e.g. don't let it remove >40% of runtime; if it does, the pause threshold in
the style profile is probably too aggressive for this recording — loosen it and rerun).

### 3. Build captions

```bash
python3 scripts/build_srt.py --edit-plan out/edit_plan.json --out out/captions.srt \
  --captions-json out/captions.json --style style.json
```

Chunks the remapped words into short on-screen caption bursts per the style profile's caption
rules (max words/chars, break on punctuation). `captions.json` keeps per-word timing too, which
you'll want for step 5 (word-triggered memes need to know exactly when a word is spoken).

### 4. Index / grow the media library

Before planning which clip goes where, make sure the library is tagged:

```bash
python3 scripts/index_media.py scan --library <path-to-library> --out out/media_scan.json
```

This walks the folder, skips anything already tagged and unchanged, probes new/changed files
with ffprobe (flagging low-resolution or corrupt files), and — for videos — extracts a few
representative frames into a temp folder. **Look at those frames yourself** (`Read` the image
files) and write a short tag set + description + mood + a quality verdict for each file, the
user told you explicitly they want you doing this eyeballing rather than hand-tagging. Then
commit what you saw:

```bash
python3 scripts/index_media.py write-tags --library <path-to-library> --tags out/new_tags.json
```

See `references/media_tagging_schema.md` for the exact tag schema and for tagging guidance (what
makes a good tag set, how to judge quality, how to describe humor/meme clips so they're
findable later). Once tagged, a clip stays tagged — this step gets faster every project.

If the library is thin for a topic the script needs (e.g. nothing tagged "cooking"), and the
user opted into stock, pull a few candidates instead of leaving a gap:

```bash
python3 scripts/fetch_stock.py --provider pexels --query "chef cooking kitchen" --type video \
  --out-dir <path-to-library>/_stock_cache --limit 3
```

Downloaded stock also needs tagging — feed it through the same scan/write-tags cycle. See
`references/media_tagging_schema.md` for provider notes and licensing caveats (Giphy in
particular has commercial-use restrictions worth flagging to the user, not just Pexels/Pixabay).

### 5. Plan the beats — this is the creative core, do it yourself

Read `out/captions.json` (or `edit_plan.json`'s word list) together with `script.txt` if present,
and segment the narration into beats — roughly sentence/clause-sized chunks. For each beat,
decide what's on screen. `references/beat_plan_schema.md` has the exact output schema and, more
importantly, the decision framework the user asked for by example:

- a specific word lands and there's an obvious visual pun for it → meme, timed to that word
- the beat is explaining a concept/process → literal illustrative footage (cooking talk → kitchen
  clips; the reference example the user gave was literally this)
- the beat is a flat, matter-of-fact stretch of explanation → a deadpan/looping reaction or
  meme-format cutaway, the kind of "monotone narration + absurd cartoon clip" pairing from shows
  people already mine for reaction clips
- nothing specific fits → a low-key, non-distracting filler clip (screen recording, hands typing,
  ambient motion) so the frame is never just dead air, but it doesn't compete with the words

Query the tagged library for candidates per beat:

```bash
python3 scripts/index_media.py query --library <path-to-library> --tags "cooking,kitchen" \
  --mood deadpan --limit 5 --exclude-recent out/recent_uses.json --out out/candidates.json
```

then pick from the returned candidates using your own judgment (the query script only scores
tag/keyword overlap and recency — it can't tell you which candidate is actually the funniest or
most apt, that's your call). Keep a running `out/recent_uses.json` (just a list of recently used
file paths) so you naturally avoid reusing the same meme twice in one video. Write your final
per-beat decisions to `out/beat_plan.json` in the schema doc's format.

### 6. Build it in Resolve and render

```bash
python3 scripts/resolve/build_project.py --project-name "<name>" --edit-plan out/edit_plan.json \
  --beat-plan out/beat_plan.json --captions out/captions.srt --style style.json \
  --render-out out/render.mp4
```

This connects to the running Resolve instance, creates/opens the project, sets timeline
resolution/fps from the style profile's aspect ratio, imports every media file referenced by the
edit plan and beat plan into organized Media Pool bins, builds the trimmed narration audio track,
builds the video track from the beat plan, imports the caption SRT as a subtitle track, and
renders a draft MP4. It leaves the Resolve project open afterward for the user to fine-tune
(color, caption styling, manual trims) — this skill gets them 90% of the way, not a
push-button final master. Tell the user that explicitly once it's done.

If anything in this step errors, don't guess — read the Resolve error text (the API returns
useful messages) and check `references/resolve_scripting_api.md`'s troubleshooting notes before
retrying blindly.

## Style profiles

`assets/style-profiles/fast-explainer.json` is the default, modeled on the fast-cut,
meme-and-cutaway-driven explainer style the user pointed to as reference (dense visual changes,
punchy 2–4 word captions, aggressive pause trimming, frequent keyword-triggered memes). Copy and
edit it per channel/series rather than hand-editing the default — pass `--style path/to/your.json`
to every script above. Field-by-field meaning is in `references/style_profile_schema.md`.

## Aspect ratio

The user works in both 16:9 (long-form) and 9:16 (shorts). If it's not obvious from context or
the style profile, ask which this project is before step 6 — it changes timeline resolution,
caption sizing/position, and which stock/library clips are even usable (a landscape-only clip
needs cropping or should be skipped for a vertical edit; the query script's `--orientation` filter
handles this if you pass it).

## When something's ambiguous

Ask the user rather than guessing on anything that's expensive to redo: which media library path
to use, aspect ratio, whether to remove filler words as aggressively as the default profile does,
and — always — before spending stock-API quota or downloading a lot of files.
