"""Apply the style profile's color grade to timeline items via Resolve's CDL controls.

CDL (Color Decision List) is the standard slope/offset/power/saturation control set every
color panel exposes — see references/style_profile_schema.md for what the numbers in a style
profile's `color.grade_cdl` mean, and references/resolve_scripting_api.md for the exact API
call this wraps (SetCDL takes space-separated per-channel strings, not lists — that conversion
happens here so the style profile itself can stay in plain JSON numbers).
"""


def _channel_string(values):
    return " ".join(str(v) for v in values)


def apply_grade(timeline_items, color_config, node_index="1"):
    """Apply one CDL grade to every given TimelineItem. Returns (applied_count, failed_paths)."""
    grade = color_config.get("grade_cdl")
    if not grade:
        return 0, []

    cdl_map = {
        "NodeIndex": node_index,
        "Slope": _channel_string(grade.get("slope", [1.0, 1.0, 1.0])),
        "Offset": _channel_string(grade.get("offset", [0.0, 0.0, 0.0])),
        "Power": _channel_string(grade.get("power", [1.0, 1.0, 1.0])),
        "Saturation": str(grade.get("saturation", 1.0)),
    }

    applied = 0
    failed = []
    for i, item in enumerate(timeline_items):
        try:
            ok = item.SetCDL(cdl_map)
        except Exception:  # noqa: BLE001 — a version-dependent API call, degrade per-clip not for the whole batch
            ok = False
        if ok:
            applied += 1
        else:
            # GetName() failing too (not just SetCDL) has been observed for a handful of items
            # in one real run — falling back through GetClipProperty and a plain index means the
            # warning still points at *something* locatable instead of a bare "<unknown clip>"
            # that gives the user nothing to click on in Resolve.
            label = None
            try:
                label = item.GetName()
            except Exception:  # noqa: BLE001
                pass
            if not label:
                try:
                    label = item.GetClipProperty("File Path")
                except Exception:  # noqa: BLE001
                    pass
            failed.append(label or f"<item #{i} in this track>")

    return applied, failed


def apply_grade_or_warn(timeline_items, color_config, node_index="1"):
    """Same as apply_grade, but prints a clear warning instead of raising — a failed grade
    shouldn't abort the whole build, the edit itself matters more than the look on a first pass."""
    import sys

    applied, failed = apply_grade(timeline_items, color_config, node_index)
    if failed:
        print(
            f"WARNING: color grade applied to {applied}/{applied + len(failed)} clips. "
            f"SetCDL failed for: {failed}. This can happen if the installed Resolve version "
            "expects a different CDL map shape — check references/resolve_scripting_api.md, "
            "or apply the grade manually in the Color page for these clips.",
            file=sys.stderr,
        )
    return applied, failed
