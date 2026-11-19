"""Beat/time helpers mirroring prpr's BpmList and RPE beat triples.

RPE stores every time as a *beat triple* ``[i, n, d]`` meaning ``i + n/d`` beats
(``i`` is a whole beat index, NOT a bar index).
"""
from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import Iterable, Sequence

MAX_DEN = 48  # 1/16, 1/12, 1/24, 1/32 and 1/48 grids are all representable


def triple_to_beat(t) -> float:
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        return parse_beat(t)
    i, n, d = t
    return float(i) + (float(n) / float(d) if d else 0.0)


def beat_to_triple(beat: float, max_den: int = MAX_DEN) -> list[int]:
    fr = Fraction(beat).limit_denominator(max_den)
    i = math.floor(fr)
    rem = fr - i
    if rem == 0:
        return [int(i), 0, 1]
    return [int(i), rem.numerator, rem.denominator]


_BEAT_RE = re.compile(r"^\s*(-?\d+)\s*(?:[+:]\s*(\d+)\s*/\s*(\d+))?\s*$")


def parse_beat(s) -> float:
    """Accept 12, 12.5, "12.5", "12+1/2", "12:1/2", "1/3", [12,1,2]."""
    if isinstance(s, (list, tuple)):
        return triple_to_beat(s)
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    m = _BEAT_RE.match(s)
    if m:
        i = int(m.group(1))
        if m.group(2):
            return i + int(m.group(2)) / int(m.group(3))
        return float(i)
    if "/" in s and "+" not in s and ":" not in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)


def fmt_beat(beat: float) -> str:
    i, n, d = beat_to_triple(beat)
    return f"{i}" if n == 0 else f"{i}+{n}/{d}"


class BpmList:
    """Same maths as prpr::core::BpmList (piecewise-constant BPM)."""

    def __init__(self, items: Sequence[tuple[float, float]]):
        items = sorted(items, key=lambda it: it[0]) or [(0.0, 120.0)]
        self.elements: list[tuple[float, float, float]] = []  # (beats, time, bpm)
        time = 0.0
        last_beats = 0.0
        last_bpm = None
        for beats, bpm in items:
            if last_bpm is not None:
                time += (beats - last_beats) * 60.0 / last_bpm
            last_beats = beats
            last_bpm = bpm
            self.elements.append((beats, time, bpm))

    @classmethod
    def from_rpe(cls, bpm_list: Iterable[dict]) -> "BpmList":
        return cls([(triple_to_beat(it["startTime"]), float(it["bpm"])) for it in bpm_list])

    def time(self, beats: float) -> float:
        el = self.elements[0]
        for e in self.elements:
            if e[0] <= beats:
                el = e
            else:
                break
        return el[1] + (beats - el[0]) * 60.0 / el[2]

    def beat(self, time: float) -> float:
        el = self.elements[0]
        for e in self.elements:
            if e[1] <= time:
                el = e
            else:
                break
        return el[0] + (time - el[1]) * el[2] / 60.0

    def bpm_at(self, beats: float) -> float:
        el = self.elements[0]
        for e in self.elements:
            if e[0] <= beats:
                el = e
        return el[2]
