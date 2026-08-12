"""Captions: NOT scriptable in the documented Resolve API — this module just tells you that
clearly instead of pretending otherwise.

This used to call `timeline.ImportIntoTimeline(srt_path, {...})`, which looked plausible but was
wrong: confirmed against Resolve's own shipped README.txt, `ImportIntoTimeline` imports an
**AAF** timeline-exchange file, not a subtitle track — it was never going to work for an .srt,
on any version. Searched the whole shipped API surface for an SRT-equivalent (case-insensitive
for "srt", "ImportSubtitle", "LoadSubtitle") and found nothing. The only subtitle-related calls
that exist are: AddTrack("subtitle") / GetTrackCount("subtitle") (manage an empty subtitle
track, don't fill it from a file), and Timeline.CreateSubtitlesFromAudio(...) (Studio-only,
Resolve's own AI re-transcribes the audio from scratch — it doesn't take our already-correct,
word-aligned captions.srt as input, so using it would throw away the accuracy this skill's
pipeline already has).

Given that, importing captions.srt onto the timeline is a manual step: File > Import > Subtitle
in Resolve's own UI (exact menu wording varies a bit by version). build_project.py prints this
instruction instead of attempting an API call that cannot succeed.
"""

MANUAL_IMPORT_MESSAGE = (
    "Captions are not importable via the scripting API (see this module's docstring for why) — "
    "import {srt_path} manually: File > Import > Subtitle in Resolve."
)


def manual_import_message(srt_path):
    return MANUAL_IMPORT_MESSAGE.format(srt_path=srt_path)
