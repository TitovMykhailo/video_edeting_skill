# Code-generated frames: drawing a shot instead of finding one

Sometimes the right visual for a beat doesn't exist as a pre-made clip anywhere — a specific
kinetic-typography reveal of a specific phrase, a chart with this project's actual numbers, or a
bespoke visual pun that would take longer to find than to draw. `scripts/generate/` covers that
case with three tiers, from zero extra setup to the full web creative-coding ecosystem. All three
output an ordinary video clip that drops into the media library and flows through the rest of the
pipeline exactly like any stock or personal clip — see "Integrating with the library" below.

## When to reach for this vs. the media library

Generate a frame when: the beat needs on-screen text/typography beyond what captions already
cover (a hero title card, a kinetic word reveal), the beat needs a chart/diagram with this
project's specific numbers, the library and stock genuinely have nothing for a `filler`/
`emotional_beat` moment and something better than nothing is worth 30 seconds of code, or a
`keyword_meme` pun is simple enough to draw (a shape, an icon, a short animated gag) and doesn't
already exist as a found clip. Don't reach for it when a real clip already fits — a genuinely
tactile, textured, or funny found clip almost always beats a generated one for `illustrative` and
`emotional_beat` intents (see `references/cinematic_principles.md`'s tactility guidance); code-
generated frames are strongest for typography, data, and abstract/graphic content, not for
standing in for photographed/filmed reality.

## The three tiers

### Tier 1 — `kinetic_text.py` (Pillow + ffmpeg, no other setup)

A word or short phrase animates in (pop-in with a slight overshoot, or a plain fade) and holds.
Supports per-word accent-color highlighting (matching a style profile's `color.accent_hex` and
the `captions.style_notes` "occasional accent word" pattern) and an optional alpha channel for
compositing as an overlay rather than a full-frame replacement.

```bash
python3 scripts/generate/kinetic_text.py --text "SELF EDUCATE" \
    --out out/generated/self_educate.mp4 --duration 1.4 --width 1920 --height 1080 \
    --bg "#0A0A0A" --fg "#FFFFFF" --accent "#E0212B" --accent-words "EDUCATE"
```

This is the default choice for a `kinetic_typography` beat — reach for the other two tiers only
when this one genuinely can't do what's needed (real data, or motion Pillow can't express).

### Tier 2 — `chart.py` (matplotlib, headless)

An animated bar or line chart — bars grow in, a line progressively draws itself — with fixed axis
limits throughout so nothing jitters or rescales frame to frame. This is what a `diagram_evidence`
beat should reach for whenever the script actually states numbers worth showing on screen instead
of just saying them.

```bash
python3 scripts/generate/chart.py --type bar \
    --data '{"Reading":10,"Doing":25,"Teaching":90}' --title "Retention by method" \
    --out out/generated/retention.mp4 --duration 3.0 --bg "#0A0A0A" --fg "#FFFFFF" --accent "#E0212B"
```

Pass `--static` for a beat too short to justify the animate-in (just hold the finished chart).

### Tier 3 — `render_html_motion.py` (Playwright + headless Chromium, optional/heavier)

Renders arbitrary HTML/CSS/JS to a frame sequence via headless Chromium, frame-accurately (not by
recording real-time playback — see the contract below). This is the general-purpose tier: anything
the web's creative-coding ecosystem can draw becomes usable footage. Reach for it when Tier 1/2
can't express the motion needed — particle effects, physics-ish motion, SVG path morphing, a
Lottie/After-Effects export, a d3 data-driven diagram more complex than a bar/line chart, or
anything genuinely custom.

**Well-known libraries this tier unlocks** (load them from a local copy or a CDN `<script>` tag —
CDN loading needs network access at render time, so prefer a local copy for reliability):

| Library | Good for |
|---|---|
| [p5.js](https://p5js.org/) | Generative/creative-coding visuals, particle systems, abstract motion — strong fit for `filler`/`abstract-motion` |
| [GSAP](https://gsap.com/) | Precise, professional-feeling motion tweening/timelines; `.seek(t)` maps directly onto this tier's contract |
| [anime.js](https://animejs.com/) | Lightweight tweening, similar use case to GSAP |
| [D3.js](https://d3js.org/) | Data-driven diagrams beyond what `chart.py`'s bar/line covers (networks, hierarchies, custom shapes driven by real data) |
| [Lottie / lottie-web](https://airbnb.io/lottie/) | Playing back After Effects exports — useful if the user (or a designer) already has `.json` Lottie assets |
| Plain Canvas/SVG/CSS | No dependency at all — see the example template, often enough on its own |

The **required contract**, demonstrated in `assets/generated-templates/example_scene.html`:

1. `window.seekTo(t)` — draws the scene's exact state at `t` seconds. Must be deterministic
   (frames are captured out of real time by calling this repeatedly with increasing `t`, not by
   recording playback). A GSAP timeline exposes `.seek(t)` natively; p5.js needs `noLoop()` +
   calling your draw logic manually inside `seekTo`; D3 transitions need to be driven by `t`
   instead of their own internal clock.
2. `window.sceneReady` — set `true` once anything async (a font, a fetched Lottie JSON, an image)
   has finished loading; the renderer waits for it before capturing. Fine to set `true`
   immediately for a scene with nothing to await.
3. A transparent `<body>` if the scene will ever render with `--transparent`.
4. (optional) Read `?transparent=1` from `location.search` if the scene wants to paint its own
   opaque background by default and skip that fill only when actually compositing as an overlay
   — see the example template for the pattern.

```bash
python3 scripts/generate/render_html_motion.py --html path/to/scene.html \
    --out out/generated/scene.mp4 --duration 3.0 --width 1920 --height 1080
```

Setup this tier needs that the other two don't: `pip3 install playwright && playwright install
chromium`. That's a real, if one-time, cost — don't reach for this tier by default, only when
Tier 1/2 genuinely can't do the job.

## Alpha / overlay compositing

All three generators can output with a transparent alpha channel (`--transparent`, writing a
`.mov` via the QuickTime Animation codec instead of an opaque `.mp4`) instead of a full-frame
opaque clip. Use this when a generated element should sit *on top of* other footage — a kinetic
word popping in over a b-roll clip, a small chart in the corner of a talking-head shot — rather
than replacing the frame outright. An overlay clip like this goes on a video track *above* the
beat's main clip in the Resolve timeline; `scripts/resolve/build_project.py` doesn't currently
place multi-track overlays automatically (it builds one video track per the beat plan), so
compositing an overlay is a manual step in Resolve for now — mention this to the user rather than
silently doing a full-frame replacement when they actually wanted an overlay.

## Integrating with the media library

A generated clip is just another file — feed it through the same cycle as everything else instead
of special-casing it in `beat_plan.json`:

1. Save it into the media library (e.g. `<media_library_path>/_generated/<tool>/`).
2. Run `scripts/index_media.py scan` — it'll show up like any new file.
3. Tag it via `write-tags` with `"source": "generated:kinetic_text"` (or `generated:chart` /
   `generated:html_motion`) instead of `"own_library"` or `"stock:*"` — see
   `references/media_tagging_schema.md`. Knowing a clip was generated (vs. found) matters later if
   the user wants to regenerate it with different text/data/duration rather than re-tag a stock
   replacement.
4. From here it's indistinguishable from any other library clip in `query` and in `beat_plan.json`
   — no changes needed to the Resolve build step.

This also means a generated clip can be *regenerated* cheaply — if a chart's numbers change or a
kinetic-text clip's wording needs a tweak, rerun the same generator command with new arguments and
re-tag, rather than treating it as a one-off asset to hand-edit.
