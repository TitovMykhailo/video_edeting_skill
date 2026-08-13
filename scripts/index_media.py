#!/usr/bin/env python3
"""Maintain the tagged asset-library index used for beat planning — covers both the visual
media library (video/image/gif clips) and a sound library (music/SFX), same index format.

Three subcommands, meant to be used together in a loop (see SKILL.md steps 4 and 5):

  scan        walk the library, find new/changed files, probe them with
              ffprobe, and pull a few representative frames per video (or a
              waveform image per audio file) so you (Claude) can look at
              them and write tags.
  write-tags  commit the tags/description/mood/quality you produced after
              looking at scan's frames/waveforms into the persistent index.
  query       search the tagged index for candidates for a beat, scored by
              tag/mood overlap with a recency penalty. Filter with --kind to
              search only visual assets or only audio (sfx/music).

The index lives at <library>/_media_index.json. Schema for every field is in
references/media_tagging_schema.md — read that before writing tags, it has
guidance on what makes a good tag set, including how to judge an SFX/music
file from its waveform image since you can't literally listen to it.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".avif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
GIF_EXTS = {".gif"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | GIF_EXTS | AUDIO_EXTS

INDEX_FILENAME = "_media_index.json"
IGNORE_DIR_PREFIXES = ("_scan_frames", ".")


def iter_media_files(library):
    for root, dirs, files in os.walk(library):
        dirs[:] = [d for d in dirs if not d.startswith(IGNORE_DIR_PREFIXES)]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in ALL_EXTS:
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, library).replace(os.sep, "/")
                yield abs_path, rel_path


def file_hash(abs_path):
    st = os.stat(abs_path)
    return f"size:{st.st_size},mtime:{int(st.st_mtime)}"


def kind_of(ext):
    if ext in IMAGE_EXTS:
        return "image"
    if ext in GIF_EXTS:
        return "gif"
    if ext in AUDIO_EXTS:
        return "audio"
    return "video"


def load_index(library):
    path = os.path.join(library, INDEX_FILENAME)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            index = json.load(f)
        if not isinstance(index, dict) or "files" not in index:
            # Reproduced live: pointing `scan`'s --out at this exact path (an easy mistake — the
            # module docstring's own "the index lives at <library>/_media_index.json" line reads
            # like the filename to use) overwrites the real index with scan's differently-shaped
            # report ({library, already_tagged_count, needs_tagging}, no "files" key), and every
            # later write-tags/query/scan call used to die on a bare `KeyError: 'files'` with no
            # indication of what actually went wrong. scan's report and this index are different
            # files by design — scan's --out is a free path for you to review, this index always
            # lives at exactly <library>/_media_index.json and is only ever written by write-tags.
            raise RuntimeError(
                f"{path} doesn't look like a media index (expected a dict with a 'files' key, "
                f"got: {list(index.keys()) if isinstance(index, dict) else type(index).__name__}). "
                "If this came from `scan`'s --out, that's a separate report file, not the index — "
                "don't point --out at this path. See the module docstring."
            )
        return index
    return {"files": {}}


def save_index(library, index):
    path = os.path.join(library, INDEX_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def have_tool(name):
    from shutil import which

    return which(name) is not None


def probe_media(abs_path, kind):
    if not have_tool("ffprobe"):
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                abs_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None

    duration_s = None
    fmt = data.get("format", {})
    if fmt.get("duration"):
        try:
            duration_s = round(float(fmt["duration"]), 3)
        except ValueError:
            pass

    width = height = codec = sample_rate = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and width is None:
            width = stream.get("width")
            height = stream.get("height")
            codec = stream.get("codec_name")
            if duration_s is None and stream.get("duration"):
                try:
                    duration_s = round(float(stream["duration"]), 3)
                except ValueError:
                    pass
        elif stream.get("codec_type") == "audio" and codec is None:
            codec = stream.get("codec_name")
            sample_rate = stream.get("sample_rate")
            if duration_s is None and stream.get("duration"):
                try:
                    duration_s = round(float(stream["duration"]), 3)
                except ValueError:
                    pass

    orientation = None
    if width and height:
        if width > height:
            orientation = "landscape"
        elif height > width:
            orientation = "portrait"
        else:
            orientation = "square"

    result = {
        "duration_s": duration_s,
        "width": width,
        "height": height,
        "orientation": orientation,
        "codec": codec,
        "kind": kind,
    }
    if kind == "audio" and sample_rate:
        result["sample_rate"] = sample_rate
    return result


def extract_waveform(abs_path, rel_path, frames_dir):
    """Render a waveform image so an audio file's energy/transient character can be judged by
    eye — a percussive whoosh/click looks visibly different from a sustained pad or music loop,
    which is the closest thing to 'listening' available without decoding audio directly."""
    safe_name = rel_path.replace("/", "__")
    out_dir = os.path.join(frames_dir, safe_name)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "waveform.png")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", abs_path,
                "-filter_complex", "showwavespic=s=800x160:colors=white",
                "-frames:v", "1", out_path,
            ],
            capture_output=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [out_path] if os.path.exists(out_path) else []


def extract_frames(abs_path, rel_path, frames_dir, kind, count, duration_s):
    if kind == "image":
        return [abs_path]
    if kind == "audio":
        if not have_tool("ffmpeg"):
            return []
        return extract_waveform(abs_path, rel_path, frames_dir)
    if not have_tool("ffmpeg"):
        return []

    safe_name = rel_path.replace("/", "__")
    out_dir = os.path.join(frames_dir, safe_name)
    os.makedirs(out_dir, exist_ok=True)

    dur = duration_s if duration_s and duration_s > 0.2 else 1.0
    fractions = [0.15, 0.5, 0.85][:count] if count < 3 else [0.1 + 0.8 * i / (count - 1) for i in range(count)]
    frame_paths = []
    for i, frac in enumerate(fractions):
        ts = max(0.0, dur * frac)
        out_path = os.path.join(out_dir, f"frame_{i}.jpg")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", abs_path, "-frames:v", "1", "-q:v", "3", out_path],
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if os.path.exists(out_path):
            frame_paths.append(out_path)
    return frame_paths


def cmd_scan(args):
    library = os.path.abspath(args.library)
    index = load_index(library)
    frames_dir = args.frames_dir or os.path.join(library, "_scan_frames")

    needs_tagging = []
    already_tagged = 0
    missing_tools_warned = False

    for abs_path, rel_path in iter_media_files(library):
        h = file_hash(abs_path)
        existing = index["files"].get(rel_path)
        if existing and existing.get("hash") == h:
            already_tagged += 1
            continue

        ext = os.path.splitext(rel_path)[1].lower()
        kind = kind_of(ext)
        probe = probe_media(abs_path, kind)
        if probe is None and not missing_tools_warned and not have_tool("ffprobe"):
            print("NOTE: ffprobe not found — files will be listed without quality/duration data.", file=sys.stderr)
            missing_tools_warned = True

        quality_flags = []
        min_height = args.min_height
        if probe and probe.get("height") and probe["height"] < min_height:
            quality_flags.append(f"low_resolution (<{min_height}px tall)")

        frames = extract_frames(abs_path, rel_path, frames_dir, kind, args.frames_per_video, probe.get("duration_s") if probe else None)

        needs_tagging.append(
            {
                "path": rel_path,
                "kind": kind,
                "hash": h,
                "probe": probe,
                "quality_flags": quality_flags,
                "frames": frames,
                "previously_tagged": existing is not None,
            }
        )

    result = {
        "library": library,
        "already_tagged_count": already_tagged,
        "needs_tagging": needs_tagging,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"{len(needs_tagging)} file(s) need tagging, {already_tagged} already up to date. "
        f"Wrote {args.out}.",
        file=sys.stderr,
    )
    if needs_tagging:
        print(
            "Look at the frame images listed per file, then write tags and run "
            "`index_media.py write-tags` — see references/media_tagging_schema.md.",
            file=sys.stderr,
        )


def cmd_write_tags(args):
    library = os.path.abspath(args.library)
    index = load_index(library)

    with open(args.tags, encoding="utf-8") as f:
        new_tags = json.load(f)

    now = datetime.now(timezone.utc).isoformat()
    written = 0
    for rel_path, tag_data in new_tags.items():
        abs_path = os.path.join(library, rel_path)
        if not os.path.exists(abs_path):
            print(f"WARNING: {rel_path} not found under {library}, skipping.", file=sys.stderr)
            continue

        ext = os.path.splitext(rel_path)[1].lower()
        kind = kind_of(ext)
        probe = probe_media(abs_path, kind)

        index["files"][rel_path] = {
            "hash": file_hash(abs_path),
            "kind": kind,  # stored independently of `probe` — probe can be None without ffprobe
            "probe": probe,
            "tags": tag_data.get("tags", []),
            "description": tag_data.get("description", ""),
            "mood": tag_data.get("mood", ""),
            "quality_ok": tag_data.get("quality_ok", True),
            "quality_notes": tag_data.get("quality_notes", ""),
            "source": tag_data.get("source", "own_library"),
            # "studio_ip" | "recognizable_individual" | None — flags real Content-ID/legal exposure
            # distinct from quality_ok (which is about whether a clip looks good, not whether it's
            # safe to use). Surfaced automatically in query()'s reasons below so the risk is visible
            # at the moment a clip is picked, not something to remember separately. See
            # references/editor_discipline.md's copyright-risk policy Part and
            # references/media_tagging_schema.md.
            "ip_risk": tag_data.get("ip_risk"),
            # which sound pack/library this asset came from (e.g. "happy-editing-transitions") —
            # lets query --pack keep a whole project inside one consistent sonic palette instead
            # of free-mixing across every tagged asset; see references/sound_mixing_techniques.md
            "pack": tag_data.get("pack"),
            # audio-only fields (SFX/music) — left null for visual assets, see
            # references/media_tagging_schema.md
            "energy": tag_data.get("energy"),
            "loopable": tag_data.get("loopable"),
            "tempo_bpm": tag_data.get("tempo_bpm"),
            "tagged_at": now,
        }
        written += 1

    save_index(library, index)
    print(f"Wrote tags for {written} file(s) to {os.path.join(library, INDEX_FILENAME)}.", file=sys.stderr)


def cmd_query(args):
    library = os.path.abspath(args.library)
    index = load_index(library)

    query_tags = [t.strip().lower() for t in args.tags.split(",")] if args.tags else []
    mood = args.mood.lower() if args.mood else None
    recent = set()
    if args.exclude_recent and os.path.exists(args.exclude_recent):
        with open(args.exclude_recent, encoding="utf-8") as f:
            recent = set(json.load(f))

    results = []
    for rel_path, entry in index["files"].items():
        if not args.allow_low_quality and entry.get("quality_ok") is False:
            continue
        if args.orientation:
            probe = entry.get("probe") or {}
            if probe.get("orientation") and probe["orientation"] != args.orientation:
                continue
        if args.kind and entry.get("kind") != args.kind:
            continue
        if args.pack and (entry.get("pack") or "").lower() != args.pack.lower():
            continue

        score = 0.0
        reasons = []
        entry_tags = [t.lower() for t in entry.get("tags", [])]
        description = (entry.get("description") or "").lower()

        for qt in query_tags:
            if qt in entry_tags:
                score += 1.0
                reasons.append(f"tag match: {qt}")
            elif qt in description:
                score += 0.5
                reasons.append(f"description mentions: {qt}")

        if mood and entry.get("mood", "").lower() == mood:
            score += 1.5
            reasons.append(f"mood match: {mood}")

        matched = score > 0 or not query_tags

        # Recency only reorders matches, it must never hide an otherwise-good one — see
        # references/media_tagging_schema.md ("deprioritizes recent files, doesn't hard-block").
        if rel_path in recent:
            score -= 2.0
            reasons.append("recently used (deprioritized)")

        # Score is untouched — ip_risk is a visibility flag for a human/agent to weigh, not a
        # penalty query should apply on its own (a Tier C clip might still be the right, deliberate
        # choice — see references/editor_discipline.md's copyright-risk policy). Hiding or
        # de-scoring it here would make that a silent decision instead of a visible one.
        ip_risk = entry.get("ip_risk")
        if ip_risk:
            reasons.append(f"WARNING: tagged ip_risk={ip_risk} - see editor_discipline.md's copyright-risk policy before using")

        if matched:
            results.append(
                {
                    "path": rel_path,
                    "kind": entry.get("kind"),
                    "pack": entry.get("pack"),
                    "score": round(score, 2),
                    "reasons": reasons,
                    "probe": entry.get("probe"),
                    "tags": entry.get("tags", []),
                    "description": entry.get("description", ""),
                    "mood": entry.get("mood", ""),
                    "energy": entry.get("energy"),
                    "loopable": entry.get("loopable"),
                    "tempo_bpm": entry.get("tempo_bpm"),
                    "ip_risk": ip_risk,
                }
            )

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[: args.limit]

    output = {"results": results}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="find new/changed media and extract frames for tagging")
    p_scan.add_argument("--library", required=True)
    p_scan.add_argument("--out", required=True)
    p_scan.add_argument("--frames-dir", help="defaults to <library>/_scan_frames")
    p_scan.add_argument("--frames-per-video", type=int, default=3)
    p_scan.add_argument("--min-height", type=int, default=720, help="flag videos shorter than this as low_resolution")
    p_scan.set_defaults(func=cmd_scan)

    p_write = sub.add_parser("write-tags", help="commit tags into the persistent index")
    p_write.add_argument("--library", required=True)
    p_write.add_argument("--tags", required=True, help="JSON file: {relative_path: {tags, description, mood, quality_ok, quality_notes, source, ip_risk, pack, energy, loopable, tempo_bpm}} — pack is which sound pack/library the asset came from (audio-relevant but not audio-only); energy/loopable/tempo_bpm are audio-only; ip_risk is \"studio_ip\"|\"recognizable_individual\"|omit, see references/media_tagging_schema.md")
    p_write.set_defaults(func=cmd_write_tags)

    p_query = sub.add_parser("query", help="search the tagged index")
    p_query.add_argument("--library", required=True)
    p_query.add_argument("--tags", default="", help="comma-separated tags/keywords")
    p_query.add_argument("--mood")
    p_query.add_argument("--kind", choices=["video", "image", "gif", "audio"], help="restrict to one asset kind, e.g. 'audio' when picking SFX/music")
    p_query.add_argument("--pack", help="restrict to one sound pack/library (e.g. 'happy-editing-transitions') to keep a project's SFX genre-consistent — see references/sound_mixing_techniques.md")
    p_query.add_argument("--orientation", choices=["landscape", "portrait", "square"])
    p_query.add_argument("--allow-low-quality", action="store_true")
    p_query.add_argument("--exclude-recent", help="path to a JSON list of recently used relative paths")
    p_query.add_argument("--limit", type=int, default=5)
    p_query.add_argument("--out", help="write JSON here instead of stdout")
    p_query.set_defaults(func=cmd_query)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
