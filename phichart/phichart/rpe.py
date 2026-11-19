"""RPE (Re:PhiEdit) JSON chart model, as consumed by Phira (prpr/src/parse/rpe.rs).

The framework lets the model write *relaxed* RPE: times may be floats / "12+1/2"
strings, note types may be names, and most note fields may be omitted.
``normalize()`` turns that into strict RPE that Phira loads.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Iterator

from .timing import BpmList, beat_to_triple, triple_to_beat

RPE_W = 1350.0
RPE_H = 900.0
HEIGHT_RATIO = 0.83175
SPEED_RATIO = 10.0 / 45.0 / HEIGHT_RATIO           # prpr const
SPEED_PX_PER_SEC = SPEED_RATIO * RPE_H / 2.0        # RPE px per second for speed value 1 (~120.2)
NOTE_WIDTH = RPE_W * 0.13175016                     # on-screen note width in RPE x units (~178)

NOTE_TYPES = {1: "tap", 2: "hold", 3: "flick", 4: "drag"}
NOTE_TYPE_IDS = {"tap": 1, "click": 1, "hold": 2, "flick": 3, "drag": 4}
EVENT_KINDS = ("moveXEvents", "moveYEvents", "rotateEvents", "alphaEvents", "speedEvents")

NOTE_DEFAULTS = {
    "above": 1, "alpha": 255, "isFake": 0, "positionX": 0.0, "size": 1.0,
    "speed": 1.0, "visibleTime": 999999.0, "yOffset": 0.0,
}

# ---------------------------------------------------------------- easing (prpr tween.rs)
def _sine(x): return 1 - math.cos(x * math.pi / 2)
def _quad(x): return x * x
def _cubic(x): return x ** 3
def _quart(x): return x ** 4
def _quint(x): return x ** 5
def _expo(x): return 2 ** (10 * (x - 1))
def _circ(x): return 1 - math.sqrt(max(0.0, 1 - x * x))
def _back(x):
    c1 = 1.70158
    return ((c1 + 1) * x - c1) * x * x
def _elastic(x):
    c4 = 2 * math.pi / 3
    return -(2 ** (10 * x - 10)) * math.sin((x * 10 - 10.75) * c4)
def _bounce(x):
    n1, d1 = 7.5625, 2.75
    x = 1 - x
    if x < 1 / d1: v = n1 * x * x
    elif x < 2 / d1: v = n1 * (x - 1.5 / d1) ** 2 + 0.75
    elif x < 2.5 / d1: v = n1 * (x - 2.25 / d1) ** 2 + 0.9375
    else: v = n1 * (x - 2.625 / d1) ** 2 + 0.984375
    return 1 - v

def _in(f): return f
def _out(f): return lambda x: 1 - f(1 - x)
def _inout(f): return lambda x: f(2 * x) / 2 if x < 0.5 else 1 - f(2 - 2 * x) / 2

_lin = lambda x: x
# RPE easingType -> function (prpr RPE_TWEEN_MAP)
RPE_EASINGS = [
    _lin, _lin,
    _out(_sine), _in(_sine), _out(_quad), _in(_quad), _inout(_sine), _inout(_quad),
    _out(_cubic), _in(_cubic), _out(_quart), _in(_quart), _inout(_cubic), _inout(_quart),
    _out(_quint), _in(_quint), _out(_expo), _in(_expo), _out(_circ), _in(_circ),
    _out(_back), _in(_back), _inout(_circ), _inout(_back), _out(_elastic), _in(_elastic),
    _out(_bounce), _in(_bounce), _inout(_bounce), _inout(_elastic),
]
EASING_NAMES = [
    "linear", "linear", "outSine", "inSine", "outQuad", "inQuad", "inOutSine", "inOutQuad",
    "outCubic", "inCubic", "outQuart", "inQuart", "inOutCubic", "inOutQuart", "outQuint", "inQuint",
    "outExpo", "inExpo", "outCirc", "inCirc", "outBack", "inBack", "inOutCirc", "inOutBack",
    "outElastic", "inElastic", "outBounce", "inBounce", "inOutBounce", "inOutElastic",
]


def ease(easing_type: int, x: float, left: float = 0.0, right: float = 1.0) -> float:
    f = RPE_EASINGS[easing_type] if 0 <= easing_type < len(RPE_EASINGS) else _lin
    left, right = max(0.0, min(1.0, left)), max(0.0, min(1.0, right))
    if easing_type > 1 and right > left and not (left == 0 and right == 1):
        a, b = f(left), f(right)
        if abs(b - a) > 1e-9:
            return (f(left + (right - left) * x) - a) / (b - a)
    return f(x)


# ---------------------------------------------------------------- io
def load(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dumps_compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))


def dumps(chart: dict) -> str:
    """Readable layout: one note / one event per line (easy to grep & edit)."""
    out = ["{"]
    keys = list(chart.keys())
    for ki, key in enumerate(keys):
        val = chart[key]
        tail = "," if ki < len(keys) - 1 else ""
        if key == "judgeLineList":
            out.append(f'  "judgeLineList": [')
            for li, line in enumerate(val):
                out.append("    {")
                lkeys = list(line.keys())
                for lk_i, lk in enumerate(lkeys):
                    lv = line[lk]
                    ltail = "," if lk_i < len(lkeys) - 1 else ""
                    if lk == "notes":
                        out.append('      "notes": [')
                        for ni, n in enumerate(lv):
                            out.append("        " + _dumps_compact(n) + ("," if ni < len(lv) - 1 else ""))
                        out.append("      ]" + ltail)
                    elif lk == "eventLayers":
                        out.append('      "eventLayers": [')
                        for ei, layer in enumerate(lv):
                            if layer is None:
                                out.append("        null" + ("," if ei < len(lv) - 1 else ""))
                                continue
                            out.append("        {")
                            ek = list(layer.keys())
                            for eki, kind in enumerate(ek):
                                evs = layer[kind]
                                out.append(f'          "{kind}": [')
                                for evi, ev in enumerate(evs or []):
                                    out.append("            " + _dumps_compact(ev) + ("," if evi < len(evs) - 1 else ""))
                                out.append("          ]" + ("," if eki < len(ek) - 1 else ""))
                            out.append("        }" + ("," if ei < len(lv) - 1 else ""))
                        out.append("      ]" + ltail)
                    else:
                        out.append(f"      {json.dumps(lk)}: {_dumps_compact(lv)}{ltail}")
                out.append("    }" + ("," if li < len(val) - 1 else ""))
            out.append("  ]" + tail)
        else:
            out.append(f"  {json.dumps(key)}: {_dumps_compact(val)}{tail}")
    out.append("}")
    return "\n".join(out) + "\n"


def save(chart: dict, path) -> None:
    Path(path).write_text(dumps(chart), encoding="utf-8")


# ---------------------------------------------------------------- construction
def make_event(start, end, v0, v1=None, easing: int = 1) -> dict:
    return {
        "startTime": beat_to_triple(float(start)) if not isinstance(start, list) else start,
        "endTime": beat_to_triple(float(end)) if not isinstance(end, list) else end,
        "start": v0, "end": v0 if v1 is None else v1,
        "easingType": easing, "easingLeft": 0.0, "easingRight": 1.0,
        "bezier": 0, "bezierPoints": [0.0, 0.0, 0.0, 0.0], "linkgroup": 0,
    }


def make_line(name="main", y=-270.0, speed=7.0, alpha=255, x=0.0, rotate=0.0) -> dict:
    return {
        "Name": name, "Texture": "line.png", "father": -1, "isCover": 1, "zOrder": 0,
        "Group": 0, "bpmfactor": 1.0, "rotateWithFather": False,
        "eventLayers": [{
            "moveXEvents": [make_event(0, 1, x)],
            "moveYEvents": [make_event(0, 1, y)],
            "rotateEvents": [make_event(0, 1, rotate)],
            "alphaEvents": [make_event(0, 1, alpha)],
            "speedEvents": [make_event(0, 1, speed)],
        }],
        "notes": [],
    }


def new_chart(name: str, song: str, bpm: float, offset_ms: int, charter="phichart (AI)",
              composer="", level="IN Lv.12", line_y=-270.0, speed=7.0) -> dict:
    return {
        "META": {
            "RPEVersion": 150, "offset": int(round(offset_ms)), "name": name, "id": "phichart",
            "song": song, "background": "background.png", "charter": charter,
            "composer": composer, "illustration": "", "level": level,
        },
        "BPMList": [{"bpm": float(bpm), "startTime": [0, 0, 1]}],
        "judgeLineGroup": ["Default"],
        "judgeLineList": [make_line("main", y=line_y, speed=speed)],
    }


# ---------------------------------------------------------------- normalisation
class ChartError(Exception):
    pass


def _norm_time(v, where: str, errors: list) -> list[int]:
    try:
        return beat_to_triple(triple_to_beat(v))
    except Exception:
        errors.append(f"{where}: bad time value {v!r} (use [beat, num, den], a number or \"12+1/2\")")
        return [0, 0, 1]


def normalize(chart: dict) -> tuple[dict, list[str], list[str]]:
    """Return (strict_chart, errors, warnings). Does not mutate the input."""
    c = copy.deepcopy(chart)
    errors: list[str] = []
    warnings: list[str] = []
    meta = c.setdefault("META", {})
    meta.setdefault("RPEVersion", 150)
    meta.setdefault("offset", 0)
    if not isinstance(meta.get("offset"), int):
        try:
            meta["offset"] = int(round(float(meta["offset"])))
        except Exception:
            errors.append("META.offset must be an integer (milliseconds)")
    if not c.get("BPMList"):
        errors.append("BPMList is empty")
        c["BPMList"] = [{"bpm": 120.0, "startTime": [0, 0, 1]}]
    for i, b in enumerate(c["BPMList"]):
        b["startTime"] = _norm_time(b.get("startTime", [0, 0, 1]), f"BPMList[{i}]", errors)
        b["bpm"] = float(b.get("bpm", 120))
    c["BPMList"].sort(key=lambda b: triple_to_beat(b["startTime"]))
    c.setdefault("judgeLineGroup", ["Default"])
    # Noise areas (噪域, Phigros blockAreaList) are NOT supported by official Phira (TeamFlos/phira):
    # its RPE parser ignores the field, so it would silently do nothing. normalize() drops it.
    for key in ("blockAreaList", "blockAreas", "noiseAreas"):
        if key in c:
            warnings.append(f"top-level '{key}' (噪域/noise areas) is ignored by official Phira; removed")
            del c[key]
    lines = c.get("judgeLineList")
    if not lines:
        errors.append("judgeLineList is empty")
        c["judgeLineList"] = []
    for li, line in enumerate(c["judgeLineList"]):
        where = f"line {li}"
        line.setdefault("Name", f"line{li}")
        line.setdefault("Texture", "line.png")
        tex = str(line.get("Texture"))
        if tex.lower().startswith("issubtract"):
            errors.append(f"{where}: Texture '{tex}' is a Line2Area noise-area (噪域) carrier line; official Phira has no "
                          "noise areas and would try to load it as an image - remove this line")
        elif tex != "line.png":
            errors.append(f"{where}: Texture '{tex}' needs an image file that phichart does not package; use \"line.png\"")
        line.setdefault("father", -1)
        line.setdefault("isCover", 1)
        line.setdefault("zOrder", 0)
        line.setdefault("Group", 0)
        line.setdefault("bpmfactor", 1.0)
        layers = line.get("eventLayers") or []
        if not layers:
            errors.append(f"{where}: eventLayers is empty (needs at least moveX/moveY/rotate/alpha/speed events)")
        for lai, layer in enumerate(layers):
            if layer is None:
                continue
            for kind in list(layer.keys()):
                evs = layer[kind]
                if evs is None:
                    continue
                for ei, ev in enumerate(evs):
                    w = f"{where} layer {lai} {kind}[{ei}]"
                    ev["startTime"] = _norm_time(ev.get("startTime", [0, 0, 1]), w, errors)
                    ev["endTime"] = _norm_time(ev.get("endTime", ev["startTime"]), w, errors)
                    if "start" not in ev:
                        errors.append(f"{w}: missing 'start'")
                        ev["start"] = 0.0
                    ev.setdefault("end", ev["start"])
                    ev.setdefault("easingType", 1)
                    ev.setdefault("easingLeft", 0.0)
                    ev.setdefault("easingRight", 1.0)
                    ev.setdefault("bezier", 0)
                    ev.setdefault("bezierPoints", [0.0, 0.0, 0.0, 0.0])
                    ev.setdefault("linkgroup", 0)
                    if triple_to_beat(ev["endTime"]) < triple_to_beat(ev["startTime"]):
                        errors.append(f"{w}: endTime before startTime")
                evs.sort(key=lambda e: triple_to_beat(e["startTime"]))
                for a, b in zip(evs, evs[1:]):
                    if triple_to_beat(b["startTime"]) < triple_to_beat(a["endTime"]) - 1e-6:
                        warnings.append(f"{where} layer {lai} {kind}: overlapping events at beat "
                                        f"{triple_to_beat(b['startTime']):g} (later one wins inconsistently)")
                if evs and lai == 0 and triple_to_beat(evs[0]["startTime"]) > 1e-6:
                    warnings.append(f"{where} {kind}: first event starts at beat {triple_to_beat(evs[0]['startTime']):g}; "
                                    "Phira extrapolates before the first event - start every event list at beat 0")
        if layers and layers[0] is not None:
            for kind in EVENT_KINDS:
                if not layers[0].get(kind):
                    warnings.append(f"{where}: layer 0 has no {kind}")
        notes = line.get("notes") or []
        new_notes = []
        for ni, n in enumerate(notes):
            w = f"{where} note[{ni}]"
            t = n.get("type", 1)
            if isinstance(t, str):
                if t.lower() not in NOTE_TYPE_IDS:
                    errors.append(f"{w}: unknown note type {t!r}")
                    continue
                t = NOTE_TYPE_IDS[t.lower()]
            if t not in NOTE_TYPES:
                errors.append(f"{w}: unknown note type {t!r} (1 tap, 2 hold, 3 flick, 4 drag)")
                continue
            n["type"] = t
            if "startTime" not in n:
                errors.append(f"{w}: missing startTime")
                continue
            n["startTime"] = _norm_time(n["startTime"], w, errors)
            if t == 2:
                if "endTime" not in n:
                    errors.append(f"{w}: hold without endTime")
                    n["endTime"] = n["startTime"]
                n["endTime"] = _norm_time(n["endTime"], w, errors)
                if triple_to_beat(n["endTime"]) <= triple_to_beat(n["startTime"]):
                    errors.append(f"{w}: hold endTime must be after startTime")
            else:
                n["endTime"] = list(n["startTime"])
            for k, v in NOTE_DEFAULTS.items():
                n.setdefault(k, v)
            for k in ("positionX", "size", "speed", "yOffset", "visibleTime"):
                n[k] = float(n[k])
            n["above"] = int(n["above"])
            n["alpha"] = int(n["alpha"])
            n["isFake"] = int(n["isFake"])
            if abs(n["positionX"]) > RPE_W / 2:
                warnings.append(f"{w} @beat {triple_to_beat(n['startTime']):g}: positionX {n['positionX']:g} is off screen (|x| must be <= 675)")
            new_notes.append(n)
        new_notes.sort(key=lambda n: (triple_to_beat(n["startTime"]), n["positionX"]))
        line["notes"] = new_notes
        line["numOfNotes"] = sum(1 for n in new_notes if not n["isFake"])
        if line["father"] not in (-1, None) and not (0 <= int(line["father"]) < len(c["judgeLineList"])):
            errors.append(f"{where}: father {line['father']} does not exist")
    return c, errors, warnings


def normalize_strict(chart: dict) -> dict:
    c, errors, _ = normalize(chart)
    if errors:
        raise ChartError("\n".join(errors))
    return c


# ---------------------------------------------------------------- queries
def bpm_list(chart: dict) -> BpmList:
    return BpmList.from_rpe(chart["BPMList"])


def iter_notes(chart: dict) -> Iterator[tuple[int, int, dict, float, float]]:
    for li, line in enumerate(chart.get("judgeLineList", [])):
        for ni, n in enumerate(line.get("notes") or []):
            b = triple_to_beat(n["startTime"])
            e = triple_to_beat(n.get("endTime", n["startTime"]))
            yield li, ni, n, b, e


def event_value(events: list[dict] | None, beat: float, default: float = 0.0) -> float:
    """Value of one RPE event list at `beat` (beats-domain approximation of prpr Anim)."""
    if not events:
        return default
    cur = None
    for ev in events:
        if triple_to_beat(ev["startTime"]) <= beat:
            cur = ev
        else:
            break
    if cur is None:
        cur = events[0]
    s, e = triple_to_beat(cur["startTime"]), triple_to_beat(cur["endTime"])
    v0, v1 = cur["start"], cur["end"]
    if not isinstance(v0, (int, float)):
        return default
    if beat >= e or e - s < 1e-9:
        return float(v1)
    x = (beat - s) / (e - s)
    if cur.get("easingType", 1) == 0:
        return float(v0)
    return float(v0 + (v1 - v0) * ease(int(cur.get("easingType", 1)), x,
                                       cur.get("easingLeft", 0.0), cur.get("easingRight", 1.0)))


def line_value(line: dict, kind: str, beat: float) -> float:
    """Sum over event layers (prpr chains layers additively)."""
    total = 0.0
    any_ = False
    for layer in line.get("eventLayers") or []:
        if layer and layer.get(kind):
            total += event_value(layer[kind], beat)
            any_ = True
    if not any_ and kind == "alphaEvents":
        return 255.0
    return total


def line_state(line: dict, beat: float) -> dict:
    return {
        "x": line_value(line, "moveXEvents", beat),
        "y": line_value(line, "moveYEvents", beat),
        "rot": line_value(line, "rotateEvents", beat),
        "alpha": line_value(line, "alphaEvents", beat),
        "speed": line_value(line, "speedEvents", beat),
    }


def note_lead_time(chart: dict, li: int, note: dict, bpms: BpmList | None = None, step: float = 0.01,
                   limit: float = 6.0) -> float:
    """Seconds between a note entering the screen and reaching its line.

    Integrates the line's speed (legacy linear speed mode) backwards from the hit time
    and compares with the distance from the line to the screen edge (static-line approximation).
    """
    bpms = bpms or bpm_list(chart)
    line = chart["judgeLineList"][li]
    tb = triple_to_beat(note["startTime"])
    t_hit = bpms.time(tb)
    st = line_state(line, tb)
    # distance from line (along its normal) to the far screen edge on the note's side
    rad = math.radians(st["rot"])
    nx, ny = -math.sin(-rad), math.cos(-rad)  # RPE rotation is clockwise-positive
    if not note.get("above", 1):
        nx, ny = -nx, -ny
    px, py = st["x"] + note.get("positionX", 0) * math.cos(rad), st["y"] - note.get("positionX", 0) * math.sin(rad)
    ds = []
    if abs(nx) > 1e-6:
        ds.append(((RPE_W / 2 if nx > 0 else -RPE_W / 2) - px) / nx)
    if abs(ny) > 1e-6:
        ds.append(((RPE_H / 2 if ny > 0 else -RPE_H / 2) - py) / ny)
    dist = min(d for d in ds if d > 0) if any(d > 0 for d in ds) else RPE_H
    nspeed = float(note.get("speed", 1.0)) or 1e-6
    travelled = 0.0
    t = t_hit
    while t > t_hit - limit:
        b = bpms.beat(t - step / 2)
        v = line_value(line, "speedEvents", b) * SPEED_PX_PER_SEC * nspeed
        travelled += v * step
        t -= step
        if travelled >= dist:
            return t_hit - t
        if t < 0:
            break
    return t_hit - max(t, 0.0)
