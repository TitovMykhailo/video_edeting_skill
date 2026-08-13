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
    """Encode frames_dir/frame_%05d.png into out_path. Always a .mov container now — see below.

    transparent=True encodes with the QuickTime Animation codec (qtrle), which preserves an
    alpha channel, for compositing an overlay clip (e.g. kinetic typography) on top of other
    footage in Resolve. transparent=False encodes Apple ProRes 422 (prores_ks), not H.264.

    Why ProRes instead of H.264 for an ordinary opaque clip: reproduced live on a real project
    that every data-level check (AppendToTimeline count, a post-save re-read, per-clip enabled/
    opacity/composite properties, the color grade's own applied-count) reported completely
    correct, while the actual rendered pixels — and the Edit page's own timeline canvas — showed
    solid black for the clip's entire duration, every time, across many independent rebuilds.
    ffmpeg's own decode of the same file (ffprobe, a full `-f null -` integrity pass) was clean.
    That combination — correct everywhere a placement/metadata read can see, wrong everywhere an
    actual frame has to be decoded and drawn, in BOTH the live UI and the render, and only for
    ffmpeg-generated clips specifically — points at Resolve's own internal media engine (which is
    not ffmpeg, and doesn't need to decode a file the same way ffmpeg does) failing to decode
    these specific H.264 files, not a timeline/placement bug. ProRes is Blackmagic's own
    reference-quality intermediate codec and the one Resolve is built around; switching removes
    an entire class of decoder-compatibility guesswork instead of chasing a specific flag.
    """
    require_ffmpeg()

    if not out_path.lower().endswith(".mov"):
        raise ValueError("Output must use a .mov path — both qtrle and ProRes are QuickTime codecs.")

    pattern = f"{frames_dir}/frame_%05d.png"
    if transparent:
        cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", pattern, "-c:v", "qtrle", "-pix_fmt", "argb", out_path]
    else:
        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps), "-i", pattern,
            "-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le", out_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg encoding failed:\n{result.stderr[-2000:]}")
