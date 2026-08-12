"""Place beat-triggered SFX and a music bed track, per beat_plan.json's `sfx`/`music_bed` fields.

Ducking model: this skill's music bed doesn't do real sidechain automation (Resolve's scripting
API doesn't expose per-keyframe audio automation reliably enough to depend on — see
references/resolve_scripting_api.md). Instead it exploits something we already know from
edit_plan.json: after plan_cuts.py, narration covers the new timeline almost continuously from
0 to `total_new_duration_s` (pauses are shrunk, not zeroed, so there's no real narration-free gap
in the middle). So the music bed only needs two gain levels: `duck_gain_db` for the whole
narration span, and `base_gain_db` for any narration-free tail (an outro that runs longer than
the narration, if the beat plan has one). That's honest given what we can actually automate, and
covers the common case correctly.

A sharper technique exists beyond this — a De-esser (mis)used as a mid-frequency carve on the
music bus, ducking just the band the voice sits in instead of the whole track — but it needs an
audio effect plugin added to a track, which isn't something this script attempts against Resolve's
API (see references/sound_mixing_techniques.md's "frequency-carve ducking" section for why, and
for how to apply it by hand in Fairlight when a project's music is dense enough to need it).
"""
import math
import sys

from timeline_build import to_frame

# Property name Resolve's TimelineItem API uses for per-clip gain varies across versions and
# isn't consistently documented — try the common one and degrade to a clear instruction if it
# doesn't stick, rather than silently producing an unbalanced mix.
VOLUME_PROPERTY_NAME = "Volume"


def _set_gain_or_warn(item, gain_db, context):
    try:
        ok = item.SetProperty(VOLUME_PROPERTY_NAME, gain_db)
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        print(
            f"WARNING: could not set gain ({gain_db} dB) on {context} via the scripting API — "
            "set it manually in the Fairlight page. See references/resolve_scripting_api.md.",
            file=sys.stderr,
        )


def get_clip_length_frames(item, fallback_frames):
    try:
        frames = item.GetClipProperty("Frames")
        return int(frames)
    except Exception:  # noqa: BLE001 — property name/shape can vary by Resolve version
        return fallback_frames


def build_sfx_track(media_pool, timeline, beat_plan, sfx_item_by_path, fps, track_index):
    clip_infos = []
    for beat in beat_plan["beats"]:
        for sfx in beat.get("sfx", []):
            item = sfx_item_by_path.get(sfx["path"])
            if item is None:
                raise RuntimeError(f"sfx entry references '{sfx['path']}' which was never imported.")
            length_frames = get_clip_length_frames(item, fallback_frames=to_frame(1.0, fps))
            record_frame = to_frame(beat["start"] + sfx["at"], fps)
            clip_infos.append(
                {
                    "mediaPoolItem": item,
                    "startFrame": 0,
                    "endFrame": max(0, length_frames - 1),
                    "trackIndex": track_index,
                    "recordFrame": record_frame,
                    "mediaType": 2,
                    "_gain_db": sfx.get("gain_db", 0.0),
                }
            )

    if not clip_infos:
        return []

    # AppendToTimeline's return order isn't formally documented either, but unlike ImportMedia
    # (matching arbitrary files, order not inherent to the operation) this call is placing an
    # explicitly ordered/positioned sequence via recordFrame — there's no batch to reorder. Treated
    # as safe to zip positionally on that basis; if gains ever land on the wrong SFX clip, this
    # assumption is the first thing to re-check.
    gains = [c.pop("_gain_db") for c in clip_infos]
    result = media_pool.AppendToTimeline(clip_infos) or []
    for item, gain_db in zip(result, gains):
        if gain_db:
            _set_gain_or_warn(item, gain_db, "an SFX clip")
    return result


def build_music_bed(media_pool, timeline, music_bed, music_item, narration_end_s, total_duration_s, fps, track_index):
    if not music_bed:
        return []

    clip_len_frames = get_clip_length_frames(music_item, fallback_frames=to_frame(30.0, fps))
    if clip_len_frames <= 0:
        raise RuntimeError(f"Music bed clip '{music_bed['path']}' reported zero/invalid length.")

    def place_span(span_start_s, span_end_s, gain_db):
        span_start_f = to_frame(span_start_s, fps)
        span_end_f = to_frame(span_end_s, fps)
        span_len = span_end_f - span_start_f
        if span_len <= 0:
            return []
        if not music_bed.get("loop", True):
            this_len = min(clip_len_frames, span_len)
            infos = [
                {
                    "mediaPoolItem": music_item,
                    "startFrame": 0,
                    "endFrame": this_len - 1,
                    "trackIndex": track_index,
                    "recordFrame": span_start_f,
                    "mediaType": 2,
                }
            ]
        else:
            repeats = math.ceil(span_len / clip_len_frames)
            infos = []
            for i in range(repeats):
                remaining = span_len - i * clip_len_frames
                this_len = min(clip_len_frames, remaining)
                infos.append(
                    {
                        "mediaPoolItem": music_item,
                        "startFrame": 0,
                        "endFrame": this_len - 1,
                        "trackIndex": track_index,
                        "recordFrame": span_start_f + i * clip_len_frames,
                        "mediaType": 2,
                    }
                )
        placed = media_pool.AppendToTimeline(infos) or []
        for item in placed:
            _set_gain_or_warn(item, gain_db, "a music bed segment")
        return placed

    duck_gain = music_bed.get("duck_gain_db", -18.0)
    base_gain = music_bed.get("base_gain_db", -12.0)

    placed_items = []
    narration_end_s = min(narration_end_s, total_duration_s)
    placed_items += place_span(0.0, narration_end_s, duck_gain)
    if total_duration_s > narration_end_s:
        placed_items += place_span(narration_end_s, total_duration_s, base_gain)

    if not placed_items:
        raise RuntimeError("Music bed produced no placeable clips — check total_duration_s is positive.")
    return placed_items
