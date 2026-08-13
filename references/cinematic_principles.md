# Cinematic principles: the judgment layer behind beat planning, critique, and design

Everything else in `references/` is mechanics — schemas, API calls, gain values. This file is
different: it's the *judgment* framework for making footage/cutaways/sound actually feel
directed rather than just correctly assembled. Read it before beat-planning a project that
matters visually (step 5 in `SKILL.md`), before critiquing an existing edit, and before designing
a video from scratch. It's a distillation of a director/cinematographer/editor/colorist/sound-
designer way of evaluating a frame — extracted as reusable principles, not a style to imitate
literally. See "Originality rule" at the end before applying any of this to a specific creator's
look.

**Two capabilities in this skill use this file without needing DaVinci Resolve at all:**
critiquing an existing video, and designing a video/storyboard from scratch (a shot list and
audio map as a planning deliverable). Both are pure judgment work — do them in any environment,
local or remote. Only *building* the result in Resolve (`SKILL.md` step 6) needs a local machine.

## The governing hierarchy

```
IDEA → EMOTION → SHOT PURPOSE → COMPOSITION → LIGHT → DEPTH → SUBJECT/ACTION
  → CAMERA MOTION → EDIT → SOUND → COLOR/TEXTURE → FINAL POLISH
```

Color grading and texture sit near the *end* of this chain, not the foundation. "Cinematic" is
not black bars, a LUT, 24fps, shallow depth of field, grain, or slow motion — those are tools
that can support a shot that's already working, and can't rescue one that isn't. If a plan starts
with "add a LUT and some transitions," that's the wrong end of the chain to start from.

## The six systems

Evaluate any shot or sequence through these six interacting systems — they're the checklist
behind both critique and design output.

### 1. Attention — where should the eye go first?
A frame can be dense without being confusing: **complexity ≠ visual confusion**. Controls:
brightness, contrast, sharpness, motion, faces, hands, color contrast, leading lines, framing,
negative space, foreground occlusion, focus, scale. When planning or critiquing a shot, name the
primary focal point, the secondary one, supporting texture, and anything actually competing with
the subject for attention.

### 2. Depth — does the frame feel dimensional or flat?
The recurring useful pattern is **foreground → subject → background**, not just a subject against
a backdrop. Foreground occlusion (something passing close to the lens, an object at the frame
edge) is not automatically a mistake — it can make the camera feel physically present in the
scene rather than a neutral observer. Depth tools: foreground objects, parallax, lens choice,
camera movement, lighting separation, haze, focus separation, scale, perspective lines.

### 3. Light — is it motivated, and does it do work?
Don't evaluate lighting only by "is the subject visible." Ask: what's the motivated source, what
direction does it come from, is the subject separated from the background, are practicals
visible, are highlights controlled, do shadows help the composition, does the lighting reinforce
the emotion. Tools: window side light, practical lamps, backlight/rim light, soft directional key,
negative fill, motivated warm/cool contrast, haze for visible beams and atmosphere.

### 4. Motion — camera, subject, and everything else that moves
Motion layers: subject movement, environment movement, camera movement, focus movement, editorial
movement between shots, graphical movement, audio movement. **Never add camera movement without a
purpose** — reveal information, raise energy, create intimacy, create scale, follow action,
transition between ideas, produce parallax, direct attention. Vocabulary: slow push-in, slow
pull-out, handheld micro-motion, whip movement, lateral slide, orbit, top-down movement, macro
tracking, foreground wipe, camera hidden behind an object before a reveal.

### 5. Rhythm — controlling attention over time
Faster cuts are not automatically better retention. Good rhythm uses **contrast**:
`FAST → FAST → FAST → PAUSE → DETAIL → BUILD → RELEASE`. A quiet shot makes the next energetic
sequence land harder. When deciding where a cut happens, the real trigger is usually that
*something changed* — movement, thought, sound, direction, scale, emotion, information — not that
an arbitrary duration elapsed. Factors: shot duration, motion intensity, information density,
speech rhythm, music phrase, sound transient, emotional state, whether the viewer needs time to
actually read the image.

### 6. Sound correspondence — sound the change of state
Not "add a sound effect to every object" — **sound the moment something changes state**: camera
accelerates → whoosh/air movement; object lands → tactile impact; pencil touches paper → detailed
scratch; door opens into a new space → mechanical foley + ambience transition; fast cut →
transient, impact, or deliberate silence; slow push-in → subtle tonal build/room pressure; object
passes close to lens → close, wide, spatial sound; wide empty frame → ambience and space; macro
shot → exaggerated tactile foley. Sound density should roughly track visual energy — high visual
energy can carry denser sound, low visual energy should get air, ambience, and silence, not the
same wall of sound at every moment. **This directly governs `beat_plan.json`'s `sfx` field** — see
`beat_plan_schema.md`, and it's why the style profiles' `sound_design.sfx_not_on_every_cut` exists.

## Shot-by-shot analysis format

Use this structure both for critiquing an existing video and for planning shots in a design
(condense it for routine beats — full detail matters most for a video's hero shots and for
critique work):

```
SHOT ID / TIME / DURATION
PURPOSE          — what this shot accomplishes
SUBJECT          — what the viewer is looking at
SHOT SIZE        — extreme wide / wide / medium / close-up / extreme close-up (macro)
ANGLE            — eye level / high / low / top-down / dutch / POV / object-mounted
LENS/PERSPECTIVE — the visual effect (compression, wideness), not a fabricated exact focal length
COMPOSITION      — centered / thirds / symmetry / asymmetry / negative space / leading lines /
                       frame-within-frame / foreground layering
DEPTH            — foreground / subject / background, described concretely
LIGHT            — direction, softness, practicals, separation, atmosphere
COLOR            — dominant palette, contrast relationship
TEXTURE          — grain, haze, reflections, motion blur
CAMERA MOTION    — direction, speed, motivation
SUBJECT MOTION   — what moves inside the frame
EDIT ENTRY/EXIT  — why we arrive at this shot, why we leave it
TRANSITION       — cut / match cut / wipe / movement transition / sound bridge
SFX / AMBIENCE / MUSIC / DIALOGUE — what's happening on each audio layer
EMOTIONAL EFFECT — what the viewer should feel
ATTENTION PATH   — where the eye looks first, second, third
WHY IT WORKS     — the actual design reason
REUSABLE PRINCIPLE — the generalized lesson, decoupled from this specific shot
```

## Storyboard sequencing patterns

Design the sequence before thinking about effects. Useful progressions — pick whichever the
content actually calls for, don't force one onto a script that doesn't fit it:

- **Scale**: `WIDE → MEDIUM → CLOSE → MACRO → WIDE PAYOFF`
- **Movement**: `STATIC → SMALL MOVEMENT → FAST MOVEMENT → IMPACT → SILENCE`
- **Information**: `QUESTION → DETAIL → PROCESS → OBSTACLE → TRANSFORMATION → RESULT`

Every shot needs a job. If two consecutive shots communicate the same information the same way,
that's a signal to cut or redesign one of them, not to add a transition between them to disguise
the redundancy.

## Transitions: priority order

Prefer transitions that emerge from scene logic over ones that exist to show off editing:

1. motivated cut (something changed)
2. movement match (camera/subject motion carries across the cut)
3. shape match (round object → round object, match cut)
4. color match
5. sound bridge (audio leads the picture into the next space)
6. foreground wipe (something crosses the lens, next shot revealed behind it)
7. camera whip
8. graphical transition
9. plugin/effect transition — last resort, not a default

A transition is good when the viewer feels continuity, surprise, or rhythm. It's bad when its only
job is to demonstrate that a transition happened.

## Audio design: six layers

1. **Dialogue/voice** — highest semantic priority when present; must stay intelligible.
2. **Production/foley** — physical actions: touch, cloth, footsteps, paper, drawing, switches,
   doors, keyboard, tools, object handling. This is what makes an action feel physically real.
3. **Ambience** — makes the environment exist beyond the frame: room tone, street, wind, café,
   office, distant traffic, computer hum.
4. **Designed motion** — whooshes, swells, reverses, tonal movement, sub drops, impacts. Use
   selectively; this is `beat_plan.json`'s `sfx` field, gated by "sound the change of state" above.
5. **Music** — supports structure, doesn't flatten the whole video into one constant emotional
   register (see "Music structure mapping" below).
6. **Silence** — an active tool, not an absence: use it for anticipation, emphasis, intimacy,
   contrast, a reveal, or an emotional reset. A video with zero silence has no dynamic range.

### Sync points — don't sync everything
Possible synchronization moments: a cut, hand movement, eye movement, an impact, the camera
stopping or accelerating, text appearing, an object reveal, a lighting change, a music beat, a
phrase change. If *every* event hits a beat, the result reads as predictable and mechanical — mix
exact sync with pre-lap (sound arrives slightly before the cut), post-lap (sound continues after),
delayed impact, silence, and asynchronous ambience.

## Music structure mapping

Don't treat a track as an unchangeable block — analyze its intro, build, phrase, percussion
entrance, drop, breakdown, emotional peak, and ending, then map story structure onto it:

| Story beat | Musical role |
|---|---|
| Hook | musical curiosity |
| Setup | controlled groove |
| Process | increasing rhythm |
| Turn/problem | reduction or tonal change |
| Payoff | strongest phrase |
| Outro | release |

Cut or restructure the music when needed to preserve this mapping — the story structure drives
the music edit, not the other way around.

## Energy curves

Retention comes from progression (information, framing, scale, motion, emotion, location, sound,
lighting, expectation evolving over time), but *constant* novelty is exhausting — use waves, not
a flat maximum. Example curve (0–10 energy scale over a sequence):

```
8 (hook) → 5 (setup) → 6 (progression) → 8 (transformation) → 3 (breath) → 9 (payoff) → 4 (resolution)
```

When planning a longer sequence, sketch an explicit curve like this rather than assuming "faster
is always better" — a style profile's `narrative_arc.beats_template` is the shape to hang a curve
on; see `style_profile_schema.md`'s `energy_curve` field for where this becomes a concrete plan.

## Hook design

A strong opening doesn't need to shout. Visual hooks that work: an unexplained beautiful image, an
impossible-looking perspective, a transformation preview, an unusual action, a macro mystery, a
striking composition, movement into frame, an emotionally interesting human moment. The target
feeling is *"I want to understand what I'm seeing / what happens next,"* not *"I was tricked into
clicking."* Positive retention mechanics generally: curiosity, visual progression, transformation,
anticipation, a satisfying reveal, contrast, escalating visual quality, a clear payoff, novelty,
emotional connection, a strong opening image, changing scale/perspective. Design comes first —
virality is a side effect of design working, not a separate objective to chase with manipulative
or misleading mechanics.

## Visual grammar table

| Visual situation | Design function | Audio tendency |
|---|---|---|
| Extreme close-up | texture, intimacy, tactile detail | detailed foley |
| Macro action | physical satisfaction | exaggerated micro-foley |
| Wide static shot | space, calm, scale | ambience |
| Fast handheld | energy, urgency | transients / rhythmic detail |
| Slow push-in | anticipation, focus | tonal build / restrained texture |
| Pull-out | reveal, isolation, resolution | widening ambience / musical release |
| Foreground wipe | depth + transition | whoosh / object foley |
| Hard cut | surprise / emphasis | transient or deliberate silence |
| Warm soft light | comfort / nostalgia | soft timbre |
| Dark contrast | mystery / tension | low texture / restrained ambience |
| Empty composition | calm / loneliness / focus | minimal sound |
| Object passes lens | physical camera presence | spatial whoosh |
| Top-down shot | graphic clarity / process | precise foley |
| Symmetrical frame | control / elegance | stable sound bed |
| Chaotic layered frame | energy / richness | selective sound hierarchy |

## Decision order (use this when improving/critiquing a video)

1. Is the idea/emotion clear?
2. Does every scene have a purpose?
3. Is the storyboard visually varied?
4. Is attention controlled?
5. Is there enough depth?
6. Is lighting intentional?
7. Is camera motion motivated?
8. Is pacing varied?
9. Are cuts motivated?
10. Does sound correspond to the image?
11. Is music structured?
12. Is color coherent?
13. Are effects necessary?
14. Can anything be removed?

Don't start a critique or a design pass with "add more transitions" — that's the last question on
this list, not the first.

## Anti-patterns

Avoid: random zooms every few seconds; constant whooshes; an impact sound on every single cut;
endless speed ramps; a transition pack as the main visual language; excessive motion blur or
grain; crushed blacks without a reason; fake cinematic letterbox bars as a substitute for actual
composition; nonstop music at one constant intensity; syncing every visual event to a beat; b-roll
that merely repeats the narration literally (illustrative b-roll should still add something — a
specific angle, a texture, a detail — not just restate the word being said); meaningless drone
shots; effects that paper over weak composition; copying a reference creator shot-for-shot;
mistaking visual density for quality; manipulative clickbait as a substitute for an actual hook;
defaulting to a bare text card on a flat background for a hook, CTA, or emphasis beat instead of
finding or building a real visual — text-on-color is the easiest option to reach for, not a style
choice, and it should lose to an actual sourced or composited visual whenever one exists (pair
generated text with motion/footage via transparent overlay compositing, or replace it outright
with a strong real clip and let captions carry the words instead). A hook beat especially: it's
the single highest-leverage 3 seconds in the video, and "bold text on black" is rarely the most
interesting thing that could be there.

## Critique output format

When critiquing an existing video/edit, respond in this order:

**A. What already works** — name the strong decisions first.
**B. Biggest visual bottleneck** — the single highest-impact change.
**C. Storyboard** — missing or redundant shots.
**D. Composition and camera** — concrete shot redesigns, not vague notes.
**E. Lighting and color** — separate production problems (fix on a reshoot) from grading problems
(fixable now).
**F. Edit and pacing** — where to cut faster, slower, or hold.
**G. Sound design** — specific foley, ambience, designed SFX, music, and silence calls.
**H. Exact improvement plan** — actionable edit instructions, not just diagnosis.

## Video design output format

When designing a video from scratch (a planning deliverable — doesn't require Resolve):

1. **Creative direction** — one concise description of the intended visual identity.
2. **Emotional goal** — what the viewer should feel.
3. **Visual rules** — 3–8 rules that keep the video coherent (this is effectively a compressed
   style profile — see `style_profile_schema.md` if the project is going into the automated
   pipeline afterward).
4. **Story structure** — hook → setup → development → turn → payoff → resolution.
5. **Shot list/storyboard** — per shot: purpose, framing, camera, action, light, transition, sound.
6. **Audio map** — dialogue + foley + ambience + designed SFX + music + silence, per the six
   layers above.
7. **Color/texture** — palette and finishing treatment.
8. **Edit rhythm** — the energy curve and shot-duration logic (see above).
9. **Motion graphics** — only when they actually earn their place.
10. **Final polish** — grain, stabilization, sound mix, subtle effects — deliberately last, per
    the governing hierarchy at the top of this file.

## Originality rule

References are a vocabulary, not a template. Extract *principles* — tactile detail, layered
foreground depth, physical camera presence, detailed foley, controlled visual density — then
adapt palette, camera behavior, typography, and pacing to this specific video's own identity,
subject, platform, and constraints. Never phrase a recommendation as "make it exactly like
[creator]." Prefer: "use the principle of layered foreground depth and tactile foley, adapted to
this video's own palette and pacing."

## Master formula

```
BEAUTIFUL FRAME → CLEAR ATTENTION → DEPTH → MOTION → MOTIVATED CUT
  → CORRESPONDING SOUND → EMOTIONAL CHANGE → PAYOFF
```

The viewer shouldn't primarily notice the editing. The viewer should feel that the video was
designed — intentional, tactile, dimensional, rhythmic, coherent, emotional, readable, original.
That's the standard this file calibrates toward, for the automated pipeline's beat-planning and
sound design just as much as for a manual critique or from-scratch design pass.
