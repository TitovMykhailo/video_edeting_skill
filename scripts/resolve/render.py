"""Render the assembled timeline to a draft file and report where it landed."""
import glob
import json
import os
import subprocess
import time
from shutil import which


def render_timeline(project, out_path, preset=None, poll_interval_s=1.0, timeout_s=3600):
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    filename = os.path.splitext(os.path.basename(out_path))[0]
    os.makedirs(out_dir, exist_ok=True)

    if preset:
        preset_ok = project.LoadRenderPreset(preset)
        if not preset_ok:
            # Not hasattr(project, "GetRenderPresetList") — independently verified (by the
            # davinci-resolve-mcp project) that bare hasattr()/getattr() on Resolve scripting
            # objects returns a truthy/callable result for ANY attribute name, real or invented,
            # so it can't actually distinguish "this method exists on this build" from "it
            # doesn't" and would let this line call a nonexistent method instead of degrading
            # cleanly. Try the call directly and treat any failure as "unavailable."
            try:
                available = project.GetRenderPresetList()
            except Exception:  # noqa: BLE001
                available = []
            raise RuntimeError(
                f"Render preset '{preset}' isn't available in this Resolve installation "
                f"(available: {available}). Create it once in the Deliver page under this exact "
                "name, or change render.preset in the style profile to one that exists."
            )

    # SetRenderSettings applies its keys ON TOP of whatever render state the Deliver page already
    # holds (a previously loaded preset, e.g. an "Audio Only" one from an earlier session) rather
    # than replacing it outright — independently verified by the davinci-resolve-mcp project: a
    # job queued with an explicit video target still rendered audio-only in seconds, with
    # SetRenderSettings, AddRenderJob, StartRendering and GetRenderJobStatus all reporting
    # success throughout. The job status is not a witness for what actually got rendered — only
    # the output file is (see the ffprobe check below).
    project.SetRenderSettings({"SelectAllFrames": True, "TargetDir": out_dir, "CustomName": filename})
    job_id = project.AddRenderJob()
    if not job_id:
        raise RuntimeError("project.AddRenderJob() returned no job id — check render settings are valid.")

    if not project.StartRendering([job_id]):
        raise RuntimeError(f"project.StartRendering failed to start job {job_id}.")

    elapsed = 0.0
    while project.IsRenderingInProgress():
        time.sleep(poll_interval_s)
        elapsed += poll_interval_s
        if elapsed > timeout_s:
            raise RuntimeError(f"Render job {job_id} did not finish within {timeout_s}s.")

    status = project.GetRenderJobStatus(job_id)
    if status.get("JobStatus") != "Complete":
        raise RuntimeError(f"Render job {job_id} finished with status: {status}")

    output_file = _find_output_file(out_dir, filename)
    _verify_has_video_stream(output_file)

    return {"job_id": job_id, "out_dir": out_dir, "filename": filename, "status": status, "output_file": output_file}


def _find_output_file(out_dir, filename):
    matches = sorted(glob.glob(os.path.join(out_dir, filename + ".*")))
    return matches[0] if matches else None


def _verify_has_video_stream(output_file):
    """A 'Complete' job status is not proof the rendered file actually has video in it — see the
    SetRenderSettings comment above. Confirm with ffprobe when it's available; skip quietly
    (rather than fail the build) when it isn't, same as this skill's other optional ffprobe uses."""
    if not output_file or not which("ffprobe"):
        return
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", output_file],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            # ffprobe itself failed (missing/unreadable file, not-yet-flushed write, etc.) —
            # that's a different problem than "no video stream", and not one this check can
            # diagnose. Skip rather than raise a false "no video stream" for the wrong reason.
            return
        streams = json.loads(out.stdout).get("streams", [])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return
    if not any(s.get("codec_type") == "video" for s in streams):
        raise RuntimeError(
            f"Render job reported Complete but '{output_file}' has no video stream — Resolve's "
            "SetRenderSettings can inherit an audio-only preset from a prior Deliver-page session "
            "instead of the video settings this build requested. Open the Deliver page, confirm "
            "'Export Video' is checked and a video codec is selected, then rerun."
        )
