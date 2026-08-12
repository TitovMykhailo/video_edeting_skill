# Troubleshooting

Resolve-specific connection/API errors are covered in `resolve_scripting_api.md`. This file is
everything else.

## `faster-whisper` is slow / seems stuck

- First run of `transcribe.py` downloads the model (a few hundred MB for `small`) — that's a
  one-time delay, not a hang. Subsequent runs reuse the cached model.
- CPU-only transcription of a 10-minute recording with the `small` model takes a few minutes on a
  typical laptop; that's normal. If it's dramatically slower, check nothing else is pegging the
  CPU, or drop to the `base` model (`--model base`) for a speed/accuracy tradeoff — good enough
  for cut-planning purposes even if a few words come out slightly off, since the transcript's job
  is timing, not a publishable transcript.
- If a GPU is available, faster-whisper picks it up automatically when `ctranslate2` was installed
  with CUDA support; no flag needed from this skill's scripts.

## `plan_cuts.py` removed way more than expected

If `removed_fraction` in `edit_plan.json` is high (the script warns past
`pacing.max_removed_fraction_warning`), the recording likely has longer natural pauses than the
style profile's `pause_threshold_s` assumes (common with a slower, more deliberate speaking style).
Raise `pause_threshold_s` in the style profile and rerun rather than accepting an edit that sounds
over-compressed — listen to a rendered sample before committing to a threshold for a given voice.

## A word sounds clipped in the render

This means `pacing.pad_s` is too small for this specific voice/mic (fast talkers or plosive-heavy
speech need more margin). Raise `pad_s` (try doubling it) and rerun `plan_cuts.py` and everything
downstream — this is cheap to redo since it's all deterministic from `transcript.json` onward.

## `index_media.py scan` finds nothing / thinks everything changed

The change-detector is `size + mtime`, not a content hash — copying files in a way that resets
mtime (some cloud-sync tools do this) will make already-tagged files look new again. If that's
happening a lot, keep the library outside of any sync-and-flatten folder, or ask before assuming a
huge tagging pass is actually needed if the library hasn't really changed.

## Stock API returns nothing / 401 / 429

- 401 → the relevant env var (`PEXELS_API_KEY` / `PIXABAY_API_KEY` / `GIPHY_API_KEY`) isn't set or
  the key is wrong. `fetch_stock.py` checks for the env var up front and tells you which one is
  missing plus where to register for a free key — don't guess at a key or try to fetch without one.
- 429 → rate limited. Free tiers are modest (Pexels: 200 requests/hour by default). Space out
  fetches across a session rather than retrying in a loop; this is exactly the kind of thing to
  surface to the user rather than silently burning through remaining quota on retries.
- A search returning irrelevant results isn't a bug to fix in code — it's a cue to pick a better
  query, or fall back to the user's own library / a different provider for that particular beat.

## Nothing renders / render job fails

Check `project.GetRenderJobStatus(job_id)` for the failure reason before retrying — the most
common cause is `render.preset` in the style profile naming a render preset that doesn't exist
in this Resolve installation yet (presets aren't shared across machines by default). Either
create the preset once in Resolve's Deliver page and save it under that exact name, or change the
style profile to a preset that already exists (`project.GetRenderPresetList()` lists what's
available).

## Render reports "Complete" but the error is about a missing video stream

This is `render.py` catching a real Resolve gotcha, not a false alarm: a `Complete` job status
only means the render ran, not that it produced the file you asked for — `SetRenderSettings`
layers its keys on top of whatever the Deliver page's render state already holds, so a stale
"Audio Only" preset from an earlier Resolve session can survive into this build's job and produce
an audio-only file in seconds. Open the Deliver page, confirm "Export Video" is checked and a
video codec/format is selected under this project's render settings, then rerun. See
`resolve_scripting_api.md`'s "Independently verified gotchas worth knowing" section.

## A build fails with "AppendToTimeline placed N/M ..."

Resolve silently drops a clip from a batch append when its record range overlaps an earlier one
on the same track — no error from Resolve itself, just a shorter-than-expected result list, which
`timeline_build.py`/`audio_design.py` now check for explicitly instead of trusting a non-empty
return. If the message names video beats, rerun `validate_timeline.py` against `beat_plan.json`
first — it already checks the beat list itself for gaps/overlaps, so it'll usually find the same
collision at the planning stage. If it names SFX cues or a music bed segment, `validate_timeline.py`
won't catch it (it only looks at `beats`, not `sfx`/`music_bed`) — check by hand for two SFX cues
placed too close together on the same beat, or a `sfx[].at` offset that lands past the next beat's
start.

## General principle

Every stage before "build in Resolve" is cheap and deterministic to rerun — transcript, edit plan,
captions, and even the beat plan are just files. If something in the final render looks wrong,
figure out *which stage's output* is actually wrong (read the JSON, don't just stare at Resolve),
fix the input/config at that stage, and rerun forward from there rather than hand-patching inside
the Resolve project.
