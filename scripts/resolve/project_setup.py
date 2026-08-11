"""Create/open the project and set timeline format from a style profile + aspect ratio."""


def ensure_project(project_manager, name):
    project = project_manager.LoadProject(name)
    if project is None:
        project = project_manager.CreateProject(name)
    if project is None:
        raise RuntimeError(
            f"Could not create or load a project named '{name}'. If a project with this name "
            "is already open with unsaved conflicting changes, close or rename it first."
        )
    return project


def set_timeline_format(project, width, height, fps):
    # collected as a list and checked with all() rather than accumulated with `ok &= ...` —
    # SetSetting isn't guaranteed to return a real bool (e.g. None on some versions), and `&=`
    # against a non-bool/non-int raises TypeError instead of just failing the check
    results = [
        project.SetSetting("timelineResolutionWidth", str(width)),
        project.SetSetting("timelineResolutionHeight", str(height)),
        project.SetSetting("timelineFrameRate", str(fps)),
    ]
    if not all(results):
        raise RuntimeError(
            f"Resolve rejected one of the timeline format settings ({width}x{height}@{fps}). "
            "This can happen if fps isn't one Resolve considers valid — try a standard value "
            "like 24, 25, 30, 50, or 60."
        )


def aspect_settings(style, aspect_ratio):
    ratios = style.get("aspect_ratios", {})
    if aspect_ratio not in ratios:
        raise ValueError(
            f"Aspect ratio '{aspect_ratio}' isn't defined in this style profile's "
            f"aspect_ratios ({list(ratios)}). Add it or pick one of those."
        )
    r = ratios[aspect_ratio]
    return r["width"], r["height"], r["fps"]
