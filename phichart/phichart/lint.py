"""Playability / readability / sync checks for a chart."""
from __future__ import annotations

import bisect
import math
from collections import defaultdict

from . import rpe
from .timing import fmt_beat

LEVELS = {  # rough peak notes-per-second (1s window) comfortable for each difficulty
    "EZ": 4.5, "HD": 7.5, "IN": 11.0, "AT": 16.0,
}
GOOD_DENS = {1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48}


def lint(chart_in: dict, analysis: dict | None = None, level: str = "IN", max_items: int = 40) -> dict:
    chart, errors, warnings = rpe.normalize(chart_in)
    info: list[str] = []
    errs = list(errors)
    warns = list(warnings)
    if errors:
        return {"errors": errs, "warnings": warns, "info": info, "stats": {}}
    bpms = rpe.bpm_list(chart)
    lines = chart["judgeLineList"]

    items = []  # (time, end_time, li, note, beat, end_beat)
    for li, _, n, b, e in rpe.iter_notes(chart):
        items.append((bpms.time(b), bpms.time(e), li, n, b, e))
    items.sort(key=lambda it: (it[0], it[2]))
    real = [it for it in items if not it[3].get("isFake")]

    def where(it):
        return f"beat {fmt_beat(it[4])} (L{it[2]} x={it[3]['positionX']:.0f} {rpe.NOTE_TYPES[it[3]['type']]})"

    # ---- off-grid
    for it in real:
        d = it[3]["startTime"][2]
        if d not in GOOD_DENS:
            warns.append(f"{where(it)}: unusual subdivision 1/{d}")

    # ---- simultaneous groups / hands
    groups = defaultdict(list)
    for it in real:
        groups[round(it[0], 3)].append(it)
    holds = [it for it in real if it[3]["type"] == 2]
    for t, g in sorted(groups.items()):
        active = [h for h in holds if h[0] < t - 0.01 and h[1] > t + 0.01]
        if len(g) + len(active) > 2:
            errs.append(f"beat {fmt_beat(g[0][4])}: {len(g)} notes + {len(active)} held holds need {len(g) + len(active)} hands (max 2)")
        same_line = defaultdict(list)
        for it in g:
            same_line[it[2]].append(it)
        for li, gg in same_line.items():
            xs = sorted(it[3]["positionX"] for it in gg)
            for a, b in zip(xs, xs[1:]):
                if b - a < rpe.NOTE_WIDTH * 0.95:
                    errs.append(f"beat {fmt_beat(gg[0][4])} L{li}: simultaneous notes overlap (x {a:.0f} and {b:.0f}, need >= {rpe.NOTE_WIDTH:.0f} apart)")
        for h in active:
            for it in g:
                if it[2] == h[2] and abs(it[3]["positionX"] - h[3]["positionX"]) < rpe.NOTE_WIDTH * 0.8:
                    errs.append(f"{where(it)}: placed on top of a running hold (hold from beat {fmt_beat(h[4])})")

    # ---- overlaps in time on the same spot (unreadable stacking)
    by_line = defaultdict(list)
    for it in real:
        by_line[it[2]].append(it)
    for li, lst in by_line.items():
        for i, it in enumerate(lst):
            for jt in lst[i + 1:i + 6]:
                dt = jt[0] - it[0]
                if dt <= 0.005:
                    continue
                if dt > 0.09:
                    break
                if abs(jt[3]["positionX"] - it[3]["positionX"]) < rpe.NOTE_WIDTH * 0.5 and not (
                        it[3]["type"] == 4 and jt[3]["type"] == 4):
                    warns.append(f"{where(it)} and {where(jt)}: {dt * 1000:.0f} ms apart on the same spot (stacked, hard to read/hit)")

    # ---- fast jumps & flick follow-ups
    singles = [g[0] for t, g in sorted(groups.items()) if len(g) == 1]
    for a, b in zip(singles, singles[1:]):
        dt = b[0] - a[0]
        dx = abs(b[3]["positionX"] - a[3]["positionX"])
        xa, xb = a[3]["positionX"], b[3]["positionX"]
        # opposite sides = normal two-hand alternation; only flag travel that one hand has to make
        same_hand = (xa > 0) == (xb > 0) or min(abs(xa), abs(xb)) < 100
        if a[2] == b[2] and dt < 0.13 and same_hand and dx > 420 and not (a[3]["type"] == 4 or b[3]["type"] == 4):
            warns.append(f"{where(a)} -> {where(b)}: {dx:.0f}px one-hand jump in {dt * 1000:.0f} ms (very hard)")
        if a[3]["type"] == 3 and dt < 0.12 and abs(b[3]["positionX"] - a[3]["positionX"]) < rpe.NOTE_WIDTH and b[3]["type"] != 4:
            warns.append(f"{where(a)}: flick followed {dt * 1000:.0f} ms later by a note at the same spot")

    # ---- density
    times = [it[0] for it in real]
    nps_peak, peak_at = 0.0, 0.0
    for i, t in enumerate(times):
        j = bisect.bisect_right(times, t + 1.0)
        if j - i > nps_peak:
            nps_peak, peak_at = j - i, t
    lim = LEVELS.get(level.upper(), 11.0)
    dense = []
    for i, t in enumerate(times):
        j = bisect.bisect_right(times, t + 1.0)
        if j - i > lim * 1.15:
            b = bpms.beat(t)
            if not dense or b - dense[-1][1] > 2:
                dense.append([b, b, j - i])
            else:
                dense[-1][1] = b
                dense[-1][2] = max(dense[-1][2], j - i)
    for b0, b1, n in dense:
        warns.append(f"beats {fmt_beat(round(b0 * 4) / 4)}-{fmt_beat(round(b1 * 4) / 4)}: density {n} notes/s exceeds {level} comfort (~{lim:.0f}/s)")

    # ---- readability: lead time & line placement & speed
    leads = []
    for it in real:
        li, n = it[2], it[3]
        line = lines[li]
        st = rpe.line_state(line, it[4])
        if st["speed"] * n.get("speed", 1) <= 0:
            errs.append(f"{where(it)}: line speed {st['speed']:.2f} * note speed {n.get('speed', 1)} <= 0 at hit time")
            continue
        rad = math.radians(st["rot"])
        hx = st["x"] + n["positionX"] * math.cos(rad)
        hy = st["y"] - n["positionX"] * math.sin(rad)
        if abs(hx) > rpe.RPE_W / 2 - 20 or abs(hy) > rpe.RPE_H / 2 - 20:
            errs.append(f"{where(it)}: hit point ({hx:.0f},{hy:.0f}) is off screen")
        lt = rpe.note_lead_time(chart, li, n, bpms, step=0.02)
        leads.append(lt)
        if lt < 0.42:
            warns.append(f"{where(it)}: visible only {lt:.2f}s before hit (too fast; aim 0.6-1.2s)")
        elif lt > 2.4:
            warns.append(f"{where(it)}: visible {lt:.2f}s before hit (too slow, screen gets cluttered)")

    # ---- audio sync
    synced = None
    if analysis:
        off_t = analysis["offset_ms"] / 1000.0
        chart_off = chart["META"].get("offset", 0) / 1000.0
        if abs(off_t - chart_off) > 0.002:
            info.append(f"chart offset {chart_off * 1000:.0f}ms differs from analysis offset {off_t * 1000:.0f}ms")
        if abs(analysis["bpm"] - chart["BPMList"][0]["bpm"]) > 0.01:
            info.append(f"chart BPM {chart['BPMList'][0]['bpm']} differs from analysis BPM {analysis['bpm']}")
        on_times = sorted(o["t"] for k in ("kick", "snare", "hat", "melody", "bass", "all")
                          for o in analysis["onsets"].get(k, []) if o["s"] >= 0.2)
        far = []
        ok = 0
        for it in real:
            mt = it[0] + chart_off
            j = bisect.bisect_left(on_times, mt)
            dist = min([abs(on_times[k] - mt) for k in (j - 1, j) if 0 <= k < len(on_times)] or [9])
            if dist <= 0.045:
                ok += 1
            else:
                far.append((dist, it))
        synced = ok / max(1, len(real))
        info.append(f"audio sync: {ok}/{len(real)} notes ({synced * 100:.0f}%) sit within 45 ms of a detected onset")
        far.sort(key=lambda x: -x[0])
        for dist, it in far[:12]:
            info.append(f"  no onset near {where(it)} (nearest {dist * 1000:.0f} ms) - intended (sustain/filler) or misplaced?")
        # loud bars left empty
        nb = analysis["n_bars"]
        counts = [0] * nb
        for it in real:
            bar = int(it[4] // analysis["beats_per_bar"])
            if 0 <= bar < nb:
                counts[bar] += 1
        empty = [b for b in range(nb) if counts[b] == 0 and analysis["bar_energy"][b] > 0.35]
        if empty:
            info.append(f"bars with music but no notes: {_ranges(empty)}")

    # ---- stats
    by_type = defaultdict(int)
    for it in real:
        by_type[rpe.NOTE_TYPES[it[3]["type"]]] += 1
    stats = {
        "notes": len(real), "fake": len(items) - len(real), "by_type": dict(by_type),
        "duration_s": round((times[-1] - times[0]) if len(times) > 1 else 0, 1),
        "avg_nps": round(len(real) / max(1e-6, (times[-1] - times[0])) if len(times) > 1 else 0, 2),
        "peak_nps_1s": nps_peak, "peak_at_beat": round(bpms.beat(peak_at), 2),
        "lead_time_s": {"min": round(min(leads), 2), "median": round(sorted(leads)[len(leads) // 2], 2),
                        "max": round(max(leads), 2)} if leads else {},
        "sync_ratio": None if synced is None else round(synced, 3),
        "lines": len(lines),
    }
    if analysis:
        per_sec = []
        for s in analysis["sections"]:
            ns = [it for it in real if s["start_beat"] <= it[4] < s["end_beat"]]
            dur = max(1e-6, bpms.time(s["end_beat"]) - bpms.time(s["start_beat"]))
            per_sec.append({"section": s["id"], "label": s["label"], "beats": f"{s['start_beat']}-{s['end_beat']}",
                            "notes": len(ns), "nps": round(len(ns) / dur, 2)})
        stats["sections"] = per_sec
    return {"errors": _cap(errs, max_items), "warnings": _cap(warns, max_items), "info": info, "stats": stats}


def _cap(lst, n):
    if len(lst) > n:
        return lst[:n] + [f"... and {len(lst) - n} more"]
    return lst


def _ranges(nums):
    out = []
    start = prev = None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = n
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def format_report(rep: dict) -> str:
    lines = []
    for key, title in (("errors", "ERRORS (must fix)"), ("warnings", "WARNINGS (should fix or justify)"), ("info", "INFO")):
        lines.append(f"## {title}: {len([x for x in rep[key] if not x.startswith('...')])}")
        lines += [f"- {x}" for x in rep[key]]
        lines.append("")
    st = rep.get("stats") or {}
    if st:
        lines.append("## STATS")
        for k, v in st.items():
            if k == "sections":
                lines.append("- per section:")
                for s in v:
                    lines.append(f"  - sec {s['section']} [{s['label']}] beats {s['beats']}: {s['notes']} notes, {s['nps']} nps")
            else:
                lines.append(f"- {k}: {v}")
    return "\n".join(lines) + "\n"
