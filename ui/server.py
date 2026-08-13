#!/usr/bin/env python3
"""Local dashboard for running/monitoring multiple video-editor builds side by side.

Why this exists: every build in this skill (assemble_video.py, the Resolve OTIO path) used to be
launched one at a time from a Claude Code conversation, blocking on that one process before
anything else could happen — no way to have two projects building at once, no persistent place to
see a critique agent's write-up after the conversation that produced it scrolled away, no way to
leave a note on a specific beat ("wrong tone here, use a calmer clip") without re-explaining it in
chat every time. This is a small local web dashboard, stdlib-only (http.server + subprocess +
threading — no pip install required), that fixes exactly those three gaps:

    - Multiple projects can build concurrently: each "Build" click launches assemble_video.py as
      its own OS subprocess, tracked independently. Nothing here blocks anything else, including
      this server's own responsiveness to other requests.
    - Critique write-ups persist as files under <project>/out/critique/*.json (see
      write_critique_result() below — call this, or hand-write the same shape, whenever a critique
      agent's findings should show up here) and render in a "Critique" tab per project, with the
      real sampled frames shown inline, instead of living only in a chat transcript.
    - Each beat (from beat_plan.json) gets a visible row with its text/intent/reasoning and an
      editable note field, saved to <project>/out/beat_notes.json — a durable, per-beat place to
      flag "this doesn't match the tone" or similar for a human (or Claude, next session) to read
      back later instead of losing it in conversation scrollback.

Deliberately NOT built: automatic critique dispatch from inside this server. That would need a
direct Anthropic API call (a separate API key, separate from a Claude Code subscription, billed
per use) — asked about directly and declined in favor of keeping critique runs inside a Claude
Code conversation as before; this dashboard only displays whatever gets written to
out/critique/*.json, it never generates that content itself.

Usage:
    python3 server.py --projects-root "C:\\path\\to\\shorts" [--port 8787]

Then open http://localhost:8787 in a browser. Each subfolder of --projects-root that contains an
out/beat_plan.json is treated as one project.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_SCRIPTS = os.path.join(SKILL_ROOT, "scripts")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

PROJECTS_ROOT = None  # set in main() from --projects-root

JOBS = {}
JOBS_LOCK = threading.Lock()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


def project_dir(name):
    """Resolves a project name to an absolute path under PROJECTS_ROOT, refusing anything that
    would escape it (a project name coming from a URL is untrusted input)."""
    candidate = os.path.abspath(os.path.join(PROJECTS_ROOT, name))
    root = os.path.abspath(PROJECTS_ROOT)
    if not (candidate == root or candidate.startswith(root + os.sep)):
        raise ValueError(f"'{name}' escapes the projects root")
    if not os.path.isdir(candidate):
        raise FileNotFoundError(f"No project '{name}'")
    return candidate


def list_projects():
    if not os.path.isdir(PROJECTS_ROOT):
        return []
    out = []
    with JOBS_LOCK:
        active_by_project = {
            j["project"]: jid for jid, j in JOBS.items() if j["status"] == "running"
        }
    for entry in sorted(os.listdir(PROJECTS_ROOT)):
        p = os.path.join(PROJECTS_ROOT, entry)
        out_dir = os.path.join(p, "out")
        beat_plan = os.path.join(out_dir, "beat_plan.json")
        if not os.path.isdir(p) or not os.path.exists(beat_plan):
            continue
        assembled = sorted(glob.glob(os.path.join(out_dir, "assembled*.mp4")), key=os.path.getmtime)
        critique_files = glob.glob(os.path.join(out_dir, "critique", "*.json"))
        out.append({
            "name": entry,
            "assembled_count": len(assembled),
            "latest_assembled": os.path.basename(assembled[-1]) if assembled else None,
            "latest_assembled_mtime": os.path.getmtime(assembled[-1]) if assembled else None,
            "has_resolve_render": os.path.exists(os.path.join(out_dir, "render.mov"))
            or os.path.exists(os.path.join(out_dir, "render.mp4")),
            "critique_count": len(critique_files),
            "active_job": active_by_project.get(entry),
        })
    return out


def probe_dimensions(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
        w, h = result.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except Exception:  # noqa: BLE001
        return None


def load_beats(name):
    p = project_dir(name)
    with open(os.path.join(p, "out", "beat_plan.json"), encoding="utf-8") as f:
        beat_plan = json.load(f)
    notes_path = os.path.join(p, "out", "beat_notes.json")
    notes = {}
    if os.path.exists(notes_path):
        with open(notes_path, encoding="utf-8") as f:
            notes = json.load(f)
    beats = []
    for i, beat in enumerate(beat_plan.get("beats", [])):
        beats.append({
            "index": i,
            "start": beat.get("start"),
            "end": beat.get("end"),
            "text": beat.get("text"),
            "intent": beat.get("intent"),
            "reasoning": beat.get("reasoning"),
            "media_path": (beat.get("media") or {}).get("path"),
            "sfx": [s.get("path") for s in beat.get("sfx", [])],
            "note": notes.get(str(i), {}).get("note", ""),
            "note_updated": notes.get(str(i), {}).get("updated"),
        })
    return beats


def save_beat_note(name, index, note):
    p = project_dir(name)
    notes_path = os.path.join(p, "out", "beat_notes.json")
    notes = {}
    if os.path.exists(notes_path):
        with open(notes_path, encoding="utf-8") as f:
            notes = json.load(f)
    notes[str(index)] = {"note": note, "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(notes_path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def load_critiques(name):
    """Reads every <project>/out/critique/*.json, newest first. Expected shape (see
    write_critique_result()'s docstring for the writer's side of this contract):
        {"timestamp": "...", "video": "assembled_v3.mp4", "summary": "...",
         "findings_markdown": "...", "frames": ["frame_0_5s.png", ...]}
    frames are resolved relative to <project>/out/critique/frames/ and served via /api/frame.
    Any file that doesn't parse as JSON with at least a "findings_markdown" key is skipped rather
    than crashing the whole dashboard over one bad write.
    """
    p = project_dir(name)
    crit_dir = os.path.join(p, "out", "critique")
    if not os.path.isdir(crit_dir):
        return []
    results = []
    for fpath in sorted(glob.glob(os.path.join(crit_dir, "*.json")), reverse=True):
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            if "findings_markdown" not in data:
                continue
            data["_file"] = os.path.basename(fpath)
            results.append(data)
        except (ValueError, OSError):
            continue
    return results


def resolve_asset_path(name, rel_path):
    """Resolves a project-relative asset path (a frame PNG, a rendered video) for /api/frame,
    refusing anything outside that project's own out/ directory."""
    p = project_dir(name)
    out_root = os.path.abspath(os.path.join(p, "out"))
    candidate = os.path.abspath(os.path.join(out_root, rel_path))
    if not (candidate == out_root or candidate.startswith(out_root + os.sep)):
        raise ValueError("path escapes project out/ directory")
    if not os.path.isfile(candidate):
        raise FileNotFoundError(candidate)
    return candidate


def start_build_job(name, mode):
    p = project_dir(name)
    out_dir = os.path.join(p, "out")
    beat_plan_path = os.path.join(out_dir, "beat_plan.json")
    narration_path = os.path.join(out_dir, "_narration_declicked.wav")
    captions_path = os.path.join(out_dir, "captions.srt")

    if mode != "ffmpeg":
        raise ValueError(
            "Only 'ffmpeg' builds can be launched from here. The Resolve/OTIO path needs a click "
            "inside DaVinci Resolve's own Scripts menu (Free edition blocks external automation "
            "of its scripting API) — this dashboard can't trigger that for you."
        )
    if not os.path.exists(narration_path):
        raise FileNotFoundError(f"Missing {narration_path}")

    with open(beat_plan_path, encoding="utf-8") as f:
        beat_plan = json.load(f)
    first_media = beat_plan["beats"][0]["media"]["path"]
    dims = probe_dimensions(first_media)
    if not dims:
        raise RuntimeError(f"Could not probe dimensions of {first_media}")
    width, height = dims

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"assembled_ui_{ts}.mp4")

    argv = [
        sys.executable, os.path.join(SKILL_SCRIPTS, "assemble_video.py"),
        "--beat-plan", beat_plan_path,
        "--narration-audio", narration_path,
        "--sound-library", p,
        "--width", str(width), "--height", str(height),
        "--out", out_path,
    ]
    if os.path.exists(captions_path):
        argv += ["--captions", captions_path]

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id, "project": name, "mode": mode, "status": "running",
        "log": [], "returncode": None, "started": time.time(), "out_path": out_path,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job

    def run():
        try:
            proc = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
            for line in proc.stdout:
                with JOBS_LOCK:
                    job["log"].append(line.rstrip("\n"))
            proc.wait()
            with JOBS_LOCK:
                job["returncode"] = proc.returncode
                job["status"] = "done" if proc.returncode == 0 else "error"
        except Exception as e:  # noqa: BLE001 — surface any launch failure into the job log itself
            with JOBS_LOCK:
                job["log"].append(f"ERROR launching build: {e}")
                job["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return job_id


def write_critique_result(project_dir_path, video_name, summary, findings_markdown, frame_files):
    """Reference implementation of the writer side of the out/critique/*.json contract this
    dashboard reads (see load_critiques()). Not called by this server itself — a critique is
    dispatched from a Claude Code conversation, not from here (see this module's docstring) — this
    exists so that flow has one exact, copy-pasteable shape to write into, and so the contract
    lives next to the code that reads it instead of only in a conversation. frame_files should
    already be copied into <project>/out/critique/frames/ before calling this."""
    crit_dir = os.path.join(project_dir_path, "out", "critique")
    frames_dir = os.path.join(crit_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video": video_name,
        "summary": summary,
        "findings_markdown": findings_markdown,
        "frames": [os.path.basename(f) for f in frame_files],
    }
    out_path = os.path.join(crit_dir, f"{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet — errors still surface via JSON error responses

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._send_json({"error": message}, status=status)

    def do_GET(self):  # noqa: N802 — http.server's naming convention
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == "/" or path == "/index.html":
                return self._send_file(os.path.join(STATIC_DIR, "index.html"))
            if path == "/api/projects":
                return self._send_json({"projects": list_projects()})
            if path == "/api/beats":
                return self._send_json({"beats": load_beats(qs["project"][0])})
            if path == "/api/critique":
                return self._send_json({"critiques": load_critiques(qs["project"][0])})
            if path == "/api/frame":
                fpath = resolve_asset_path(qs["project"][0], qs["path"][0])
                return self._send_file(fpath)
            if path == "/api/jobs":
                with JOBS_LOCK:
                    return self._send_json({"jobs": [
                        {k: v for k, v in j.items() if k != "log"} for j in JOBS.values()
                    ]})
            if path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    if not job:
                        return self._error(404, "no such job")
                    return self._send_json({**{k: v for k, v in job.items() if k != "log"}, "log": "\n".join(job["log"])})
            return self._error(404, "not found")
        except FileNotFoundError as e:
            self._error(404, str(e))
        except (ValueError, KeyError) as e:
            self._error(400, str(e))
        except Exception as e:  # noqa: BLE001
            self._error(500, str(e))

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            return self._error(400, "invalid JSON body")
        try:
            if path == "/api/build":
                job_id = start_build_job(body["project"], body.get("mode", "ffmpeg"))
                return self._send_json({"job_id": job_id})
            if path == "/api/beats/note":
                save_beat_note(body["project"], body["index"], body.get("note", ""))
                return self._send_json({"ok": True})
            return self._error(404, "not found")
        except FileNotFoundError as e:
            self._error(404, str(e))
        except (ValueError, KeyError) as e:
            self._error(400, str(e))
        except Exception as e:  # noqa: BLE001
            self._error(500, str(e))


def main():
    global PROJECTS_ROOT
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--projects-root", required=True, help="folder whose subfolders are each one project (each must contain out/beat_plan.json)")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    PROJECTS_ROOT = os.path.abspath(args.projects_root)
    if not os.path.isdir(PROJECTS_ROOT):
        print(f"ERROR: --projects-root {PROJECTS_ROOT} does not exist", file=sys.stderr)
        sys.exit(1)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Video editor dashboard: http://127.0.0.1:{args.port}  (projects root: {PROJECTS_ROOT})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
