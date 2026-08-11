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
4. Free vs Studio: the scripting API itself works the same in both. What differs is the Neural
   Engine (Studio-only) — built-in Speech-to-Text, Scene Cut Detection quality, Smart Reframe.
   This skill doesn't depend on any of those; transcription is done externally via
   `faster-whisper` specifically so the pipeline works on Free.

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
mediaPool.ImportMedia([absolute file paths]) -> list[MediaPoolItem]
mediaPool.CreateEmptyTimeline(name) -> Timeline
mediaPool.AppendToTimeline([clipInfo, ...]) -> list[TimelineItem]
```

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
