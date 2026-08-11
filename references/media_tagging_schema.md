# Media library tagging schema

The media library is one folder the user reuses across projects (their own collected clips, plus
a `_stock_cache/` subfolder this skill manages for downloaded stock). `scripts/index_media.py`
keeps a single index file at the library root: `_media_index.json`. You never edit that file by
hand — `scan` reads it, `write-tags` writes it, `query` reads it.

## `_media_index.json` shape

```jsonc
{
  "files": {
    "relative/path/clip.mp4": {
      "hash": "size:1234567,mtime:1733939200",   // cheap change-detector, not a real content hash
      "probe": {
        "duration_s": 4.2,
        "width": 1920,
        "height": 1080,
        "orientation": "landscape",               // "landscape" | "portrait" | "square"
        "codec": "h264",
        "kind": "video"                                // "video" | "image"
      },
      "tags": ["cooking", "kitchen", "chopping", "sitcom"],
      "description": "Two people chopping vegetables on a busy restaurant line, quick cuts, loud kitchen energy.",
      "mood": "chaotic-energetic",
      "quality_ok": true,
      "quality_notes": "",
      "source": "own_library",                         // "own_library" | "stock:pexels" | "stock:pixabay" | "stock:giphy"
      "tagged_at": "2026-08-11T12:00:00Z"
    }
  }
}
```

## Tagging guidance (for the `write-tags` step — this is on you, not a script)

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

## `query` output shape

```jsonc
{
  "results": [
    {
      "path": "relative/path/clip.mp4",
      "score": 3.4,
      "reasons": ["tag match: cooking", "tag match: kitchen", "mood match: chaotic-energetic"],
      "probe": { "...": "as above" },
      "tags": ["..."],
      "description": "..."
    }
  ]
}
```

`score` is a simple heuristic (tag/keyword overlap + mood bonus − recency penalty) meant to
shortlist candidates, not to pick for you — always read `description`/`tags` on the shortlist and
choose with judgment, same as a human editor scanning a bin.

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
