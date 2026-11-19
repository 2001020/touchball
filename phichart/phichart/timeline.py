"""Editor-style overview: notes on a beat axis next to the detected onsets.

Time runs upwards inside each column (like a chart editor / like notes falling onto the line).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import rpe
from .engine import font
from .timing import fmt_beat

COL_W = 300          # note area width per column
LANE_W = 78          # onset lanes width per column
PX_PER_BEAT = 96
COLORS = {1: (80, 170, 255), 2: (80, 170, 255), 3: (255, 80, 100), 4: (245, 215, 70)}
LANE_LAYERS = (("kick", (255, 110, 90)), ("snare", (120, 220, 120)), ("hat", (190, 190, 190)),
               ("melody", (110, 160, 255)), ("bass", (200, 130, 255)))


def render_timeline(chart: dict, analysis: dict | None, start: float, end: float, out: Path,
                    beats_per_col: int = 8, highlight: tuple[float, float] | None = None) -> Path:
    start = float(start)
    end = float(end)
    n_cols = max(1, int(-(-(end - start) // beats_per_col)))
    col_h = beats_per_col * PX_PER_BEAT
    top_pad, bot_pad = 34, 26
    W = n_cols * (COL_W + LANE_W + 18) + 10
    H = col_h + top_pad + bot_pad
    im = Image.new("RGB", (W, H), (22, 22, 28))
    d = ImageDraw.Draw(im, "RGBA")
    f_small, f_med = font(11), font(14)
    d.text((8, 6), f"timeline beats {fmt_beat(start)}-{fmt_beat(end)}   tap=blue  drag=yellow  flick=red  hold=blue bar  "
                   f"white outline=simultaneous  'v'=below-line  lanes: K S H M B onsets", fill=(230, 230, 230), font=f_med)

    notes = [(li, n, b, e) for li, _, n, b, e in rpe.iter_notes(chart) if e >= start - 1e-6 and b < end + 1e-6]
    times_count: dict[float, int] = {}
    for _, n, b, _ in notes:
        if not n.get("isFake"):
            times_count[round(b, 4)] = times_count.get(round(b, 4), 0) + 1
    multi_line = len(chart.get("judgeLineList", [])) > 1
    bpms = rpe.bpm_list(chart)

    for c in range(n_cols):
        cb0 = start + c * beats_per_col
        cb1 = cb0 + beats_per_col
        x0 = 10 + c * (COL_W + LANE_W + 18)
        lane_x = x0
        note_x = x0 + LANE_W + 4

        def y_of(beat):
            return top_pad + col_h - (beat - cb0) * PX_PER_BEAT

        d.rectangle([note_x, top_pad, note_x + COL_W, top_pad + col_h], fill=(30, 30, 38))
        if highlight:
            h0, h1 = max(highlight[0], cb0), min(highlight[1], cb1)
            if h1 > h0:
                d.rectangle([note_x, y_of(h1), note_x + COL_W, y_of(h0)], fill=(255, 220, 120, 28))
        # grid
        q = cb0
        while q <= cb1 + 1e-6:
            y = y_of(q)
            if abs(q - round(q)) < 1e-6:
                is_bar = int(round(q)) % 4 == 0
                d.line([(lane_x, y), (note_x + COL_W, y)], fill=(200, 200, 210) if is_bar else (90, 90, 100), width=2 if is_bar else 1)
                lab = f"{int(round(q))}" + (f" (bar {int(round(q)) // 4})" if is_bar else "")
                d.text((note_x + COL_W - (70 if is_bar else 22), y - 13), lab, fill=(200, 200, 210), font=f_small)
            else:
                d.line([(note_x, y), (note_x + COL_W, y)], fill=(50, 50, 58), width=1)
            q += 0.25
        for xv in (-450, -225, 0, 225, 450):
            px = note_x + (xv / rpe.RPE_W + 0.5) * COL_W
            d.line([(px, top_pad), (px, top_pad + col_h)], fill=(45, 45, 55), width=1)
        d.text((note_x + 2, top_pad + col_h + 4), "x: -675 ... 0 ... 675", fill=(120, 120, 130), font=f_small)
        # onset lanes
        if analysis:
            lw = LANE_W / len(LANE_LAYERS)
            for i, (layer, col) in enumerate(LANE_LAYERS):
                lx = lane_x + i * lw
                d.text((lx + 3, top_pad - 14), layer[0].upper(), fill=col, font=f_small)
                for o in analysis["onsets"].get(layer, []):
                    if cb0 - 0.01 <= o["raw"] < cb1 and o["s"] >= 0.15:
                        y = y_of(o["raw"])
                        w = max(2, min(lw - 2, lw * min(1.0, o["s"])))
                        d.rectangle([lx + 1, y - 1.5, lx + 1 + w, y + 1.5], fill=col + (int(110 + 145 * min(1, o["s"])),))
        # notes
        for li, n, b, e in notes:
            if e < cb0 - 1e-6 or b >= cb1:
                continue
            col = COLORS.get(n["type"], (255, 255, 255))
            alpha = 90 if n.get("isFake") else 255
            px = note_x + (float(n.get("positionX", 0)) / rpe.RPE_W + 0.5) * COL_W
            hw = rpe.NOTE_WIDTH / rpe.RPE_W * COL_W / 2 * float(n.get("size", 1.0))
            if n["type"] == 2:
                yb, ye = y_of(max(b, cb0)), y_of(min(e, cb1))
                d.rectangle([px - hw * 0.8, ye, px + hw * 0.8, yb], fill=col + (110,))
                if b >= cb0:
                    d.rectangle([px - hw, yb - 4, px + hw, yb + 4], fill=col + (alpha,))
            else:
                if b < cb0:
                    continue
                y = y_of(b)
                hh = 3 if n["type"] == 4 else 4
                d.rectangle([px - hw, y - hh, px + hw, y + hh], fill=col + (alpha,))
                if n["type"] == 3:
                    d.polygon([(px - 5, y - hh), (px + 5, y - hh), (px, y - hh - 7)], fill=col + (alpha,))
            if b >= cb0 and times_count.get(round(b, 4), 0) > 1 and not n.get("isFake"):
                y = y_of(b)
                d.rectangle([px - hw - 1, y - 6, px + hw + 1, y + 6], outline=(255, 255, 255, 220), width=1)
            if b >= cb0:
                tag = ("v" if not n.get("above", 1) else "") + (f"L{li}" if multi_line else "")
                if tag:
                    d.text((px + hw + 2, y_of(b) - 7), tag, fill=(255, 255, 255), font=f_small)
        # line speed annotations at bar starts
        for li, line in enumerate(chart.get("judgeLineList", [])):
            last = None
            for bb in range(int(cb0), int(cb1)):
                if bb % 4:
                    continue
                st = rpe.line_state(line, bb)
                lab = f"L{li} spd {st['speed']:.1f}" + (f" y{st['y']:.0f}" if abs(st['y'] + 270) > 1 else "")
                if lab != last and (li == 0 or rpe.line_value(line, 'alphaEvents', bb) > 0):
                    d.text((note_x + 3, y_of(bb) - 13 - 11 * li), lab, fill=(140, 200, 140), font=f_small)
                last = lab
        d.text((x0, top_pad + col_h + 4), f"t={bpms.time(cb0) + chart['META'].get('offset', 0) / 1000:.1f}s",
               fill=(120, 120, 130), font=f_small)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
