# Media library tagging schema

The library is one folder the user reuses across projects — their own collected clips/memes, a
`_stock_cache/` subfolder this skill manages for downloaded visual stock, and (recommended) a
`sfx/` and `music/` area for sound assets. Visual and audio assets share the same index and the
same scan/write-tags/query workflow; `scripts/index_media.py` keeps one file at the library root:
`_media_index.json`. You never edit that file by hand — `scan` reads it, `write-tags` writes it,
`query` reads it.

## `_media_index.json` shape

```jsonc
{
  "files": {
    "relative/path/clip.mp4": {
      "hash": "size:1234567,mtime:1733939200",   // cheap change-detector, not a real content hash
      "kind": "video",                                 // "video" | "image" | "gif" | "audio" — always set,
                                                            // independent of `probe` (which can be null if ffprobe is missing)
      "probe": {
        "duration_s": 4.2,
        "width": 1920,
        "height": 1080,
        "orientation": "landscape",               // "landscape" | "portrait" | "square" — visual only
        "codec": "h264",
        "kind": "video"
      },
      "tags": ["cooking", "kitchen", "chopping", "sitcom"],
      "description": "Two people chopping vegetables on a busy restaurant line, quick cuts, loud kitchen energy.",
      "mood": "chaotic-energetic",
      "quality_ok": true,
      "quality_notes": "",
      "source": "own_library",                         // "own_library" | "stock:pexels" | "stock:pixabay" | "stock:giphy"
                                                            // | "generated:kinetic_text" | "generated:chart" | "generated:html_motion"
      "ip_risk": null,                                     // null | "studio_ip" | "recognizable_individual" — see
                                                            // "Copyright/IP risk tagging" below and editor_discipline.md's policy Part
      "pack": null,                                        // which sound pack/library this came from (e.g. "happy-editing-transitions"),
                                                            // mainly meaningful for audio — see references/sound_mixing_techniques.md
      "energy": null,                                     // audio-only, see below
      "loopable": null,                                    // audio-only
      "tempo_bpm": null,                                  // audio-only
      "tagged_at": "2026-08-11T12:00:00Z"
    }
  }
}
```

## Tagging guidance for visual assets (video/image/gif)

`index_media.py scan` hands you a list of files it can't classify yet plus a few extracted frames
per video (stills, not the whole clip — enough to judge content, not to watch it). For each one,
look at the frames and write:

- **`tags`**: 3–8 short, lowercase, single-or-two-word tags. Mix *literal content* tags (what's
  physically in frame: "kitchen", "typing", "crowd") with *usage* tags (what beat it'd fit: "meme",
  "reaction", "process-shot", "establishing"). Specific beats a keyword-triggered meme (e.g. "eyes
  looking around" for the word "looking") should get a tag that names the pun directly, like
  `looking-eyes` or `side-eye`, so `query` can find it by a near-exact match later.
- **`description`**: one sentence, plain language, written so that *you*, months later with zero
  memory of tagging this file, could decide from the sentence alone whether it fits a given beat.
- **`mood`**: a single word or short hyphenated phrase describing emotional register — e.g.
  `deadpan`, `chaotic-energetic`, `wholesome`, `dramatic-tension`, `absurdist`. This is what lets
  beat planning match "the narration just went flat and matter-of-fact" to the right cutaway.
- **`quality_ok`** / **`quality_notes`**: fail a clip for being blurry, heavily watermarked, too
  low-resolution for the target aspect ratio (cross-check `media.quality_min_height_px` in the
  style profile), or containing a burned-in logo/caption that would clash with this skill's own
  captions. A failed clip stays in the index (so it's not re-scanned every time) but `query`
  excludes it by default.
- Don't over-invest per clip — a few seconds of looking and a one-line judgment is the target. The
  index gets better over time as the library grows; it doesn't need to be perfect on pass one.

## Copyright/IP risk tagging

Set `ip_risk` on a clip when a viewer would recognize it at a glance as coming from something
specific and owned:

- `"studio_ip"` — a shot from a specific movie/show/game is identifiable as such (a distinctive
  character, a recognizable set/HUD, a well-known scene) — real Content ID / claim / demonetization
  exposure. A meme library built by scraping reaction clips accumulates these constantly; tag them
  as you find them rather than only when something goes wrong.
- `"recognizable_individual"` — a real, identifiable person (not a fictional character), even if
  the clip itself isn't from copyrighted media — different risk profile (personality rights, not
  Content ID) but still worth flagging the same way.
- Leave `null`/omit for your own footage, code-generated clips, licensed stock, and generic
  non-identifiable reaction content — the common, low-risk case.

This is a visibility flag, not a ban — `query`'s scoring never penalizes an `ip_risk` clip, it just
appends a `WARNING: tagged ip_risk=...` reason so the flag is impossible to miss at the exact
moment the clip is being considered. What to actually do about a flagged clip is a project-level
creative/legal call — see `editor_discipline.md`'s copyright-risk policy Part for the concrete
tiers-and-limits framework, not a rule enforced here.

## Tagging guidance for audio assets (SFX/music)

You can't literally listen to an audio file, so `index_media.py scan` gives you the next best
thing for judging it: a rendered **waveform image** (a still PNG of the amplitude over time,
generated via ffmpeg's `showwavespic`). Reading that image gets you surprisingly far:

- A tight cluster of tall, sharp spikes → a **percussive** hit/transient (a whoosh, click, stinger,
  impact) — good for a cut-point accent, bad as a bed.
- A long, relatively even, rolling waveform → a **sustained** loop (a music bed, ambient pad,
  drone) — good under narration, bad as a standalone accent.
- A waveform with a clear loud spike followed by a long fading tail → an **impact** sound
  (a boom, riser-and-drop) — good for a single dramatic beat, not for looping.

Combine that visual read with the filename (creators usually name SFX/music somewhat
descriptively — "whoosh", "ding", "lofi-loop", "tension-pad") and, when present, whatever folder
structure the user already organized (`sfx/`, `music/`, `sfx/transitions/`). Then write:

- **`tags`**: same idea as visual tags — what it *is* ("whoosh", "click", "riser") plus what it's
  *for* ("transition", "reveal", "punchline", "background-bed").
- **`pack`**: which pack/library the file came from (e.g. `"happy-editing-transitions"`,
  `"artlist-corporate"`) — infer it from the folder it landed in under `_stock_cache/` or
  wherever the user dropped a downloaded pack. This is what lets `query --pack <name>` keep a
  whole project's SFX genre-consistent instead of free-mixing across everything ever tagged — see
  `references/sound_mixing_techniques.md`, this is the single highest-leverage habit for a
  coherent-sounding edit. Leave `null` for one-off files that don't belong to any pack.
- **`mood`**: same field as visual assets, same purpose — lets a beat's emotional register (from
  `beat_plan.json`) pull a mood-matched sound the same way it pulls a mood-matched cutaway.
- **`energy`**: `"percussive"` | `"sustained"` | `"impact"` | `"ambient"` — your read of the
  waveform shape, see above. This is the field beat planning uses to pick "a short accent" vs "a
  bed to sit under a whole section."
- **`loopable`**: `true` if the waveform looks like it could repeat cleanly (a bed/loop) without an
  obvious edit-breaking transient at the start/end; `false` for anything one-shot (most SFX).
- **`tempo_bpm`**: only if you can reasonably infer it (a filename that states it, or a visibly
  even rhythmic pulse in the waveform) — leave `null` rather than guessing a number that isn't
  there, a wrong BPM is worse than none for pacing decisions later.
- **`quality_ok`**: fail anything that's clearly clipped/distorted-looking in the waveform (flat-
  topped spikes) or absurdly short/silent.

## `query` output shape

```jsonc
{
  "results": [
    {
      "path": "relative/path/clip.mp4",
      "kind": "video",
      "pack": null,
      "score": 3.4,
      "reasons": ["tag match: cooking", "tag match: kitchen", "mood match: chaotic-energetic"],
      "probe": { "...": "as above" },
      "tags": ["..."],
      "description": "...",
      "mood": "...",
      "energy": null,
      "loopable": null,
      "tempo_bpm": null,
      "ip_risk": null              // present whenever tagged — also surfaced as a "WARNING: ..." reason string
    }
  ]
}
```

`score` is a simple heuristic (tag/keyword overlap + mood bonus − recency penalty) meant to
shortlist candidates, not to pick for you — always read `description`/`tags` on the shortlist and
choose with judgment, same as a human editor scanning a bin. Pass `--kind audio` to search only
the sound library (e.g. when picking a beat's `sfx` or the video's `music_bed` — see
`beat_plan_schema.md`), or `--kind video`/`image`/`gif` to keep visual queries from surfacing
sound files by accident. Add `--pack <name>` once a project has settled on a sound pack to stay
inside it for every subsequent SFX/music query — a hard filter, not a scoring bonus, since the
whole point is not seeing options from other packs at all.

## Stock providers (`fetch_stock.py`)

| provider | good for | licensing note |
|---|---|---|
| Pexels | high-quality neutral b-roll (typing, offices, nature, city) | Free for commercial use, no attribution required |
| Pixabay | similar to Pexels, wider but more variable quality | Free for commercial use, no attribution required |
| Giphy | reaction gifs / meme-format clips | Giphy's API terms restrict some commercial/monetized uses — **flag this to the user** before pulling Giphy content into anything monetized; when in doubt use the user's own library for meme/reaction content instead |

Downloaded files land in `<media_library_path>/_stock_cache/<provider>/` with a small metadata
JSON sidecar (query used, source URL, license note) that `index_media.py scan` picks up like any
other new file — they still need the same tagging pass before `query` will surface them well,
since a generic "typing on laptop" search result needs an actual mood/description judgment too.

There's still no scripted `fetch_stock.py`-equivalent for audio (no API-key-based automation) —
free stock-audio APIs with clear, standardized commercial-use terms are less consistent than
Pexels/Pixabay for video. But a real, repeatable MANUAL workflow now exists and is worth using
over `scripts/generate/synth_sfx.py`'s synthesized tones whenever real SFX matter more than zero
setup time (synthesized whooshes/impacts are a functional fallback, not a substitute for real
sound design — see `sound_mixing_techniques.md`):

- **Mixkit** (mixkit.co/free-sound-effects/) — free for commercial and non-commercial use, no
  attribution required. Its category pages (`/free-sound-effects/whoosh/`, `/impact/`, `/click/`,
  `/cinematic/` for riser-style tension builds, etc.) are plain enough that `curl`ing the page and
  grepping for `https://[^"]*-preview\.mp3` finds direct, downloadable file URLs — confirmed live,
  no API key or login needed. Download a few candidates per category rather than trusting the
  first result: category pages mix genuinely single-hit sounds with multi-hit sequences (a "click"
  page can return a double-click or a 5-blip ratchet, not a single blip) and full sound-design
  clips with long reverb tails (a 4-8s "impact" when a beat needs a 1s accent).
- **Verify every download before using it** — this is the same waveform-image discipline this
  file already describes for tagging any audio asset, just applied as a real check instead of
  only a tagging aid: render each candidate with `ffmpeg -i <file> -filter_complex
  "showwavespic=s=600x120" -frames:v 1 <out>.png` and look at the shape (a whoosh should swell in
  and out, a riser should build continuously toward the end, an impact/click should be one sharp
  transient with a short decay — see this file's waveform-reading guide above), plus
  `ffmpeg -i <file> -af volumedetect -f null -` to confirm it isn't silent or clipped
  (`max_volume` near but under 0 dB, not positive). Trim with `ffmpeg -i in -t <n> -af
  "afade=t=out:st=<n-0.15>:d=0.15" out` to cut a long tail down and avoid an abrupt stop. Confirmed
  live on a real project: this caught a "click" candidate that was actually a multi-blip ratchet
  (retrimmed to isolate one blip) before it went anywhere near a real mix.
- Build the sound library from whatever the user already owns/licenses first — this workflow is
  for filling a specific gap (a beat needs a real whoosh/impact/riser and nothing suitable exists
  yet), not a default first move.

## Generated sources (`scripts/generate/`)

A fourth source alongside your own library and stock: a clip drawn by code instead of found —
kinetic typography, a chart, or a custom motion-graphic scene. Tag these with
`"source": "generated:<tool>"` (`kinetic_text` / `chart` / `html_motion`) rather than
`own_library`, so it's obvious later that the clip can be cheaply *regenerated* with different
text/data/duration instead of needing to be replaced by a found one. See
`references/code_generated_frames.md` for when to reach for this and how each generator works.
