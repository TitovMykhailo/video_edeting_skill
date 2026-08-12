"""Build the Media Pool bins and timeline tracks from edit_plan.json / beat_plan.json.

Frame math: Resolve's timeline API is frame-indexed, not seconds-native.
`to_frame(seconds, fps)` is used everywhere a timestamp needs to become a
frame number — always round, never truncate, so segments stay contiguous
instead of drifting by a frame each cut.
"""
import math
import os
import sys


def to_frame(seconds, fps):
    return round(seconds * fps)


def _verify_append_count(result, clip_infos, what):
    """AppendToTimeline does not overwrite an overlapping record: when two clipInfos in the same
    batch resolve to overlapping record ranges on the same track, Resolve silently keeps the
    EARLIER one and drops the later one from the returned list — no exception, no indication of
    which clipInfo lost (independently verified against a real Resolve build by the
    davinci-resolve-mcp project's testing; see references/resolve_scripting_api.md). A non-empty
    `result` is therefore not proof nothing was lost — only a count match is. Call this after
    every AppendToTimeline batch that's supposed to place exactly len(clip_infos) items."""
    if len(result) != len(clip_infos):
        raise RuntimeError(
            f"AppendToTimeline placed {len(result)}/{len(clip_infos)} {what}. Resolve drops a "
            "clip whose record range overlaps an earlier one on the same track instead of "
            "erroring — rerun validate_timeline.py against beat_plan.json to find the collision "
            "before re-running the build."
        )


def get_or_create_folder(media_pool, root_folder, name):
    for sub in root_folder.GetSubFolderList():
        if sub.GetName() == name:
            return sub
    return media_pool.AddSubFolder(root_folder, name)


def ensure_empty_timeline(media_pool, project, name):
    """Create a fresh empty timeline named `name`, deleting any existing one with that name
    first. Without this, re-running build_project.py after ANY failure downstream of timeline
    creation (a bad clip, AppendToTimeline rejecting the batch, a crash) leaves a same-named
    timeline behind, and the next attempt fails immediately at CreateEmptyTimeline with no
    indication that the fix is to go delete a leftover timeline by hand in Resolve's UI — caught
    exactly this way on a real production run. Re-running this script should be safe to just
    retry, not require manual cleanup first."""
    existing = None
    for i in range(1, project.GetTimelineCount() + 1):
        tl = project.GetTimelineByIndex(i)
        if tl and tl.GetName() == name:
            existing = tl
            break
    if existing is not None:
        media_pool.DeleteTimelines([existing])

    timeline = media_pool.CreateEmptyTimeline(name)
    if timeline is None:
        raise RuntimeError(
            f"CreateEmptyTimeline('{name}') failed even after removing any existing timeline "
            "with that name. Check the project isn't in a bad state (e.g. still rendering)."
        )
    return timeline


def ensure_audio_tracks(timeline, count):
    """Make sure the timeline has at least `count` audio tracks (narration=1, SFX=2, music=3)."""
    current = timeline.GetTrackCount("audio")
    for _ in range(count - current):
        if not timeline.AddTrack("audio"):
            raise RuntimeError(
                f"Could not add an audio track (have {timeline.GetTrackCount('audio')}, need {count})."
            )


def import_into_bin(media_pool, folder, abs_paths, cache):
    """Import files not already in `cache` (abs_path -> MediaPoolItem), into `folder`.

    Matches each returned MediaPoolItem back to the path that produced it by its actual
    `File Path` clip property (basename), rather than assuming `ImportMedia`'s return list is in
    the same order as the input list — that ordering isn't part of the documented contract, and
    pairing by position would silently cache the wrong item for a path (wrong footage/audio
    placed on the timeline later) if Resolve ever returns them out of order.
    """
    to_import = [p for p in abs_paths if p not in cache]
    if to_import:
        media_pool.SetCurrentFolder(folder)
        items = media_pool.ImportMedia(to_import)
        if items is None:
            items = []

        by_basename = {}
        for item in items:
            try:
                file_path = item.GetClipProperty("File Path")
            except Exception:  # noqa: BLE001 — fall back to "unmatched" below rather than aborting the whole import
                file_path = None
            by_basename.setdefault(os.path.basename(file_path) if file_path else None, []).append(item)

        missing = []
        for path in to_import:
            candidates = by_basename.get(os.path.basename(path))
            if candidates:
                cache[path] = candidates.pop(0)
            else:
                missing.append(path)

        if missing:
            raise RuntimeError(
                f"Resolve only imported {len(items)}/{len(to_import)} files into '{folder.GetName()}'. "
                f"Likely missing/unreadable: {missing}"
            )
    return cache


def build_audio_track_declicked(media_pool, timeline, narration_item, total_duration_s, fps, track_index=1):
    """Place the ALREADY-declicked narration (see scripts/render_narration_audio.py) as one
    single clip spanning the whole timeline. This is what build_project.py actually uses now —
    see build_audio_track() below for why placing keep_segments directly, un-declicked, isn't
    used anymore."""
    end_frame = to_frame(total_duration_s, fps) - 1
    clip_info = {
        "mediaPoolItem": narration_item,
        "startFrame": 0,
        "endFrame": end_frame,
        "trackIndex": track_index,
        "mediaType": 2,
    }
    result = media_pool.AppendToTimeline([clip_info])
    if not result:
        raise RuntimeError(
            "AppendToTimeline returned nothing for the narration audio track. Check the "
            "declicked narration file imported correctly."
        )
    _verify_append_count(result, [clip_info], "for the declicked narration track")
    return result


def build_audio_track(media_pool, timeline, narration_item, keep_segments, fps, track_index=1):
    """Append the trimmed narration segments to an audio track, in order, back to back, straight
    out of the ORIGINAL (un-declicked) recording. Superseded by build_audio_track_declicked() —
    every cut here is a hard amplitude discontinuity with no fade (Resolve's scripting API has
    no fade/crossfade control at all — confirmed by grepping the shipped README.txt), and a
    narration with a few hundred keep_segments produced audible clicking on a real render.
    Kept only in case something ever needs the raw multi-segment placement directly; build_project.py
    calls scripts/render_narration_audio.py first and uses build_audio_track_declicked() instead."""
    clip_infos = []
    for seg in keep_segments:
        start_frame = to_frame(seg["src_start"], fps)
        end_frame = to_frame(seg["src_end"], fps) - 1
        if end_frame <= start_frame:
            continue
        clip_infos.append(
            {
                "mediaPoolItem": narration_item,
                "startFrame": start_frame,
                "endFrame": end_frame,
                "trackIndex": track_index,
                "mediaType": 2,  # audio
            }
        )
    if not clip_infos:
        raise RuntimeError("edit_plan.json has no usable keep_segments — nothing to build the audio track from.")

    result = media_pool.AppendToTimeline(clip_infos)
    if not result:
        raise RuntimeError(
            "AppendToTimeline returned nothing for the narration audio track. Check that the "
            "narration file imported correctly and its startFrame/endFrame ranges are within "
            "its actual duration."
        )
    _verify_append_count(result, clip_infos, "narration segments")
    return result


def build_video_track(media_pool, timeline, beat_plan, media_item_by_path, fps, track_index=1):
    """Place each beat's media at its explicit timeline position (recordFrame), looping if asked."""
    clip_infos = []
    for beat in beat_plan["beats"]:
        media = beat["media"]
        item = media_item_by_path.get(media["path"])
        if item is None:
            raise RuntimeError(
                f"Beat at {beat['start']}s references media '{media['path']}' which was never "
                "imported — check the path is correct relative to the media library."
            )

        beat_start_frame = to_frame(beat["start"], fps)
        beat_end_frame = to_frame(beat["end"], fps)
        beat_len_frames = beat_end_frame - beat_start_frame
        clip_start = to_frame(media["src_in"], fps)
        clip_end = to_frame(media["src_out"], fps)
        clip_len = clip_end - clip_start
        if clip_len <= 0 or beat_len_frames <= 0:
            continue

        if media.get("loop") and clip_len < beat_len_frames:
            repeats = math.ceil(beat_len_frames / clip_len)
            for i in range(repeats):
                remaining = beat_len_frames - i * clip_len
                this_len = min(clip_len, remaining)
                clip_infos.append(
                    {
                        "mediaPoolItem": item,
                        "startFrame": clip_start,
                        "endFrame": clip_start + this_len - 1,
                        "trackIndex": track_index,
                        "recordFrame": beat_start_frame + i * clip_len,
                        "mediaType": 1,  # video
                    }
                )
        else:
            # clip runs once; if it's longer than the beat, trim to the beat's length instead
            # of overrunning into the next beat. If it's SHORTER and not looping, this only
            # places the clip's own natural length — the remainder of the beat is left empty on
            # the video track (Resolve has no scripting call this repo relies on for freeze-
            # framing a clip's last frame to fill extra time), not held on the last frame. Flag it
            # rather than let a silent black gap show up as a surprise in the render.
            if clip_len < beat_len_frames:
                print(
                    f"WARNING: beat at {beat['start']}s uses '{media['path']}' ({clip_len} frames) "
                    f"which is shorter than the beat ({beat_len_frames} frames) and isn't set to "
                    "loop — the video track will have an empty gap for the remainder of this beat. "
                    'Set `"loop": true` on this beat\'s media, trim the beat to the clip\'s length, '
                    "or pick a longer clip.",
                    file=sys.stderr,
                )
            this_len = min(clip_len, beat_len_frames)
            clip_infos.append(
                {
                    "mediaPoolItem": item,
                    "startFrame": clip_start,
                    "endFrame": clip_start + this_len - 1,
                    "trackIndex": track_index,
                    "recordFrame": beat_start_frame,
                    "mediaType": 1,
                }
            )

    if not clip_infos:
        raise RuntimeError("beat_plan.json produced no placeable clips — check it has beats with valid media.")

    result = media_pool.AppendToTimeline(clip_infos)
    if not result:
        raise RuntimeError(
            "AppendToTimeline returned nothing for the video track. A common cause is a "
            "recordFrame that collides with the timeline's existing content in an unexpected "
            "way, or a startFrame/endFrame outside the source clip's real duration."
        )
    _verify_append_count(result, clip_infos, "video beats")
    return result
