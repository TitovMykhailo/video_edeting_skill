# Editor discipline: from Creative Director to Video Editor

`cinematic_principles.md` is the *why* — the six systems, the master formula. This file is the
*how a real editor actually works* — the discipline that turns a beautiful treatment into
something frame-accurate, technically honest, and machine-executable. Read this before any beat
plan that will actually be built (not just pitched), and re-read Part 8 (the critique loop) after
every render.

**The core failure mode this file exists to prevent:** writing confident-sounding technical
numbers — "4-frame glitch," "VO leads picture by 0.3s" — that *sound* professional but aren't
derived from anything real. A Creative Director can get away with that in a pitch deck. A Video
Editor cannot, because someone is about to cut frame-accurate media against those numbers. If a
number in a beat plan didn't come from real word timestamps, phoneme boundaries, or a measured
BPM/beat grid, it is not a real number yet — it's a placeholder, and it must be labeled one.

## 1. Timing: provisional vs. audio-derived — never blur the two

Every beat plan has one of two timing bases, and it must say which:

- **`timing_basis: "audio_derived"`** — every `start`/`end`/anticipation-window number comes from
  real data: `transcript.json`'s word timestamps (and, where available, phoneme boundaries,
  breaths, pause lengths, pitch/energy peaks from the actual recording) or a real measured music
  BPM/beat grid. This is the only basis frame-accurate numbers like "text appears 180ms before the
  stressed syllable" are allowed to use.
- **`timing_basis: "provisional"`** — no real narration audio exists yet. Durations are *estimates*
  (word count ÷ a reasonable words-per-second for the style, or straightforward guesses), and every
  number derived from them must be presented as provisional, not as if it were measured. Don't
  invent frame counts or millisecond offsets in this mode — "the text appears roughly on the
  stressed word" is honest; "text appears at frame 47" is not, if there's no real frame 47 yet.

Run `scripts/validate_timeline.py` before treating either kind of beat plan as final — see
`beat_plan_schema.md`'s "Timing validation" section. Timing basis being provisional doesn't excuse
gaps/overlaps/missing coverage; it only limits how precise the individual numbers are allowed to
claim to be.

## 2. Attention: model where the eye actually is

For every shot, name a **primary eye target** and, if relevant, a **secondary** one, as normalized
coordinates (`x`, `y`, both 0–1, origin top-left). This isn't decoration — it's what lets you
decide on purpose whether the next cut continues the eye's position (continuity) or breaks it
(interruption), instead of that happening by accident.

```
shot A primary eye target: x=.72 y=.40   (a face, right-of-center)
shot B primary eye target: x=.70 y=.43   (near-identical → continuity, calm cut)
```

vs.

```
shot A primary eye target: x=.80 y=.50
shot B primary eye target: x=.20 y=.50   (far apart → deliberate pattern interruption)
```

Ground the target in what actually pulls a real eye: faces, motion, brightness, contrast, text,
scale, color, depth, leading lines. Before every cut, ask "where is the eye right now, and where
should it land after this cut" — and make the answer a decision, not a guess made after the fact.

## 3. Motion continuity

Track not just what's in a frame but how it's *moving*: direction, velocity, camera movement,
subject movement, screen position. A subject exiting frame-right into the cut can either continue
moving right in the next shot (continuity — feels like one continuous motion crossing the cut) or
reverse into left-to-right-become-right-to-left (collision/interruption — feels like a conflict or
a hard stop). Both are legitimate; the difference is whether it's a choice. Don't just label a cut
"match cut" — say what perceptual function the matched or broken motion is performing.

## 4. Editing rhythm follows speech structure, not sentence boundaries

Tag narration by rhetorical function, not just grammar: **setup / build / emphasis / punchline /
pause / reveal / question / answer**. The image doesn't have to change on every sentence — it can
change *before* a word (anticipation: the brain registers the change, then the word confirms it,
120–300ms lead **only when real word timestamps back that number** — see Part 1), *on* a word
(sync), *after* a word (delayed, for a punchline effect), or not at all (letting a static image sit
through a whole clause on purpose). Which one to use is itself a storytelling decision — say which
you picked and why, not just "cut here."

## 5. Humor engine

A short reaction-meme habit is not a humor strategy. Use these, deliberately, by name:

- **A. Expectation → violation.** Build a real expectation, then break it with a *consciously
  chosen* absurd payoff — the more serious the setup, the harder a genuinely silly payoff can land.
- **B. Rule of three.** A, A, B — the first instance sets the rule, the second confirms it, the
  third breaks or intensifies it. The timing has to sell it too: a third beat that's noticeably
  *faster* than the first two (not just a third similar-length shot) is what makes it read as a
  punchline instead of a third example.
- **C. Editorial deadpan.** Say something absurd, then let the edit not react at all — hold a
  completely serious shot. Often funnier than a reaction cut or a sting.
- **D. Overreaction.** A tiny event gets a disproportionately large audiovisual build-up. Use
  rarely — it only works because it's rare.
- **E. Underreaction.** A gigantic claim gets a small, quiet, unimpressed treatment. Often funnier
  than the big version of the same beat.
- **F. Visual contradiction.** The voice says one thing, the image quietly disagrees — irony
  through the gap between the two channels, not through either one alone.
- **G. Callback joke.** A joke planted early returns later in a new form, unexplained. If you have
  to point it out, it's not a callback, it's exposition.
- **H. Micro-jokes / easter eggs.** Small details that reward a close/repeat viewing — a fake
  filename, a background label, a joke result in a mocked-up UI — that never carry primary
  information, so missing them costs nothing on a first watch.

## 6. "Unnecessary" shots can be necessary — flavor shots

Not every shot has to add new information. A shot's job can legitimately be personality, humor,
texture, beauty, breathing room, anticipation, or emotional reset — call these **flavor shots**.
The old test ("if removed, does information disappear?") is too weak; use instead: **"if removed,
does the experience get worse?"** A hand slowly closing an old laptop after a punchline can pass
that test even though the story loses nothing on paper without it.

## 7. Visual beauty engine

For every hero shot specifically (not every shot — see Part 9), evaluate: composition, balance,
negative space, foreground/midground/background separation, lighting direction and contrast, color
harmony, texture, subject separation, implied lens feel, camera height, perspective, movement,
simplicity. But don't make every shot beautiful the same way — beauty needs contrast against
functional, ugly-on-purpose, minimal, dense, and funny shots to still register as beauty. A reel
that's uniformly gorgeous stops feeling like anything at all.

## 8. Text is a visual object, not a subtitle track

For every text event, first ask **why text at all** — if the image already delivers the
information, text is often redundant illustration, not reinforcement. When text *is* the right
call, it's a full design decision: size, position, weight, font role, line breaks, tracking, case,
color, depth, entrance, exit, duration, and relationship to the voice (before/on/after — see
Part 4). Text can also physically interact with the world instead of floating as an overlay:
tucked behind a foreground object, attached to a surface, following the camera, sized to literally
occupy the percentage it's naming (a "70%" that fills 70% of the frame rather than sitting centered
at any size), masked, given depth. Meaning becomes design.

### Size hierarchy — don't make every emphasized word huge
- **Level 1 (small)** — supporting information.
- **Level 2 (medium)** — an important keyword.
- **Level 3 (large)** — a major statement.
- **Level 4 (hero, near-full-screen)** — reserved, rare, and only for the moment that's actually
  earned it. If everything is Level 4, nothing is.

### Entrance style — pick deliberately, not by default
Whole-word, syllable-by-syllable, letter-by-letter, line-by-line, or all-at-once — each implies a
different relationship to the voice. Letter-by-letter needs real reading time; don't use it under
fast narration, it will always lose that race.

### Timing category
- **Pre-emptive** — appears slightly before the VO reaches it (anticipation).
- **Sync** — lands exactly on the stressed syllable.
- **Delayed** — appears after the word, for a punchline/reveal effect.
- **Build** — constructs itself across the whole phrase.
- **Reveal** — full meaning only completes at the sentence's end.

## 9. Information density budget

Rate every moment low/medium/high. Never stack fast narration + complex b-roll + animated text +
a chart + camera movement + loud SFX simultaneously — a viewer can't process all of it at once, and
something in that stack is being wasted. When narration is dense, simplify the image. When
narration is simple, the image has room to get more complex. Think of it as a fixed attention
budget being spent every second, not a checklist of things to include.

## 10. Sound is not decoration — it's an equal layer

For every audiovisual event, decide deliberately: what should the viewer *hear* before they *see*
it (a J-cut/pre-lap creates anticipation), and what should they *see* before they *hear* it
(delayed sound can be its own kind of punchline). SFX should not automatically accompany every
animation — often, an animation *without* a sound effect reads as more expensive, not less. Mix in
layers, always in this priority: **voice** (always the dominant, always-intelligible layer) >
**foreground** (the SFX that matters this second) > **midground** (music) > **background**
(ambience/texture). If real audio is available for mixing, that means actually reasoning about
LUFS/peak level, spectral masking between voice and music, stereo width, and ducking — not just
"turn the music down a bit."

## 11. Music has memory

Don't pick a fresh, unrelated track per section. Build (or select) music that can carry a **theme**
across the whole piece — instrumentation callbacks, harmonic callbacks, rhythmic callbacks — so
that when a visual callback returns, the music can return with it and the two reinforce each other
instead of the audio accidentally undercutting a visual payoff with unrelated material.

## 12. Pattern → pattern → break, and novelty control

Pattern interruption only works if a pattern existed first and had time to register — two
repetitions minimum before a break reads as a break rather than noise. This applies to shot
duration, camera movement, music, color, text, sound, and composition, not just imagery.

Rate every shot's **novelty 1–10** relative to what came just before it. Don't hold 9–10 constantly
— a viewer adapts to sustained novelty and stops experiencing it as novel. A contour like
`6 5 5 8 4 4 9 3` reads as a sequence of *events*; a flat `9 9 9 9 9 9` reads as noise.

## 13. Hero moments: density, not just quality

Aim for roughly **one hero moment per 30–60 seconds** of a fast-paced short-form piece (adjust for
format/genre). Everything else exists partly to make those moments land harder. Before a hero
moment, consider deliberately *reducing* movement, music density, brightness, information density,
and cut frequency — perceptual headroom, not padding, is what makes the hero moment read as a
step up rather than more of the same.

## 14. Visual metaphor before literal footage — but not always

Before reaching for the obvious illustration, ask: can the *meaning* be shown instead of the
object? "Google dominated search" doesn't require the Google logo — negative space consuming a
cluttered competitor's layout can show domination directly. But don't force a metaphor onto every
line; sometimes the literal shot is simply the better shot, and metaphor used everywhere stops
reading as metaphor and starts reading as a tic.

## 15. Know when to be stupid — and keep meme language on a short leash

Sometimes the technically elegant choice is worse than a deliberately dumb one — a rubber duck, a
cheap-looking freeze-frame, a comically small logo, an intentionally bad chart. Permission to use
these is part of having taste, not a lapse in it — the skill is knowing exactly when the "stupid"
choice is the right one. Reaction-meme/found-clip humor specifically should stay rare and pass all
four checks: it genuinely strengthens the punchline, it reads without requiring the viewer to know
the specific meme, it doesn't damage the video's own visual identity, and it isn't the *default*
humor tool reached for every time — build original audiovisual humor (Part 5) first.

## 16. Build a visual grammar per video — and name its exceptions up front

Before any shot list: write the video's own rules explicitly (camera stays controlled; accent color
= X; hero numbers get color Y; historical material is warmer/rougher; modern material is cleaner;
an elevated POV signals danger; the first visual instability is reserved for moment Z). Then also
write **rule-break conditions** — exactly when each rule is allowed to break, and why that specific
moment earns it. A rule that's never allowed to break becomes a template; a rule broken without
a stated reason isn't a rule at all.

## 17. Design for rewatchability

Layer a second pass of information under the first: on a first watch the story is completely
legible; on a second, a viewer starts noticing callbacks, compositional rhymes, and background
jokes (see Part 5's easter eggs). Plant these without pointing at them — an object that reappears
transformed 90 seconds later rewards attention precisely because nothing calls it out.

## 18. Transitions across meaning, not just across pixels

The best transition isn't always visual. Consider semantic transitions (a concept bridges two
ideas), audio transitions (a sound bridges two spaces), motion transitions (movement direction
carries across the cut), color transitions, shape transitions (round object → globe), and
conceptual transitions (a typing cursor → a blinking city light; a phone grid → a server rack).
Look for what the *last* visual element of one idea and the *first* visual element of the next
idea actually share, and cut on that.

## 19. Every cut needs a stated function

Before a cut exists, name its job: information, energy, comedy, emotion, continuity, surprise,
relief, beauty, or orientation. If none of those apply, the cut probably shouldn't exist.

## 20. Breathing room — compression and release

Retention isn't the absence of pauses. A good pace alternates compression (density, speed) and
release (held shots, silence, ambient stillness, negative space, slow movement) — fast sections
only read as fast *because* slow sections exist to contrast against. Constant intensity flattens
into a single, forgettable texture.

## 21. Real asset selection is a real skill

When actual candidate footage exists, evaluate each candidate on semantic relevance, composition,
motion, quality, emotional register, lighting, color, likely eye target, available duration, and
uniqueness — then choose the best one. If nothing available is truly right, **adapt the edit to
the footage that exists** rather than describing an ideal shot that isn't real and pretending a
mediocre substitute is that ideal shot. Reality drives the treatment; the treatment doesn't get to
override reality.

## 22. Generated footage is a deliberate choice, not a default

Reach for `scripts/generate/` (see `code_generated_frames.md`) specifically when: no reasonable
footage search will find what's needed, the beat calls for a visual metaphor no stock library
will have, a custom transition asset is required, an impossible camera/shot is needed, or a
generated look is itself part of the intended art direction. Don't generate a frame just because
it's possible — real archival material and real photography usually carry more visual truth than a
generated stand-in, and should win by default when both are viable.

## 23. Try multiple candidates for moments that matter

For a genuinely important beat, don't lock the first idea. Sketch at least: **A — restrained**,
**B — aggressive**, **C — unconventional.** For "Google got scared," that might be (A) the logo
plus a subtle value shift, (B) a real multi-frame visual glitch, (C) no Google visual at all —
just the music suddenly cutting to nothing. Compare against the whole video's context before
picking — this is what makes the process resemble an actual editor's *try → watch → compare →
choose* loop instead of committing to the first idea that came to mind.

## 24. The critique loop — a render must actually be watched

A timeline description is not a finished edit. After a real render exists, watch it and hunt
specifically for: boring stretches, visual overload, awkward cuts, bad eye travel, unreadable text,
music masking the voice, SFX fatigue, repetitive transitions, hero moments that didn't earn their
build-up, jokes that land flat, and timing that feels mechanical rather than felt. Then re-edit.
Repeat. Four focused critique passes are worth running by name, one after another, not folded into
a single vague "does this look good":

- **Humor critic** — setup clarity, surprise, timing, originality, character consistency,
  distraction risk. A joke that needs explaining has already failed.
- **Text critic** — did the viewer have time to read it; does it compete with a face/subject for
  attention; is there too much of it; does size match importance; does emphasis land on the actual
  stressed moment; is the text even necessary at all — checked against the real rendered frame, not
  the spec.
- **Beauty critic** — not "is this technically correct" but "would I want to pause on this frame."
  Score hero shots on frame beauty, composition, depth, light, color, clarity, originality — but
  don't chase 100 on every score; contrast across shots matters more than a uniformly high average
  (see Part 7).
- **Video critic (general)** — the full checklist above, applied to the whole piece.

## 25. Retention engines, not just cut speed

"More cuts" is not a retention strategy on its own. Name, per section, what's actually earning the
next 5–10 seconds of attention: a question, anticipation, an unfinished action, an information gap,
emotion, beauty, humor, surprise, stakes, scale, a pattern, or a story promise made earlier. If a
section's only retention engine is "it's fast," that's worth flagging as a weakness, not treating
as sufficient.

## 26. Payoff accounting

Track every setup explicitly: **setup → expected payoff → actual payoff timestamp.** A mystery that
never resolves is a bug, not intrigue. Build this as a real table for any video with more than a
couple of running threads (a teased element, a planted callback, an open question) so nothing gets
silently dropped between the treatment and the final cut.

## 27. Confidence, honestly stated

For creative decisions — humor, music choice, an unusual transition, a long hold, complex text
animation — state a confidence score 0–100 instead of presenting every choice with uniform
certainty:

- **82+** — use directly.
- **60–81** — flag for a render check before committing.
- **below 60** — don't ship it as the only option; build an alternative (see Part 23's A/B/C).

Taste can't be fully resolved by logic alone; a stated confidence score is the honest way to admit
that without pretending every call is equally solid.

## 28. Editorial personality, declared before the shot list

Before beat-planning, define: humor register (dry / absurd / sarcastic / playful / none), energy
(calm / dynamic / chaotic), visual personality (clean / tactile / imperfect / graphic / cinematic),
and the narrator's implied relationship to the audience (serious expert / curious friend /
mischievous storyteller / investigative narrator). Every subsequent decision should be checkable
against this declaration — it's what keeps 70 individually-reasonable shot decisions from adding up
to something with no coherent voice.

## 29. Allow imperfection

A perfectly smooth, perfectly symmetrical, perfectly timed edit reads as artificial. Slightly long
holds, an unexpected cut, asymmetric composition, an awkward comedic pause, visible archive
texture/grain — these are allowed to survive rather than being sanded down in the name of
mathematical cleanliness. Human editing has a pulse; over-optimizing removes it.

## 30. Two-layer output — don't mix philosophy with execution

Every deliverable should separate:

- **Layer A — creative intent** (short): what the viewer should feel, why this sequence exists,
  what visual idea drives it. A sentence or two, not a paragraph.
- **Layer B — execution** (precise): source asset, in/out points, crop, scale, position, motion,
  text and its timing, transition, music, SFX, mix notes, eye target.

Don't let 500 words of philosophy stand in for one concrete edit instruction, and don't strip all
the reasoning out of a shot list either — an executor needs both, clearly separated, not blended.

## 31. Machine-readable shot fields

Every shot should be expressible as structured data an executor (human or automated) can act on
without re-deriving intent. See `beat_plan_schema.md` for the concrete JSON shape this maps onto —
`shot_id`, voice range, start/end, asset + in/out, crop/scale/position, motion, primary/secondary
eye target, text spec (content, animation, start/end), music/SFX references, transition, cut
function, novelty score, purpose, and confidence. The goal is that this data is specific enough to
eventually drive a real Premiere/Resolve/ffmpeg timeline, not just describe one in prose.

## 32. The final question for every decision

Not just "is this professional" — ask **why is this here, why now, why this long, why this size,
why this position, why this sound, why this cut, why this image, why not nothing.** If there's no
good answer, try removing it. But remember that "it makes the moment funnier," "it makes the frame
beautiful," "it gives the viewer a breath," and "it establishes personality" are all completely
valid answers — editing exists to create an *experience*, not only to transmit information.

## The full quality loop

```
SCRIPT → STORY ANALYSIS → VOICE ANALYSIS → ASSET ANALYSIS → CREATIVE PLAN → CANDIDATE EDITS
  → TIMELINE → RENDER → WATCH → CRITIQUE → RE-EDIT → RENDER → FINAL CRITIQUE
```

The first pass through a timeline is a draft, not an answer — assume it needs at least one real
critique-and-revise cycle (Part 24) once a render actually exists to watch.
