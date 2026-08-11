"""Build the Media Pool bins and timeline tracks from edit_plan.json / beat_plan.json.

Frame math: Resolve's timeline API is frame-indexed, not seconds-native.
`to_frame(seconds, fps)` is used everywhere a timestamp needs to become a
frame number — always round, never truncate, so segments stay contiguous
instead of drifting by a frame each cut.
"""
import math
import os


def to_frame(seconds, fps):
    return round(seconds * fps)


def get_or_create_folder(media_pool, root_folder, name):
    for sub in root_folder.GetSubFolderList():
        if sub.GetName() == name:
            return sub
    return media_pool.AddSubFolder(root_folder, name)


def ensure_audio_tracks(timeline, count):
    """Make sure the timeline has at least `count` audio tracks (narration=1, SFX=2, music=3)."""
    current = timeline.GetTrackCount("audio")
    for _ in range(count - current):
        if not timeline.AddTrack("audio"):
            raise RuntimeError(
                f"Could not add an audio track (have {timeline.GetTrackCount('audio')}, need {count})."
            )


def import_into_bin(media_pool, folder, abs_paths, cache):
    """Import files not already in `cache` (abs_path -> MediaPoolItem), into `folder`."""
    to_import = [p for p in abs_paths if p not in cache]
    if to_import:
        media_pool.SetCurrentFolder(folder)
        items = media_pool.ImportMedia(to_import)
        if items is None:
            items = []
        if len(items) != len(to_import):
            imported_names = {os.path.basename(i.GetClipProperty("File Path")) for i in items} if items else set()
            missing = [p for p in to_import if os.path.basename(p) not in imported_names]
            raise RuntimeError(
                f"Resolve only imported {len(items)}/{len(to_import)} files into '{folder.GetName()}'. "
                f"Likely missing/unreadable: {missing}"
            )
        for path, item in zip(to_import, items):
            cache[path] = item
    return cache


def build_audio_track(media_pool, timeline, narration_item, keep_segments, fps, track_index=1):
    """Append the trimmed narration segments to an audio track, in order, back to back."""
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
    return result


def _clip_duration_frames(beat_media, fps):
    return to_frame(beat_media["src_out"], fps) - to_frame(beat_media["src_in"], fps)


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
            # of overrunning into the next beat
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
    return result
