"""Connect to a running local DaVinci Resolve instance via its scripting API.

See references/resolve_scripting_api.md for the one-time environment setup this depends on
(RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB / PYTHONPATH). On DaVinci Resolve Free, calling
`scriptapp("Resolve")` yourself is Studio-only as of 19.1 no matter who calls it — confirmed by
direct test that this is true even for code Resolve itself launches via Workspace > Scripts, not
just an external terminal process. What Free *does* give a script launched that way (also
confirmed by direct test) is an already-connected `resolve` object pre-injected as a global into
that script's `__main__` — the same hand-off the F6 Console gets. get_resolve() below checks for
that first and only falls back to requesting a fresh connection via scriptapp() if it's missing
(the normal case for an external terminal run, where Studio would allow it).
"""
import os
import platform
import sys


def _candidate_api_paths():
    system = platform.system()
    if system == "Darwin":
        return ["/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"]
    if system == "Windows":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return [os.path.join(program_data, "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting")]
    return ["/opt/resolve/Developer/Scripting", "/home/resolve/Developer/Scripting"]


def _injected_resolve():
    """The `resolve` global Resolve pre-injects into __main__ when it launches a script itself
    (Workspace > Scripts, or the F6 Console) — not present at all for a normal external run."""
    import __main__

    return getattr(__main__, "resolve", None)


def get_resolve():
    """Return the connected `Resolve` scripting object, or raise RuntimeError with a fix."""
    injected = _injected_resolve()
    if injected is not None:
        return injected

    api_path = os.environ.get("RESOLVE_SCRIPT_API")
    candidates = [api_path] if api_path else _candidate_api_paths()
    found = next((p for p in candidates if p and os.path.isdir(p)), None)

    if not found:
        raise RuntimeError(
            "Could not locate the DaVinci Resolve scripting API. Run "
            "scripts/check_environment.py, and see references/resolve_scripting_api.md "
            "for the RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB env vars for your OS."
        )

    modules_path = os.path.join(found, "Modules")
    if modules_path not in sys.path:
        sys.path.append(modules_path)

    try:
        import DaVinciResolveScript as dvr_script  # noqa: N813
    except ImportError as e:
        raise RuntimeError(
            f"Found the API at {found} but couldn't import it ({e}). Check RESOLVE_SCRIPT_LIB "
            "is set — see references/resolve_scripting_api.md."
        ) from e

    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError(
            "Resolve's scripting module loaded but returned no connection, and no pre-injected "
            "`resolve` global was found either (this isn't running via Resolve's own Console or "
            "Scripts menu). First, make sure DaVinci Resolve is actually running. If it is: on "
            "DaVinci Resolve Free, requesting a fresh scripting connection like this is "
            "Studio-only as of 19.1 — no preference re-enables it. Use "
            "scripts/resolve/build_otio.py, or install scripts/resolve/run_from_menu.py via "
            "install_menu_script.py and run it from Resolve's own Workspace > Scripts > Comp "
            "menu instead (Resolve pre-injects a working connection there). On Resolve Studio, "
            "this error instead usually means Resolve just isn't running yet — see "
            "references/resolve_scripting_api.md."
        )
    return resolve
