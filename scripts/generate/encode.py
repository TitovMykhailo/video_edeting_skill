"""Shared PNG-sequence -> video encoding helper for the frame generators in this folder.

All generators (kinetic_text.py, chart.py, render_html_motion.py) work the same way: render one
PNG per frame into a temp directory, then call ffmpeg once to encode the sequence. Keeping that
one call in one place means the alpha-channel handling only needs to be right once.
"""
import shutil
import subprocess
import sys


def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def require_ffmpeg():
    if not have_ffmpeg():
        print(
            "ffmpeg is required to encode generated frames into a clip and isn't on PATH. "
            "Run scripts/check_environment.py for install instructions.",
            file=sys.stderr,
        )
        sys.exit(1)


def encode_frames_to_video(frames_dir, out_path, fps, transparent=False):
    """Encode frames_dir/frame_%05d.png into out_path.

    transparent=True requires out_path to end in .mov — encodes with the QuickTime Animation
    codec (qtrle), which preserves an alpha channel and is broadly supported for compositing an
    overlay clip (e.g. kinetic typography) on top of other footage in Resolve. transparent=False
    encodes an ordinary opaque H.264 .mp4, which is what a normal full-frame beat clip wants.
    """
    require_ffmpeg()

    if transparent and not out_path.lower().endswith(".mov"):
        raise ValueError("Transparent output must use a .mov path (qtrle requires QuickTime container).")

    pattern = f"{frames_dir}/frame_%05d.png"
    if transparent:
        cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", pattern, "-c:v", "qtrle", "-pix_fmt", "argb", out_path]
    else:
        cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", pattern, "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg encoding failed:\n{result.stderr[-2000:]}")
