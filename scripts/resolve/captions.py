"""Tier 1 captions: import the generated .srt as a subtitle track.

See references/resolve_scripting_api.md for the Tier 2 (per-word animated
pop-in via a Fusion Text+ template) upgrade path — deliberately not
implemented here since it depends on a template the user builds by hand in
Resolve first, and is more fragile across Resolve versions.
"""


def import_srt(timeline, srt_path):
    ok = timeline.ImportIntoTimeline(
        srt_path,
        {
            "autoImportSourceClipsIntoMediaPool": False,
            "importSourceClips": False,
            "insertAdditionalTracks": True,
        },
    )
    if not ok:
        raise RuntimeError(
            f"timeline.ImportIntoTimeline failed for {srt_path}. Some Resolve versions need "
            "slightly different option keys for subtitle import — check the exact signature in "
            "the README.txt Resolve ships with its scripting API (see "
            "references/resolve_scripting_api.md), and confirm the timeline already has at "
            "least one video/audio track before importing."
        )
    return ok
