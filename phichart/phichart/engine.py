"""Bridge to Phira's real renderer (phira-snap, built on prpr) + image annotation."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import rpe
from .timing import fmt_beat

PKG_ROOT = Path(__file__).resolve().parent.parent          # .../phichart (project root)
CACHE = Path(os.environ.get("PHICHART_CACHE", PKG_ROOT / ".cache"))
PHIRA_DIR = Path(os.environ.get("PHICHART_PHIRA_DIR", PKG_ROOT / "third_party" / "phira"))
SNAP_BIN = Path(os.environ.get("PHICHART_SNAP_BIN", PHIRA_DIR / "target" / "release" / "phira-snap"))
FONT_PATHS = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    PHIRA_DIR / "assets" / "bold.ttf",
]


class EngineError(RuntimeError):
    pass


def font(size: int):
    for p in FONT_PATHS:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return ImageFont.load_default()


# ------------------------------------------------------------------ headless display + audio sink
def _alsa_home() -> Path:
    home = CACHE / "alsahome"
    home.mkdir(parents=True, exist_ok=True)
    rc = home / ".asoundrc"
    if not rc.exists():
        rc.write_text('pcm.nullpcm {\n  type null\n}\npcm.!default {\n  type plug\n  slave.pcm "nullpcm"\n}\n')
    return home


def ensure_display() -> str:
    if os.environ.get("PHICHART_DISPLAY"):
        return os.environ["PHICHART_DISPLAY"]
    for n in range(87, 97):
        sock = Path(f"/tmp/.X11-unix/X{n}")
        lock = Path(f"/tmp/.X{n}-lock")
        if sock.exists() and lock.exists():
            try:
                pid = int(lock.read_text().strip())
                os.kill(pid, 0)
                return f":{n}"
            except Exception:
                pass
        if not lock.exists():
            if not shutil.which("Xvfb"):
                raise EngineError("Xvfb not found: install xvfb (see scripts/setup.sh) or set PHICHART_DISPLAY")
            subprocess.Popen(["Xvfb", f":{n}", "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            for _ in range(50):
                if sock.exists():
                    return f":{n}"
                time.sleep(0.1)
    raise EngineError("could not start a virtual X display")


# ------------------------------------------------------------------ rendering
def render_times(chart: dict, music: Path, times: list[float], outs: list[Path], width=1280, height=720,
                 background: Path | None = None, dim: float = 0.55) -> None:
    """Render the chart (strict RPE dict) at chart-times (seconds) with phira-snap."""
    if not SNAP_BIN.exists():
        raise EngineError(f"phira-snap not built ({SNAP_BIN}). Run scripts/setup.sh first.")
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=CACHE, prefix="snap-") as td:
        td = Path(td)
        (td / "chart.json").write_text(json.dumps(chart), encoding="utf-8")
        music_name = "music" + music.suffix
        os.symlink(music.resolve(), td / music_name)
        job = {
            "chart_dir": str(td), "chart": "chart.json", "music": music_name, "dim": dim,
            "frames": [{"time": max(0.0, float(t)), "out": str(Path(o).resolve())} for t, o in zip(times, outs)],
        }
        if background and Path(background).exists():
            job["background"] = str(Path(background).resolve())
        (td / "job.json").write_text(json.dumps(job))
        env = dict(os.environ)
        env.update({"DISPLAY": ensure_display(), "HOME": str(_alsa_home()),
                    "PHIRA_SNAP_W": str(width), "PHIRA_SNAP_H": str(height), "RUST_BACKTRACE": "0"})
        proc = subprocess.run([str(SNAP_BIN), str(td / "job.json")], env=env, capture_output=True, text=True,
                              timeout=60 + 2 * len(times))
        missing = [o for o in outs if not Path(o).exists()]
        if proc.returncode != 0 or missing:
            err = "\n".join(l for l in (proc.stderr or "").splitlines()
                            if "waking futures" not in l and "tokio-rt-worker" not in l and l.strip())
            raise EngineError(f"phira-snap failed (code {proc.returncode}):\n{err[-3000:]}")


def _label_strip(width: int, text: str, ruler: bool = True) -> Image.Image:
    h = 44 if ruler else 26
    strip = Image.new("RGB", (width, h), (16, 16, 22))
    d = ImageDraw.Draw(strip)
    d.text((8, 4), text, fill=(240, 240, 240), font=font(17))
    if ruler:
        f = font(11)
        for x in range(-600, 601, 150):
            px = int((x / (rpe.RPE_W / 2) + 1) / 2 * width)
            d.line([(px, 26), (px, 33)], fill=(150, 150, 160), width=1)
            d.text((px - 12, 31), f"{x}", fill=(150, 150, 160), font=f)
    return strip


def frame_label(chart: dict, beat: float, extra: str = "") -> str:
    bpms = rpe.bpm_list(chart)
    t = bpms.time(beat)
    bar, inbar = divmod(beat, 4)
    return f"beat {fmt_beat(beat)} ({beat:.2f})  bar {int(bar)}+{inbar:g}  t={t + chart['META'].get('offset', 0) / 1000:.2f}s {extra}"


def snap_sheet(chart: dict, music: Path, beats: list[float], out: Path, compare: dict | None = None,
               cols: int | None = None, scale: float = 0.5, background: Path | None = None,
               label: str = "") -> Path:
    """Render frames at the given beats and assemble a labelled contact sheet."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows_src = [("", chart)] if compare is None else [("BEFORE", compare), ("AFTER", chart)]
    tiles_by_row = []
    with tempfile.TemporaryDirectory(dir=CACHE if CACHE.exists() else None) as td:
        for ri, (tag, ch) in enumerate(rows_src):
            bpms = rpe.bpm_list(ch)
            times = [bpms.time(b) for b in beats]
            outs = [Path(td) / f"r{ri}_{i}.png" for i in range(len(beats))]
            render_times(ch, music, times, outs, background=background)
            tiles = []
            for b, p in zip(beats, outs):
                im = Image.open(p).convert("RGB")
                if scale != 1.0:
                    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
                lab = _label_strip(im.width, (f"[{tag}] " if tag else "") + frame_label(ch, b), ruler=True)
                tile = Image.new("RGB", (im.width, im.height + lab.height))
                tile.paste(im, (0, 0))
                tile.paste(lab, (0, im.height))
                tiles.append(tile)
            tiles_by_row.append(tiles)
    n = len(beats)
    if compare is None:
        cols = cols or min(n, 3 if scale <= 0.5 else 2)
        grid = [tiles_by_row[0][i:i + cols] for i in range(0, n, cols)]
    else:
        cols = n
        grid = tiles_by_row
    tw, th = grid[0][0].size
    head = 30 if label else 0
    sheet = Image.new("RGB", (cols * tw + (cols - 1) * 6, head + len(grid) * th + (len(grid) - 1) * 6), (40, 40, 48))
    if label:
        ImageDraw.Draw(sheet).text((8, 5), label, fill=(255, 220, 120), font=font(18))
    for r, row in enumerate(grid):
        for c, tile in enumerate(row):
            sheet.paste(tile, (c * (tw + 6), head + r * (th + 6)))
    sheet.save(out)
    return out


def render_video(chart: dict, music: Path, out: Path, start_beat: float | None = None, end_beat: float | None = None,
                 fps: int = 30, width: int = 960, height: int = 540, background: Path | None = None,
                 hitsounds: bool = True) -> Path:
    """Preview video (Phira frames + music + optional tap sounds), for humans."""
    import numpy as np
    import soundfile as sf

    bpms = rpe.bpm_list(chart)
    off = chart["META"].get("offset", 0) / 1000.0
    last_beat = max([e for _, _, _, _, e in rpe.iter_notes(chart)] + [4.0])
    sb = 0.0 if start_beat is None else start_beat
    eb = (last_beat + 2) if end_beat is None else end_beat
    t0, t1 = bpms.time(sb), bpms.time(eb)
    out = Path(out)
    with tempfile.TemporaryDirectory(dir=CACHE) as td:
        td = Path(td)
        times = list(np.arange(t0, t1, 1.0 / fps))
        outs = [td / f"f{i:06d}.png" for i in range(len(times))]
        for i in range(0, len(times), 300):
            render_times(chart, music, times[i:i + 300], outs[i:i + 300], width, height, background=background)
        audio_in = td / "mix.wav"
        y, sr = sf.read(str(music), always_2d=True) if music.suffix.lower() in (".wav", ".flac", ".ogg") else (None, None)
        if y is None:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(music), str(td / "m.wav")], check=True)
            y, sr = sf.read(str(td / "m.wav"), always_2d=True)
        y = y.astype("float32") * 0.8
        if hitsounds:
            n = int(0.035 * sr)
            tick = (np.sin(2 * np.pi * 1800 * np.arange(n) / sr) * np.exp(-np.arange(n) / (0.008 * sr))).astype("float32") * 0.5
            for _, _, note, b, _ in rpe.iter_notes(chart):
                if note.get("isFake"):
                    continue
                i = int((bpms.time(b) + off) * sr)
                if 0 <= i < len(y) - n:
                    y[i:i + n] += tick[:, None]
        a0, a1 = int((t0 + off) * sr), int((t1 + off) * sr)
        seg = y[max(0, a0):max(0, a1)]
        if a0 < 0:  # chart starts before the audio (negative offset): pad leading silence
            seg = np.concatenate([np.zeros((-a0, y.shape[1]), dtype=y.dtype), seg])
        sf.write(str(audio_in), np.clip(seg, -1, 1), sr)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(fps), "-i", str(td / "f%06d.png"),
                        "-i", str(audio_in), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                        "-c:a", "aac", "-shortest", str(out)], check=True)
    return out
