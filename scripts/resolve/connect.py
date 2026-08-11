"""Connect to a running local DaVinci Resolve instance via its scripting API.

See references/resolve_scripting_api.md for the one-time environment setup
this depends on (RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB / PYTHONPATH, and
enabling 'External scripting using: Local' in Resolve's preferences).
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
            "Resolve's scripting module loaded but returned no connection. Make sure DaVinci "
            "Resolve is running and Preferences > General > 'External scripting using' is set "
            "to 'Local' (restart Resolve after changing it)."
        )
    return resolve
