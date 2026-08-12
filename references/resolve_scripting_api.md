# DaVinci Resolve scripting API — setup and cheat sheet

Resolve ships its own scripting manual (`README.txt` / `README.md`) alongside the API at the
path below for the version actually installed on this machine — if anything here doesn't match
what you observe (Blackmagic does change signatures between versions), that shipped file is the
authoritative source, not this doc. Read it before guessing at an unfamiliar call.

## One-time setup (do this before step 1 of anything)

1. In Resolve: **Preferences → General → External scripting using → Local**. Restart Resolve
   after changing this.
2. Set environment variables so Python can find the API module. Defaults per OS:

   **macOS**
   ```bash
   export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
   export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
   export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
   ```

   **Windows** (PowerShell)
   ```powershell
   $env:RESOLVE_SCRIPT_API = "$env:PROGRAMDATA\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
   $env:RESOLVE_SCRIPT_LIB = "C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
   $env:PYTHONPATH = "$env:PYTHONPATH;$env:RESOLVE_SCRIPT_API\Modules\"
   ```

   **Linux**
   ```bash
   export RESOLVE_SCRIPT_API="/opt/resolve/Developer/Scripting"
   export RESOLVE_SCRIPT_LIB="/opt/resolve/libs/Fusion/fusionscript.so"
   export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
   ```
   (Some Linux installs use `/home/resolve/Developer/Scripting` instead of `/opt/resolve/...` —
   `check_environment.py` tries both.)

3. Resolve must be **running** (any project open or the project manager screen) before any script
   connects — `scripts/resolve/connect.py` fails fast with a clear message if it isn't.
4. **Free edition cannot use `build_project.py` at all — this isn't a settings problem, don't
   spend time chasing one.** As of Resolve 19.1 (Nov 2024), Blackmagic made the *external*
   scripting interface (an outside process calling `scriptapp("Resolve")`, which is what every
   `resolve/*.py` module here does) Studio-only. Confirmed empirically against a real Resolve 21
   Free install for this skill: env vars correct, DLL loads without error, a project open, same
   Windows session, the scripting TCP port reachable — `scriptapp("Resolve")` still returns
   `None`, always. No preference toggle re-enables it; the old "External scripting using: Local"
   dropdown some guides mention has been removed from Free's Preferences UI entirely (it's not
   hidden, not renamed to something else — it isn't there). The *internal* Console (Workspace
   menu → Console, F6, language dropdown → Py3) still works fine on Free, because that runs
   inside Resolve's own process rather than connecting from outside — it's just useless for this
   skill's scripts, which by design run as an external Python process.

   **If you're on Free: use `scripts/resolve/build_otio.py` instead of `build_project.py`.** It
   writes a `.otio` (OpenTimelineIO) file from the same `edit_plan.json`/`beat_plan.json`, which
   Resolve imports as a normal file via File → Import Timeline → OpenTimelineIO — not gated by
   the scripting restriction because it isn't scripting. It also writes a
   `<output>.manual_steps.md` next to the `.otio` file listing everything that doesn't survive
   the OTIO round-trip (clip gain levels, the CDL color grade, captions import) so you can finish
   those by hand in a few minutes. See references/beat_plan_schema.md's "Free-edition OTIO path"
   section.

   If you're on Studio, none of this applies — `build_project.py` works as documented below.

## Connecting (the boilerplate every `resolve/*.py` module shares)

```python
import sys, os

def get_resolve():
    api_path = os.environ.get("RESOLVE_SCRIPT_API")
    if api_path:
        sys.path.append(os.path.join(api_path, "Modules"))
    import DaVinciResolveScript as dvr_script  # noqa: E402
    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError("Could not connect to DaVinci Resolve — is it running?")
    return resolve
```

## Core objects and calls used by this skill

```
resolve.GetProjectManager()
projectManager.CreateProject(name) / LoadProject(name) / GetCurrentProject()
project.GetMediaPool()
project.SetSetting("timelineResolutionWidth", str(width))
project.SetSetting("timelineResolutionHeight", str(height))
project.SetSetting("timelineFrameRate", str(fps))
mediaPool.GetRootFolder()
mediaPool.AddSubFolder(parentFolder, name)
mediaPool.SetCurrentFolder(folder)
mediaPool.ImportMedia([absolute file paths]) -> list[MediaPoolItem]   # order not documented as
                                                                            # matching the input list — match
                                                                            # returned items back to paths by
                                                                            # GetClipProperty("File Path"),
                                                                            # not by position (see import_into_bin)
mediaPool.CreateEmptyTimeline(name) -> Timeline
mediaPool.AppendToTimeline([clipInfo, ...]) -> list[TimelineItem]
timeline.GetTrackCount("audio") -> int
timeline.AddTrack("audio") -> bool
mediaPoolItem.GetClipProperty("Frames") -> str/int   # total clip length, used for looping SFX/music —
                                                            # this is a MediaPoolItem call (the object
                                                            # ImportMedia/the import cache returns), not
                                                            # a TimelineItem one
```

This skill uses three audio tracks by convention — 1 = narration, 2 = SFX, 3 = music bed —
created up front via `timeline_build.ensure_audio_tracks(timeline, 3)`, which calls `AddTrack`
until `GetTrackCount` reaches the target. Keeping them on fixed track numbers makes the project
easy to read by eye afterward in the Edit page, not just correct.

`clipInfo` dicts for `AppendToTimeline` are how both the audio track (sequential, trimmed
segments) and the video track (explicit positions, since beats have gaps/overlaps to manage) get
built:

```python
{
    "mediaPoolItem": item,       # from ImportMedia
    "startFrame": int,             # in-point into the SOURCE clip, in frames
    "endFrame": int,                 # out-point into the SOURCE clip, in frames
    "trackIndex": 1,                  # 1-based
    "recordFrame": int,             # where on the TIMELINE this lands, in frames — omit to
                                        # append sequentially after whatever's already there
    "mediaType": 1,                   # 1 = video, 2 = audio — every clipInfo dict this skill
                                        # builds sets this explicitly, see timeline_build.py /
                                        # audio_design.py
}
```

Convert seconds → frames with the project fps from the style profile (`round(seconds * fps)`);
Resolve's API is frame-indexed throughout, there's no seconds-native call.

## Subtitles (Tier 1 captions — default)

```python
timeline.ImportIntoTimeline(srt_path, {
    "autoImportSourceClipsIntoMediaPool": False,
    "importSourceClips": False,
})
```
This creates a subtitle track from the SRT. Set the subtitle track's look once, by hand, in the
Edit page (Subtitles panel → style) the first time the user runs this — Resolve remembers a
track's style, so this is a one-time setup, not a per-project chore. Document whatever style the
user lands on in their style profile's `captions.style_notes` for reference.

## Word-pop animated captions (Tier 2 — optional upgrade, more setup)

The reference style the user wants (punchy word-by-word text) needs individual Fusion `Text+`
generators per caption chunk, not a subtitle track — Resolve's subtitle styling API doesn't expose
per-word keyframed reveal. The standard technique:

1. In Resolve, build one `Text+` title by hand with the exact look wanted (font, color, outline,
   a keyframed pop-in), save it into the **Titles** bin as a template (e.g. named `AutoCaption`).
2. Per caption chunk, duplicate that template onto the timeline at the right position, then reach
   into its Fusion composition to set the text:
   ```python
   item = mediaPool.AppendToTimeline([{ "mediaPoolItem": auto_caption_template, ... }])[0]
   comp = item.GetFusionCompByIndex(1)
   tool = comp.FindToolByID("TextPlus") or comp.GetToolList(False, "TextPlus").values()
   tool.StyledText = caption_text
   ```
   Exact traversal (`FindToolByID` vs `GetToolList`) varies by Resolve version — check the tool
   name Resolve actually gives the node (visible in the Fusion page) before scripting this.
3. This is meaningfully more fragile than Tier 1 and depends on a template the user builds by
   hand once. Only reach for it once Tier 1 captions are working end-to-end and the user
   specifically wants the word-pop look — don't attempt it on a first run.

## Color grading (CDL)

```python
timelineItem.SetCDL({
    "NodeIndex": "1",
    "Slope": "1.0 1.0 1.0",       # per-channel R G B, space-separated string, not a list
    "Offset": "0.0 0.0 0.0",
    "Power": "1.05 1.05 1.05",
    "Saturation": "0.92",
})
```

`scripts/resolve/color_grade.py` wraps this — it converts a style profile's `color.grade_cdl`
(plain JSON number lists, see `references/style_profile_schema.md`) into the space-separated
string format `SetCDL` expects, applies it to every video clip on the timeline, and warns (rather
than aborting the build) for any clip where `SetCDL` returns falsy. `NodeIndex` targets which
color node the CDL lands on — `"1"` (the first/only node) is enough for the primary-correction
style push this skill does; a clip that needs more than that is a case for manual grading, not
more scripting.

For a fully custom look instead of a CDL push, `timelineItem.SetLUT(nodeIndex, lutPath)` applies a
.cube LUT file, and `timelineItem.ApplyGradeFromDRX(path, gradeMode)` applies a saved DaVinci grade
(.drx) — both are reasonable upgrades once a project has a locked-in look worth saving, but neither
is exercised by this skill's scripts by default.

## Per-clip audio gain (music bed ducking, SFX levels)

```python
timelineItem.SetProperty("Volume", gain_db)
```

`scripts/resolve/audio_design.py` uses this to set the music bed's level under narration vs. in
narration-free stretches, and each SFX cue's individual gain. **This property name is the least
certain call in this whole skill** — Resolve's scripting API doesn't consistently document
per-clip gain control across versions, and `audio_design.py` already wraps every call in a
try/except that prints a clear warning instead of failing the build if it doesn't stick. If you
see that warning, the fallback is genuinely simple: open the Fairlight page and set the levels by
ear for the flagged clips — it's a few clicks, not a blocker, and worth doing once by hand rather
than fighting the scripting API for it.

## Rendering

```python
project.SetRenderSettings({"SelectAllFrames": True, "TargetDir": out_dir, "CustomName": name})
project.LoadRenderPreset(style["render"]["preset"])   # e.g. "H.264 Master" — must exist in Resolve already
job_id = project.AddRenderJob()
project.StartRendering([job_id])
# poll:
while project.IsRenderingInProgress():
    time.sleep(1)
status = project.GetRenderJobStatus(job_id)
```

## Common errors and what they usually mean

- `ImportError: No module named 'DaVinciResolveScript'` → env vars not set / wrong path for this
  OS or install location. Re-run `check_environment.py`.
- `resolve` comes back `None` from `scriptapp("Resolve")` → Resolve isn't running, or "External
  scripting using" is still set to "None" in preferences.
- `AppendToTimeline` silently does nothing / returns an empty list → usually a bad `startFrame`/
  `endFrame` pair (out of the source clip's range) or an unimported `mediaPoolItem` (import it
  first, keep the returned object, don't re-resolve by path).
- Subtitle import succeeds but no track appears → some Resolve versions need
  `"insertAdditionalTracks": True` in the options dict, or the timeline needs to already have at
  least one video/audio track before subtitle import; check the shipped README's exact signature
  for the installed version if the call above doesn't produce a track.
- `SetCDL` returns `False` for every clip → check the CDL map's values are strings, not numbers or
  lists (`"1.0 1.0 1.0"`, not `[1.0, 1.0, 1.0]`) — `color_grade.py` already does this conversion,
  so this usually means a version mismatch worth checking against the shipped README.
- `AddTrack("audio")` fails / `GetTrackCount` doesn't increase → some Resolve versions cap track
  count differently or need the timeline to be the *current* timeline (`project.SetCurrentTimeline`)
  before adding tracks — `build_project.py` already sets it current first; if this still fails,
  add the third audio track manually in the Edit page once and rerun.
