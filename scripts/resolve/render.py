"""Render the assembled timeline to a draft file and report where it landed."""
import os
import time


def render_timeline(project, out_path, preset=None, poll_interval_s=1.0, timeout_s=3600):
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    filename = os.path.splitext(os.path.basename(out_path))[0]
    os.makedirs(out_dir, exist_ok=True)

    if preset:
        preset_ok = project.LoadRenderPreset(preset)
        if not preset_ok:
            available = project.GetRenderPresetList() if hasattr(project, "GetRenderPresetList") else []
            raise RuntimeError(
                f"Render preset '{preset}' isn't available in this Resolve installation "
                f"(available: {available}). Create it once in the Deliver page under this exact "
                "name, or change render.preset in the style profile to one that exists."
            )

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

    return {"job_id": job_id, "out_dir": out_dir, "filename": filename, "status": status}
