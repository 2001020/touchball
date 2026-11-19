"""Audio analysis for charting: tempo grid, per-layer onsets, energy, sections.

Outputs (in <work>/analysis/):
  analysis.json  - machine-readable everything (used by lint / timeline / onsets)
  summary.md     - human/model readable overview (tempo, sections, density hints)
  bars.txt       - per-bar 16th-step onset grids for each layer (the main "sampling" sheet)
  overview.png   - spectrogram + energy + sections picture
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

SR = 22050
HOP = 256
LAYERS = ("kick", "snare", "hat", "melody", "bass")
LAYER_DESC = {
    "kick": "low percussive (<150 Hz): kick drum / low hits",
    "snare": "mid percussive (150-4k Hz): snare, claps, toms, percussive attacks",
    "hat": "high percussive (>5 kHz): hi-hats, cymbals, shakers",
    "melody": "harmonic 250-4k Hz note starts: lead / vocal / chords",
    "bass": "harmonic 40-250 Hz note starts: bass line",
}
STEP_CHARS = ".123456789"


def _norm(x: np.ndarray, q: float = 99.0) -> np.ndarray:
    hi = np.percentile(x, q) if x.size else 1.0
    return np.clip(x / (hi + 1e-9), 0.0, 1.5)


def _salience(x: np.ndarray, win_frames: int = 43, q: float = 99.0) -> np.ndarray:
    """Onset envelope minus its running median (removes the 'always busy' floor), normalised."""
    from scipy.ndimage import median_filter
    base = median_filter(x, size=win_frames, mode="nearest")
    sal = np.maximum(x - base, 0.0)
    hi = np.percentile(sal, q) if sal.size else 1.0
    return np.clip(sal / (hi + 1e-9), 0.0, 1.5)


def _band_onset(librosa, S_db: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    idx = np.where((freqs >= lo) & (freqs < hi))[0]
    if len(idx) == 0:
        return np.zeros(S_db.shape[1])
    env = librosa.onset.onset_strength(S=S_db[idx], sr=SR, hop_length=HOP, aggregate=np.mean)
    return env


def _sample(env: np.ndarray, times: np.ndarray, win: float = 0.03) -> np.ndarray:
    """max of env within +-win seconds of each time."""
    fr = times * SR / HOP
    w = max(1, int(round(win * SR / HOP)))
    out = np.zeros(len(times))
    n = len(env)
    for i, f in enumerate(fr):
        c = int(round(f))
        a, b = max(0, c - w), min(n, c + w + 1)
        out[i] = env[a:b].max() if b > a else 0.0
    return out


def _fit_grid(env: np.ndarray, bpm0: float, duration: float, bpm_fixed: float | None = None):
    """Grid-search BPM (+-1.5%) and phase maximising onset energy on beats & 8ths."""
    frame_t = np.arange(len(env)) * HOP / SR
    envs = np.convolve(env, np.ones(3) / 3, mode="same")

    def score(bpm, phases):
        period = 60.0 / bpm
        n = int((duration - phases.max()) / period) - 1
        if n < 8:
            return np.full(len(phases), -1.0)
        k = np.arange(n)
        beats = phases[:, None] + k[None, :] * period
        eighth = beats + period / 2
        vb = np.interp(beats, frame_t, envs)
        ve = np.interp(eighth, frame_t, envs)
        return vb.mean(axis=1) + 0.35 * ve.mean(axis=1)

    if bpm_fixed:
        cands = np.array([bpm_fixed])
    else:
        cands = np.unique(np.concatenate([
            np.linspace(bpm0 * 0.985, bpm0 * 1.015, 61),
            np.round(np.linspace(bpm0 * 0.985, bpm0 * 1.015, 61)),
        ]))
    best = (-1, bpm0, 0.0)
    for bpm in cands:
        period = 60.0 / bpm
        phases = np.arange(0, period, 0.004)
        sc = score(bpm, phases)
        i = int(np.argmax(sc))
        if sc[i] > best[0]:
            best = (float(sc[i]), float(bpm), float(phases[i]))
    _, bpm, phase = best
    # prefer a "round" BPM if it scores almost as well
    if not bpm_fixed:
        for rb in (round(bpm), round(bpm * 2) / 2):
            period = 60.0 / rb
            phases = np.arange(0, period, 0.002)
            sc = score(rb, phases)
            i = int(np.argmax(sc))
            if sc[i] >= best[0] * 0.985:
                bpm, phase = float(rb), float(phases[i])
                break
    # fine phase refinement
    period = 60.0 / bpm
    phases = np.arange(max(0.0, phase - 0.01), phase + 0.01, 0.0005)
    sc = score(bpm, phases)
    phase = float(phases[int(np.argmax(sc))]) % period
    return bpm, phase


def analyze(audio_path: str | Path, out_dir: str | Path, bpm: float | None = None,
            offset_ms: float | None = None, downbeat_shift: int = 0, beats_per_bar: int = 4) -> dict:
    import librosa  # heavy import, keep local

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    y, _ = librosa.load(str(audio_path), sr=SR, mono=True)
    duration = len(y) / SR

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    H, P = librosa.decompose.hpss(S, margin=(1.0, 2.0))
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    P_db = librosa.amplitude_to_db(P, ref=np.max)
    H_db = librosa.amplitude_to_db(H, ref=np.max)

    env_all = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    envs = {
        "kick": _band_onset(librosa, P_db, freqs, 20, 150),
        "snare": _band_onset(librosa, P_db, freqs, 150, 4000),
        "hat": _band_onset(librosa, P_db, freqs, 5000, 11025),
        "melody": _band_onset(librosa, H_db, freqs, 250, 4000),
        "bass": _band_onset(librosa, H_db, freqs, 40, 250),
    }
    n_fr = min(len(env_all), *(len(v) for v in envs.values()))
    env_all = env_all[:n_fr]
    envs = {k: v[:n_fr] for k, v in envs.items()}
    frame_t = np.arange(n_fr) * HOP / SR

    # ---- tempo & grid
    if bpm:
        bpm0 = float(bpm)
    else:
        tempo = librosa.feature.tempo(onset_envelope=env_all, sr=SR, hop_length=HOP, aggregate=np.median)
        bpm0 = float(np.atleast_1d(tempo)[0])
        # charts read best with BPM in [90, 200]
        while bpm0 < 90:
            bpm0 *= 2
        while bpm0 > 200:
            bpm0 /= 2
    grid_env = env_all + 0.5 * envs["kick"] + 0.5 * envs["snare"]
    bpm_fit, phase = _fit_grid(grid_env, bpm0, duration, bpm_fixed=float(bpm) if bpm else None)
    period = 60.0 / bpm_fit
    # phase bias correction: align the grid with the median position of strong onsets
    sal_all = _salience(env_all)
    pk = librosa.util.peak_pick(sal_all, pre_max=3, post_max=3, pre_avg=8, post_avg=8, delta=0.10, wait=int(0.07 * SR / HOP))
    pk = [p for p in pk if sal_all[p] > 0.4]
    if len(pk) > 16:
        b = (frame_t[pk] - phase) / period
        signed = (b - np.round(b * 4) / 4) * period
        bias = float(np.median(signed))
        if abs(bias) < 0.03:
            phase = (phase + bias) % period

    # downbeat: choose phase (mod beats_per_bar) with strongest low-end accents
    n_beats_total = int((duration - phase) / period)
    beat_times = phase + np.arange(n_beats_total) * period
    low = _sample(_norm(envs["kick"]) + 0.5 * _norm(envs["bass"]), beat_times)
    allb = _sample(_norm(env_all), beat_times)
    scores = []
    for p in range(beats_per_bar):
        sel = np.arange(p, n_beats_total, beats_per_bar)
        scores.append(low[sel].mean() + 0.3 * allb[sel].mean() if len(sel) else 0)
    db_phase = (int(np.argmax(scores)) + downbeat_shift) % beats_per_bar
    first_downbeat = phase + db_phase * period
    while first_downbeat - beats_per_bar * period >= 0:
        first_downbeat -= beats_per_bar * period
    # one bar of lead-in before the first downbeat so that notes at the very start of the song are
    # readable (META.offset may be negative; Phira starts its clock early in that case)
    first_downbeat -= beats_per_bar * period
    if offset_ms is not None:
        first_downbeat = offset_ms / 1000.0
    offset = first_downbeat
    total_beats = int(math.floor((duration - offset) / period))
    n_bars = total_beats // beats_per_bar + (1 if total_beats % beats_per_bar else 0)

    def t_of(beat):
        return offset + beat * period

    # ---- step grids (16ths) and triplet grids
    steps_per_beat = 4
    step_beats = np.arange(total_beats * steps_per_beat) / steps_per_beat
    step_t = t_of(step_beats)
    tri_beats = np.arange(total_beats * 3) / 3
    tri_t = t_of(tri_beats)
    normed = {k: _salience(v) for k, v in envs.items()}
    normed["all"] = _salience(env_all)

    # ---- onsets per layer (peak picked) with quantisation
    onsets: dict[str, list[dict]] = {}
    for k, env in list(normed.items()):
        peaks = librosa.util.peak_pick(env, pre_max=3, post_max=3, pre_avg=8, post_avg=8,
                                       delta=0.10, wait=int(0.07 * SR / HOP))
        items = []
        for p in peaks:
            t = frame_t[p]
            if t < offset - 0.03:
                continue
            b = (t - offset) / period
            q4 = round(b * 4) / 4
            q3 = round(b * 3) / 3
            e4 = abs(b - q4) * period
            e3 = abs(b - q3) * period
            if e3 + 0.008 < e4 and abs(q3 * 4 - round(q3 * 4)) > 1e-6:
                qb, err, grid_name = q3, e3, "1/3"
            else:
                qb, err, grid_name = q4, e4, "1/4"
            items.append({"t": round(float(t), 4), "beat": round(float(qb), 4), "raw": round(float(b), 4),
                          "err_ms": round(float(err * 1000), 1), "grid": grid_name,
                          "s": round(float(min(env[p], 1.5)), 3)})
        onsets[k] = items

    # 16th-step grid built from the peak-picked onsets (strength of the onset snapped to that step)
    grid = {}
    for k, items in onsets.items():
        g = np.zeros(total_beats * steps_per_beat)
        for o in items:
            if o["grid"] != "1/4" or o["err_ms"] > 45:
                continue
            si = int(round(o["beat"] * steps_per_beat))
            if 0 <= si < len(g):
                g[si] = max(g[si], o["s"])
        grid[k] = g

    # sustain estimate for melody/bass onsets (hold candidates): follow the dominant pitch bin of
    # the harmonic spectrogram from the onset until it decays by ~7 dB or a new onset arrives there
    Hn = H[:, :n_fr]
    for k, (lo, hi) in (("melody", (250, 4000)), ("bass", (40, 250))):
        band = np.where((freqs >= lo) & (freqs < hi))[0]
        lst = onsets[k]
        for i, o in enumerate(lst):
            f0 = int(round(o["t"] * SR / HOP))
            if f0 + 3 >= n_fr:
                o["len_beats"] = 0.0
                continue
            seg = Hn[band, f0 + 1:f0 + 4].mean(axis=1)
            kb = band[int(np.argmax(seg))]
            rows = slice(max(0, kb - 1), kb + 2)
            peak = Hn[rows, f0:f0 + 4].sum(axis=0).max()
            f = f0 + 2
            limit = min(n_fr, f0 + int(4 * period * SR / HOP))
            while f < limit and Hn[rows, f].sum() > 0.45 * peak:
                f += 1
            o["len_beats"] = round(float((f - f0) * HOP / SR / period), 2)
            # pitch: strongest bin in the fundamental range (vocals/lead 180-1100 Hz, bass 40-250 Hz)
            plo, phi = (180, 1100) if k == "melody" else (lo, hi)
            pb = np.where((freqs >= plo) & (freqs < phi))[0]
            hz = float(freqs[pb[int(np.argmax(Hn[pb, f0 + 1:f0 + 4].mean(axis=1)))]])
            o["pitch"] = int(round(69 + 12 * math.log2(hz / 440.0))) if hz > 0 else None

    # ---- energy per beat / bar
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0][:n_fr]
    rms_db = librosa.amplitude_to_db(rms + 1e-6, ref=np.max)
    beat_energy = []
    for b in range(total_beats):
        a, c = max(0, int(t_of(b) * SR / HOP)), max(0, int(t_of(b + 1) * SR / HOP))
        beat_energy.append(float(np.mean(rms[a:c])) if c > a else 0.0)
    beat_energy = np.array(beat_energy)
    be_norm = beat_energy / (np.percentile(beat_energy, 98) + 1e-9) if len(beat_energy) else beat_energy
    be_norm = np.clip(be_norm, 0, 1)
    bar_energy = [float(be_norm[i * beats_per_bar:(i + 1) * beats_per_bar].mean()) for i in range(n_bars)]

    # ---- onset density per bar (strong onsets of any layer)
    bar_density = []
    for i in range(n_bars):
        sl = grid["all"][i * beats_per_bar * steps_per_beat:(i + 1) * beats_per_bar * steps_per_beat]
        bar_density.append(int((sl > 0.35).sum()))

    # ---- sections (bar-level novelty on timbre+harmony+energy)
    bar_feats = []
    chroma = librosa.feature.chroma_stft(S=H ** 2, sr=SR, hop_length=HOP)[:, :n_fr]
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(librosa.feature.melspectrogram(S=S ** 2, sr=SR)), n_mfcc=13)[:, :n_fr]
    for i in range(n_bars):
        a = max(0, int(t_of(i * beats_per_bar) * SR / HOP))
        c = max(0, int(t_of(min((i + 1) * beats_per_bar, total_beats)) * SR / HOP))
        c = max(c, a + 1)
        f = np.concatenate([chroma[:, a:c].mean(axis=1), mfcc[1:, a:c].mean(axis=1) / 40.0,
                            [bar_energy[i] * 2, bar_density[i] / 16.0]])
        bar_feats.append(f)
    bar_feats = np.array(bar_feats) if n_bars else np.zeros((0, 26))
    sections = _segment(bar_feats, bar_energy, n_bars, duration, beats_per_bar, period)

    for s in sections:
        s["start_beat"] = s["start_bar"] * beats_per_bar
        s["end_beat"] = min(s["end_bar"] * beats_per_bar, total_beats)
        s["start_time"] = round(t_of(s["start_beat"]), 2)
        s["end_time"] = round(t_of(s["end_beat"]), 2)
        bars = range(s["start_bar"], s["end_bar"])
        s["energy"] = round(float(np.mean([bar_energy[b] for b in bars])), 3)
        s["onsets_per_bar"] = round(float(np.mean([bar_density[b] for b in bars])), 1)

    result = {
        "audio": str(audio_path),
        "duration": round(duration, 3),
        "bpm": round(bpm_fit, 3),
        "offset_ms": int(round(offset * 1000)),
        "beats_per_bar": beats_per_bar,
        "total_beats": total_beats,
        "n_bars": n_bars,
        "steps_per_beat": steps_per_beat,
        "sections": sections,
        "bar_energy": [round(v, 3) for v in bar_energy],
        "bar_density": bar_density,
        "beat_energy": [round(float(v), 3) for v in be_norm],
        "grid": {k: [round(float(x), 2) for x in v] for k, v in grid.items()},
        "onsets": onsets,
        "layers": LAYER_DESC,
    }
    (out_dir / "analysis.json").write_text(json.dumps(result), encoding="utf-8")
    (out_dir / "bars.txt").write_text(render_bars(result), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_summary(result), encoding="utf-8")
    try:
        _plot_overview(y, S, result, out_dir / "overview.png")
    except Exception as exc:  # plotting is optional
        print(f"[analyze] overview plot failed: {exc}")
    return result


def _segment(feats: np.ndarray, energy: list[float], n_bars: int, duration: float, bpb: int, period: float) -> list[dict]:
    if n_bars < 8:
        return [{"id": 0, "start_bar": 0, "end_bar": n_bars, "label": "A"}]
    X = feats - feats.mean(axis=0)
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    ssm = X @ X.T
    nov = np.zeros(n_bars)
    for L in (4, 8):
        k = np.ones((2 * L, 2 * L))
        k[:L, L:] = -1
        k[L:, :L] = -1
        g = np.exp(-((np.arange(2 * L) - L + 0.5) ** 2) / (2 * (L / 2) ** 2))
        k = k * np.outer(g, g)
        pad = np.pad(ssm, L, mode="edge")
        for b in range(n_bars):
            nov[b] += float((pad[b:b + 2 * L, b:b + 2 * L] * k).sum())
    nov = np.maximum(nov, 0)
    nov /= nov.max() + 1e-9
    e = np.array(energy)
    ejump = np.zeros(n_bars)
    for b in range(2, n_bars - 1):
        ejump[b] = abs(e[b:b + 2].mean() - e[b - 2:b].mean())
    ejump /= ejump.max() + 1e-9
    score = nov + 0.6 * ejump
    score += 0.25 * (np.arange(n_bars) % 4 == 0)  # phrase prior
    score += 0.15 * (np.arange(n_bars) % 8 == 0)
    bar_sec = period * bpb
    target = max(2, int(round(duration / 22.0)))
    min_len = max(4, int(round(8.0 / bar_sec)))
    order = np.argsort(-score)
    bounds = [0, n_bars]
    for b in order:
        b = int(b)
        if b < min_len or b > n_bars - min_len // 2:
            continue
        if all(abs(b - x) >= min_len for x in bounds):
            bounds.append(b)
        if len(bounds) - 1 >= target:
            break
    bounds = sorted(bounds)
    segs = []
    for i in range(len(bounds) - 1):
        segs.append({"id": i, "start_bar": bounds[i], "end_bar": bounds[i + 1]})
    # label by similarity of mean features
    means = [X[s["start_bar"]:s["end_bar"]].mean(axis=0) for s in segs]
    labels: list[str] = []
    protos: list[np.ndarray] = []
    for m in means:
        m = m / (np.linalg.norm(m) + 1e-9)
        found = None
        for li, p in enumerate(protos):
            if float(m @ p) > 0.8:
                found = li
                break
        if found is None:
            protos.append(m)
            found = len(protos) - 1
        labels.append(chr(ord("A") + found))
    for s, l in zip(segs, labels):
        s["label"] = l
    # role hints
    en = [float(np.mean(energy[s["start_bar"]:s["end_bar"]])) for s in segs]
    hi = np.percentile(en, 70) if en else 0
    lo = np.percentile(en, 30) if en else 0
    for i, s in enumerate(segs):
        if i == 0 and en[i] <= lo + 1e-9:
            role = "intro"
        elif i == len(segs) - 1 and en[i] <= lo + 1e-9:
            role = "outro"
        elif en[i] >= hi:
            role = "climax (chorus/drop)"
        elif i + 1 < len(segs) and en[i + 1] > en[i] + 0.12:
            role = "build-up"
        elif en[i] <= lo:
            role = "calm (breakdown/verse)"
        else:
            role = "main (verse)"
        s["role_hint"] = role
    return segs


def _step_line(vals) -> str:
    out = []
    for v in vals:
        if v < 0.12:
            out.append(".")
        else:
            out.append(STEP_CHARS[min(9, max(1, int(round(v * 9))))])
    return "".join(out)


def render_bars(a: dict) -> str:
    bpb, spb = a["beats_per_bar"], a["steps_per_beat"]
    period = 60.0 / a["bpm"]
    off = a["offset_ms"] / 1000
    lines = [
        "# Per-bar onset sheet. Each layer cell = one bar, one char per 1/4 beat (16th note).",
        "# '.' = nothing, 1..9 = onset strength. Beat boundaries are separated by '|'.",
        f"# beat b starts at time {off:.3f} + b*{period:.4f}s.  bar n starts at beat n*{bpb}.",
        "# 'tri' lists onsets that sit on a 1/3-beat (triplet) grid instead of 1/4.",
        "# Layers: " + "; ".join(f"{k}={v}" for k, v in a["layers"].items()),
        "",
    ]
    tri_by_bar: dict[int, list[str]] = {}
    for layer in ("all",):
        for o in a["onsets"][layer]:
            if o["grid"] == "1/3" and o["s"] > 0.25:
                bar = int(o["beat"] // bpb)
                from .timing import fmt_beat
                tri_by_bar.setdefault(bar, []).append(fmt_beat(o["beat"]))
    for s in a["sections"]:
        lines.append(f"== section {s['id']} [{s['label']}] {s.get('role_hint', '')}: bars {s['start_bar']}-{s['end_bar'] - 1}, "
                     f"beats {s['start_beat']}-{s['end_beat']}, {s['start_time']:.1f}s-{s['end_time']:.1f}s, energy {s['energy']:.2f} ==")
        hdr = "bar  beat   time  E   | " + " | ".join(f"{k:<{bpb * spb + bpb - 1}}" for k in ("kick", "snare", "hat", "melody", "bass"))
        lines.append(hdr)
        for bar in range(s["start_bar"], s["end_bar"]):
            st = bar * bpb * spb
            cells = []
            for k in ("kick", "snare", "hat", "melody", "bass"):
                vals = a["grid"][k][st:st + bpb * spb]
                txt = _step_line(vals).ljust(bpb * spb, " ")
                cells.append("|".join(txt[i:i + spb] for i in range(0, bpb * spb, spb)))
            t = off + bar * bpb * period
            e = a["bar_energy"][bar] if bar < len(a["bar_energy"]) else 0
            row = f"{bar:>3} {bar * bpb:>5} {t:>6.2f} {e:.2f} | " + " | ".join(cells)
            if bar in tri_by_bar:
                row += "   tri: " + ",".join(tri_by_bar[bar][:8])
            lines.append(row)
        lines.append("")
    return "\n".join(lines)


def render_summary(a: dict) -> str:
    bpb = a["beats_per_bar"]
    lines = [
        "# Audio analysis summary",
        "",
        f"- duration: {a['duration']:.2f} s",
        f"- BPM: {a['bpm']}  (beat = {60 / a['bpm']:.4f} s; verify by rendering - if notes feel doubled/halved, re-run `phichart analyze --bpm X`)",
        f"- offset: {a['offset_ms']} ms  (music time of beat 0 = META.offset; beat 0 is one bar BEFORE the first detected downbeat, giving a lead-in bar. Negative = before the audio starts)",
        f"- meter: {bpb}/4, total beats: {a['total_beats']}, bars: {a['n_bars']}",
        "",
        "## Sections (auto-detected - refine them in your plan)",
        "",
        "| id | label | role hint | bars | beats | time | energy | onsets/bar |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in a["sections"]:
        lines.append(f"| {s['id']} | {s['label']} | {s.get('role_hint', '')} | {s['start_bar']}-{s['end_bar'] - 1} | "
                     f"{s['start_beat']}-{s['end_beat']} | {s['start_time']:.1f}-{s['end_time']:.1f}s | {s['energy']:.2f} | {s['onsets_per_bar']} |")
    lines += ["", "## Layer onset counts (peak-picked, strength>=0.3)", ""]
    for k, lst in a["onsets"].items():
        strong = [o for o in lst if o["s"] >= 0.3]
        tri = sum(1 for o in strong if o["grid"] == "1/3")
        lines.append(f"- {k}: {len(strong)} onsets ({tri} on triplet grid) - {a['layers'].get(k, 'all layers combined')}")
    hold_c = [o for o in a["onsets"]["melody"] if o.get("len_beats", 0) >= 1.0 and o["s"] >= 0.3]
    lines.append(f"- sustained melody notes (>=1 beat, hold candidates): {len(hold_c)}")
    lines += [
        "",
        "## Energy per bar (0-1)",
        "",
        "```",
    ]
    for i in range(0, a["n_bars"], 16):
        seg = a["bar_energy"][i:i + 16]
        lines.append(f"bars {i:>3}-{i + len(seg) - 1:>3}: " + " ".join(f"{v:.2f}" for v in seg))
    lines += ["```", "", "Files: bars.txt (per-bar onset sheet), overview.png (spectrogram/energy/sections), analysis.json.", ""]
    return "\n".join(lines)


def _plot_overview(y, S, a: dict, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import librosa
    import librosa.display

    fig, axes = plt.subplots(3, 1, figsize=(18, 9), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]})
    D = librosa.amplitude_to_db(S, ref=np.max)
    librosa.display.specshow(D, sr=SR, hop_length=HOP, x_axis="time", y_axis="log", ax=axes[0], cmap="magma")
    period = 60 / a["bpm"]
    off = a["offset_ms"] / 1000
    colors = plt.cm.tab10.colors
    for s in a["sections"]:
        for ax in axes:
            ax.axvline(s["start_time"], color="white" if ax is axes[0] else "k", lw=1.2, ls="--")
        axes[0].text(s["start_time"] + 0.3, 6000, f"{s['id']}:{s['label']}\n{s.get('role_hint', '')}", color="white", fontsize=8, va="top")
        axes[1].axvspan(s["start_time"], s["end_time"], color=colors[ord(s["label"]) % 10], alpha=0.25)
    bt = off + np.arange(len(a["beat_energy"])) * period
    axes[1].plot(bt, a["beat_energy"], color="k", lw=0.8)
    axes[1].set_ylabel("energy")
    st = off + np.arange(len(a["grid"]["all"])) / a["steps_per_beat"] * period
    for k, c in (("kick", "tab:red"), ("snare", "tab:green"), ("melody", "tab:blue")):
        axes[2].plot(st, a["grid"][k], lw=0.5, color=c, label=k)
    axes[2].legend(loc="upper right", fontsize=7)
    axes[2].set_ylabel("onsets")
    for b in range(0, a["n_bars"], 4):
        axes[2].text(off + b * a["beats_per_bar"] * period, 1.4, str(b), fontsize=6)
    axes[2].set_xlabel("time (s); numbers = bar index")
    fig.suptitle(f"BPM {a['bpm']}  offset {a['offset_ms']}ms  bars {a['n_bars']}")
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def load_analysis(work: Path) -> dict | None:
    p = Path(work) / "analysis" / "analysis.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None
