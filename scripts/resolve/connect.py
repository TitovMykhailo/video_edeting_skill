"""Connect to a running local DaVinci Resolve instance via its scripting API.

See references/resolve_scripting_api.md for the one-time environment setup this depends on
(RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB / PYTHONPATH). If get_resolve() below raises "loaded
but returned no connection" and this process is a normal external one (a terminal, not something
Resolve itself launched via its Scripts menu) — that's very likely DaVinci Resolve Free, where
this call is Studio-only as of 19.1 (there's no preference to re-enable it; see
resolve_scripting_api.md's "Free edition" note). Use scripts/resolve/run_from_menu.py (installed
via install_menu_script.py) or scripts/resolve/build_otio.py instead.
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


def get_resolve():
    """Return the connected `Resolve` scripting object, or raise RuntimeError with a fix."""
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
            "Resolve's scripting module loaded but returned no connection. First, make sure "
            "DaVinci Resolve is actually running. If it is: on DaVinci Resolve Free, external "
            "scripting (a script run as its own process, like this one) is blocked entirely as "
            "of Resolve 19.1 — no preference re-enables it. Use scripts/resolve/build_otio.py, "
            "or install scripts/resolve/run_from_menu.py via install_menu_script.py and run it "
            "from Resolve's own Workspace > Scripts > Comp menu instead (that runs in-process, "
            "which isn't gated). On Resolve Studio, this error instead usually means Resolve "
            "just isn't running yet — see references/resolve_scripting_api.md."
        )
    return resolve
