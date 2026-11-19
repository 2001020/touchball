"""phichart command line.  Run `phichart -h` or `phichart <cmd> -h`."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from . import rpe
from .timing import fmt_beat, parse_beat

PKG_ROOT = Path(__file__).resolve().parent.parent
GUIDE = PKG_ROOT / "GUIDE.md"


# ------------------------------------------------------------------ workspace helpers
def _ws(path) -> Path:
    w = Path(path)
    if not (w / "chart.json").exists():
        sys.exit(f"error: {w} is not a phichart workspace (no chart.json). Run `phichart init` first.")
    return w


def _meta(w: Path) -> dict:
    p = w / "workspace.json"
    return json.loads(p.read_text()) if p.exists() else {"song": "song.ogg"}


def _music(w: Path) -> Path:
    return w / _meta(w).get("song", "song.ogg")


def _load_chart(w: Path, strict=True, path: Path | None = None) -> dict:
    p = path or (w / "chart.json")
    try:
        raw = rpe.load(p)
    except json.JSONDecodeError as exc:
        sys.exit(f"error: {p} is not valid JSON: {exc}")
    chart, errors, warnings = rpe.normalize(raw)
    if errors and strict:
        print("chart has format errors:\n" + "\n".join(f"  - {e}" for e in errors[:30]), file=sys.stderr)
        sys.exit(2)
    return chart


def _analysis(w: Path):
    from .audio import load_analysis
    return load_analysis(w)


def _history(w: Path) -> list[Path]:
    h = w / "history"
    return sorted(h.glob("*.json")) if h.exists() else []


def _checkpoint(w: Path, msg: str = "") -> Path:
    h = w / "history"
    h.mkdir(exist_ok=True)
    n = len(_history(w)) + 1
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in msg)[:40]
    dst = h / f"{n:04d}_{time.strftime('%H%M%S')}{'_' + safe if safe else ''}.json"
    shutil.copy(w / "chart.json", dst)
    return dst


def _resolve_compare(w: Path, spec: str | None):
    if not spec:
        return None
    if spec.startswith("@"):
        hist = _history(w)
        if not hist:
            sys.exit("error: no checkpoints yet (run `phichart checkpoint`)")
        k = 1 if spec in ("@prev", "@last") else int(spec[1:])
        return _load_chart(w, path=hist[-k])
    return _load_chart(w, path=Path(spec))


def _make_background(path: Path, title: str):
    from PIL import Image, ImageDraw
    from .engine import font
    W, H = 1920, 1080
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(30 + 40 * k), int(26 + 20 * k), int(60 + 50 * (1 - k))))
    d.text((80, H - 140), title, fill=(120, 120, 150), font=font(56))
    im.save(path)


# ------------------------------------------------------------------ commands
def cmd_init(a):
    from .audio import analyze
    src = Path(a.audio)
    if not src.exists():
        sys.exit(f"error: {src} not found")
    w = Path(a.out)
    if (w / "chart.json").exists() and not a.force:
        sys.exit(f"error: {w} already has a chart.json (use --force to overwrite)")
    w.mkdir(parents=True, exist_ok=True)
    song = w / "song.ogg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ar", "44100", "-c:a", "libvorbis",
                    "-q:a", "6", str(song)], check=True)
    name = a.name or src.stem
    print(f"[init] analysing {src.name} ...")
    res = analyze(song, w / "analysis", bpm=a.bpm, offset_ms=a.offset_ms, downbeat_shift=a.downbeat_shift)
    chart = rpe.new_chart(name, "song.ogg", res["bpm"], res["offset_ms"], composer=a.composer or "",
                          level=a.level, speed=6.5)
    rpe.save(chart, w / "chart.json")
    (w / "workspace.json").write_text(json.dumps({
        "name": name, "song": "song.ogg", "source_audio": str(src.resolve()), "level": a.level,
        "composer": a.composer or "", "created": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2, ensure_ascii=False))
    _make_background(w / "background.png", name)
    if GUIDE.exists():
        shutil.copy(GUIDE, w / "GUIDE.md")
    if not (w / "PLAN.md").exists():
        (w / "PLAN.md").write_text(PLAN_TEMPLATE.format(name=name, bpm=res["bpm"], offset=res["offset_ms"],
                                                         bars=res["n_bars"], level=a.level), encoding="utf-8")
    print(f"[init] workspace ready: {w}")
    print(f"       BPM {res['bpm']}  offset {res['offset_ms']} ms  bars {res['n_bars']}  sections {len(res['sections'])}")
    print(f"       read {w / 'GUIDE.md'}, {w / 'analysis/summary.md'}, {w / 'analysis/bars.txt'}")


PLAN_TEMPLATE = """# Chart plan: {name}

Target difficulty: {level}
BPM {bpm}, offset {offset} ms, {bars} bars.

## 1. Sections (verify/adjust the auto-detected ones by listening-through-analysis + timeline renders)
| section | bars | beats | character | layer(s) to follow | density target (nps) | flow speed | line motion |
|---|---|---|---|---|---|---|---|

## 2. Sampling (采音) decisions
- main layer per section, what is deliberately NOT charted, where holds/flicks/drags/doubles go

## 3. Motifs / recurring patterns (same sound -> same pattern)

## 4. Progress log (section done? reviewed with snap + timeline? lint clean?)
"""


def cmd_analyze(a):
    from .audio import analyze
    w = _ws(a.work)
    res = analyze(_music(w), w / "analysis", bpm=a.bpm, offset_ms=a.offset_ms, downbeat_shift=a.downbeat_shift)
    print(f"BPM {res['bpm']}  offset {res['offset_ms']} ms  bars {res['n_bars']}")
    if a.update_chart:
        raw = rpe.load(w / "chart.json")
        n_notes = sum(len(l.get("notes") or []) for l in raw["judgeLineList"])
        if n_notes and not a.force:
            sys.exit("chart already has notes; changing BPM/offset moves them. Re-run with --force to update anyway.")
        _checkpoint(w, "before_reanalyze")
        raw["BPMList"] = [{"bpm": res["bpm"], "startTime": [0, 0, 1]}]
        raw["META"]["offset"] = res["offset_ms"]
        rpe.save(raw, w / "chart.json")
        print("chart.json BPMList / META.offset updated")


def cmd_onsets(a):
    w = _ws(a.work)
    an = _analysis(w)
    if not an:
        sys.exit("no analysis; run `phichart analyze`")
    b0, b1 = parse_beat(a.start), parse_beat(a.end)
    if a.rank:
        _onsets_rank(an, b0, b1, a.rank, a.weights)
        return
    layers = a.layers.split(",") if a.layers else ["kick", "snare", "hat", "melody", "bass"]
    rows: dict[float, dict] = {}
    for k in layers:
        for o in an["onsets"].get(k, []):
            if b0 - 1e-6 <= o["beat"] < b1 and o["s"] >= a.min:
                r = rows.setdefault(o["beat"], {})
                if o["s"] > r.get(k, {}).get("s", -1):
                    r[k] = o
    print(f"# onsets beats {fmt_beat(b0)}-{fmt_beat(b1)}, strength>={a.min}; format: beat | layer:strength(...) ; "
          "'len' = sustain in beats (hold candidate if >=1)")
    for beat in sorted(rows):
        parts = []
        for k in layers:
            if k in rows[beat]:
                o = rows[beat][k]
                extra = f" len{o['len_beats']}" if o.get("len_beats", 0) >= 0.75 else ""
                tri = " tri" if o["grid"] == "1/3" else ""
                parts.append(f"{k}:{o['s']:.2f}{extra}{tri}")
        bar, inbar = divmod(beat, 4)
        print(f"{fmt_beat(beat):>9} (bar {int(bar)} +{inbar:<5g}) | " + "  ".join(parts))


def _onsets_rank(an, b0, b1, k, weights):
    w = {"kick": 1.0, "snare": 1.0, "melody": 0.8, "bass": 0.6, "hat": 0.3}
    if weights:
        for part in weights.split(","):
            name, val = part.split("=")
            w[name.strip()] = float(val)
    score: dict[float, float] = {}
    who: dict[float, list] = {}
    for layer, wt in w.items():
        for o in an["onsets"].get(layer, []):
            if b0 - 1e-6 <= o["beat"] < b1 and o["err_ms"] <= 45:
                score[o["beat"]] = score.get(o["beat"], 0.0) + wt * min(1.2, o["s"])
                if o["s"] >= 0.5:
                    who.setdefault(o["beat"], []).append(layer[0].upper())
    bpb = an["beats_per_bar"]
    print(f"# top-{k} candidate positions per bar by weighted salience ({', '.join(f'{x}={v:g}' for x, v in w.items())})")
    print("# format: beat(score letters)  letters = layers with strength>=0.5 (K S M B H); sorted by time")
    bar = int(b0 // bpb)
    while bar * bpb < b1:
        items = [(b, sc) for b, sc in score.items() if bar * bpb <= b < (bar + 1) * bpb]
        top = sorted(sorted(items, key=lambda x: -x[1])[:k])
        txt = "  ".join(f"{fmt_beat(b)}({sc:.1f}{''.join(sorted(set(who.get(b, []))))})" for b, sc in top)
        print(f"bar {bar:>3} [{bar * bpb}-{(bar + 1) * bpb}): {txt}")
        bar += 1


def _parse_beats_list(vals):
    out = []
    for v in vals or []:
        for p in str(v).split(","):
            if p.strip():
                out.append(parse_beat(p))
    return out


def cmd_snap(a):
    from .engine import snap_sheet
    w = _ws(a.work)
    chart = _load_chart(w)
    beats = _parse_beats_list(a.beat)
    if a.around is not None:
        c = parse_beat(a.around)
        offs = [parse_beat(x) for x in a.offsets.split(",")]
        beats += [c + o for o in offs]
    if a.range:
        b0, b1 = parse_beat(a.range[0]), parse_beat(a.range[1])
        x = b0
        while x <= b1 + 1e-9:
            beats.append(x)
            x += a.step
    if not beats:
        sys.exit("give --beat B, --around B or --range B0 B1")
    beats = [max(0.0, b) for b in beats]
    compare = _resolve_compare(w, a.compare)
    out = Path(a.out) if a.out else w / "renders" / f"snap_{fmt_beat(beats[0]).replace('/', '_').replace('+', 'p')}{'_cmp' if compare else ''}.png"
    scale = a.scale if a.scale else (1.0 if len(beats) == 1 and not compare else 0.5)
    snap_sheet(chart, _music(w), beats, out, compare=compare, scale=scale, background=w / "background.png",
               label=a.label or "")
    print(out)


def cmd_timeline(a):
    from .timeline import render_timeline
    w = _ws(a.work)
    chart = _load_chart(w)
    b0, b1 = parse_beat(a.start), parse_beat(a.end)
    hl = (parse_beat(a.highlight[0]), parse_beat(a.highlight[1])) if a.highlight else None
    out = Path(a.out) if a.out else w / "renders" / f"timeline_{fmt_beat(b0).replace('/', '_').replace('+', 'p')}-{fmt_beat(b1).replace('/', '_').replace('+', 'p')}.png"
    render_timeline(chart, _analysis(w), b0, b1, out, beats_per_col=a.cols_beats, highlight=hl)
    print(out)


def cmd_lint(a):
    from .lint import format_report, lint
    w = _ws(a.work)
    raw = rpe.load(w / "chart.json")
    rep = lint(raw, _analysis(w), level=a.level or _meta(w).get("level", "IN").split()[0], max_items=a.max)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(format_report(rep))
    sys.exit(1 if rep["errors"] else 0)


def cmd_stats(a):
    from .lint import lint
    w = _ws(a.work)
    rep = lint(rpe.load(w / "chart.json"), _analysis(w))
    print(json.dumps(rep["stats"], ensure_ascii=False, indent=1))


def cmd_fmt(a):
    w = _ws(a.work)
    raw = rpe.load(w / "chart.json")
    chart, errors, warnings = rpe.normalize(raw)
    for e in errors:
        print("ERROR:", e)
    for x in warnings:
        print("warn:", x)
    if errors:
        sys.exit(2)
    rpe.save(chart, w / "chart.json")
    print("chart.json normalised")


def cmd_notes(a):
    w = _ws(a.work)
    chart = _load_chart(w)
    b0, b1 = parse_beat(a.start), parse_beat(a.end)
    for li, ni, n, b, e in rpe.iter_notes(chart):
        if (a.line is None or li == a.line) and b0 - 1e-9 <= b < b1:
            t = rpe.NOTE_TYPES[n["type"]]
            extra = f" ->{fmt_beat(e)}" if n["type"] == 2 else ""
            flags = "".join([" below" if not n["above"] else "", " fake" if n["isFake"] else "",
                             f" spd{n['speed']:g}" if n["speed"] != 1 else "", f" size{n['size']:g}" if n["size"] != 1 else ""])
            print(f"L{li} #{ni:<4} {fmt_beat(b):>9} {t:<5} x={n['positionX']:>6.0f}{extra}{flags}")


def cmd_splice(a):
    w = _ws(a.work)
    raw = rpe.load(w / "chart.json")
    b0, b1 = parse_beat(a.start), parse_beat(a.end)
    data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    new_notes = data["notes"] if isinstance(data, dict) else data
    if a.line >= len(raw["judgeLineList"]):
        sys.exit(f"error: line {a.line} does not exist")
    # validate new notes in isolation first
    probe = {"META": raw["META"], "BPMList": raw["BPMList"], "judgeLineList": [{"eventLayers": [{}], "notes": new_notes}]}
    _, errors, _ = rpe.normalize(probe)
    errors = [e for e in errors if "note[" in e]
    if errors:
        sys.exit("notes file has errors:\n" + "\n".join(errors))
    for n in new_notes:
        b = rpe.triple_to_beat(n["startTime"])
        if not (b0 - 1e-9 <= b < b1):
            print(f"warning: note at beat {fmt_beat(b)} is outside the splice range {fmt_beat(b0)}-{fmt_beat(b1)}")
    _checkpoint(w, f"before_splice_{fmt_beat(b0)}")
    line = raw["judgeLineList"][a.line]
    old = line.get("notes") or []
    kept = [n for n in old if not (b0 - 1e-9 <= rpe.triple_to_beat(n["startTime"]) < b1)]
    removed = len(old) - len(kept)
    line["notes"] = kept + new_notes
    chart, errors, _ = rpe.normalize(raw)
    rpe.save(chart, w / "chart.json")
    print(f"line {a.line}: removed {removed} notes in [{fmt_beat(b0)}, {fmt_beat(b1)}), inserted {len(new_notes)}; "
          f"line now has {len(chart['judgeLineList'][a.line]['notes'])} notes")


def cmd_checkpoint(a):
    w = _ws(a.work)
    print(_checkpoint(w, a.message or ""))


def cmd_history(a):
    w = _ws(a.work)
    for p in _history(w):
        print(p.name)


def cmd_export(a):
    from .lint import lint
    w = _ws(a.work)
    raw = rpe.load(w / "chart.json")
    chart, errors, _ = rpe.normalize(raw)
    if errors:
        sys.exit("cannot export, chart has errors:\n" + "\n".join(errors[:20]))
    rep = lint(raw, _analysis(w))
    if rep["errors"] and not a.force:
        sys.exit("lint reports errors (run `phichart lint`); fix them or pass --force:\n" + "\n".join(rep["errors"][:10]))
    meta = _meta(w)
    chart["META"]["name"] = meta.get("name", chart["META"].get("name", ""))
    out = Path(a.out) if a.out else w / "export" / "chart.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(chart, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"exported RPE chart: {out}  ({rep['stats'].get('notes', 0)} notes)")
    if a.pez:
        pez = out.with_suffix(".pez")
        level = chart["META"].get("level", "IN Lv.12")
        try:
            diff = float(level.split("Lv.")[-1])
        except ValueError:
            diff = 12.0
        info = "\n".join([
            f"name: {json.dumps(meta.get('name', 'phichart'), ensure_ascii=False)}",
            f"difficulty: {diff}", f"level: {json.dumps(level)}",
            f"charter: {json.dumps(chart['META'].get('charter', 'phichart'), ensure_ascii=False)}",
            f"composer: {json.dumps(meta.get('composer', ''), ensure_ascii=False)}",
            "illustrator: \"\"", "chart: chart.json", "format: rpe", f"music: {_music(w).name}",
            "illustration: background.png", "previewStart: 0.0", "aspectRatio: 1.7777778",
            "backgroundDim: 0.6", "lineLength: 6.0", "offset: 0.0", "tags: []", "intro: \"generated with phichart\"", ""])
        with zipfile.ZipFile(pez, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("chart.json", json.dumps(chart, ensure_ascii=False, separators=(",", ":")))
            z.writestr("info.yml", info)
            z.write(_music(w), _music(w).name)
            if (w / "background.png").exists():
                z.write(w / "background.png", "background.png")
        print(f"Phira package: {pez}")


def cmd_video(a):
    from .engine import render_video
    w = _ws(a.work)
    chart = _load_chart(w)
    out = Path(a.out) if a.out else w / "renders" / "preview.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    render_video(chart, _music(w), out, parse_beat(a.start) if a.start else None, parse_beat(a.end) if a.end else None,
                 fps=a.fps, background=w / "background.png")
    print(out)


def cmd_guide(a):
    print(GUIDE.read_text(encoding="utf-8") if not a.path else GUIDE)


def cmd_make(a):
    from .agent import run_agent
    w = Path(a.out)
    if not (w / "chart.json").exists() or a.force:
        cmd_init(argparse.Namespace(audio=a.audio, out=a.out, name=a.name, composer=a.composer, level=a.level,
                                    bpm=a.bpm, offset_ms=a.offset_ms, downbeat_shift=a.downbeat_shift, force=a.force))
    code = run_agent(w, backend=a.backend, model=a.model, max_turns=a.max_turns, effort=a.effort)
    if code != 0:
        print(f"[make] agent backend exited with code {code}")
    # final gate: export what the model produced
    try:
        cmd_export(argparse.Namespace(work=str(w), out=a.final, pez=True, force=False))
    except SystemExit as exc:
        print(f"[make] export blocked: {exc}")
        return 1
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="phichart", description="AI charting framework for Phira (RPE json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(fn=fn)
        return sp

    def audio_opts(sp):
        sp.add_argument("--bpm", type=float, help="force BPM (skip detection)")
        sp.add_argument("--offset-ms", type=float, help="force time (ms) of beat 0")
        sp.add_argument("--downbeat-shift", type=int, default=0, help="shift detected bar start by N beats")

    sp = add("init", cmd_init, "create a workspace from an audio file (convert, analyse, chart skeleton)")
    sp.add_argument("audio")
    sp.add_argument("--out", required=True)
    sp.add_argument("--name")
    sp.add_argument("--composer")
    sp.add_argument("--level", default="IN Lv.12")
    sp.add_argument("--force", action="store_true")
    audio_opts(sp)

    sp = add("analyze", cmd_analyze, "re-run audio analysis (optionally with forced BPM/offset)")
    sp.add_argument("work")
    audio_opts(sp)
    sp.add_argument("--update-chart", action="store_true", help="write new BPM/offset into chart.json")
    sp.add_argument("--force", action="store_true")

    sp = add("onsets", cmd_onsets, "list detected onsets (quantised beats + strengths) in a beat range")
    sp.add_argument("work")
    sp.add_argument("--from", dest="start", required=True)
    sp.add_argument("--to", dest="end", required=True)
    sp.add_argument("--layers", help="comma list of kick,snare,hat,melody,bass,all")
    sp.add_argument("--min", type=float, default=0.3)
    sp.add_argument("--rank", type=int, help="instead: show the top-K strongest positions per bar (weighted over layers)")
    sp.add_argument("--weights", help="layer weights for --rank, e.g. kick=1,snare=1,melody=0.8,bass=0.6,hat=0.3")

    sp = add("snap", cmd_snap, "render real Phira frames at beats and save a labelled contact sheet")
    sp.add_argument("work")
    sp.add_argument("--beat", action="append", help="beat(s) to render; repeatable or comma separated")
    sp.add_argument("--around", help="center beat; renders center+offsets")
    sp.add_argument("--offsets", default="-2,-1,-0.5,0,0.5,1")
    sp.add_argument("--range", nargs=2, metavar=("FROM", "TO"))
    sp.add_argument("--step", type=float, default=1.0)
    sp.add_argument("--compare", help="other chart to show as BEFORE row: a path, or @prev / @N for checkpoints")
    sp.add_argument("--scale", type=float)
    sp.add_argument("--label")
    sp.add_argument("--out")

    sp = add("timeline", cmd_timeline, "editor-style overview image of notes vs detected onsets")
    sp.add_argument("work")
    sp.add_argument("--from", dest="start", required=True)
    sp.add_argument("--to", dest="end", required=True)
    sp.add_argument("--cols-beats", type=int, default=8)
    sp.add_argument("--highlight", nargs=2, metavar=("FROM", "TO"))
    sp.add_argument("--out")

    sp = add("lint", cmd_lint, "playability / readability / sync report")
    sp.add_argument("work")
    sp.add_argument("--level", help="EZ/HD/IN/AT density reference")
    sp.add_argument("--max", type=int, default=40)
    sp.add_argument("--json", action="store_true")

    sp = add("stats", cmd_stats, "note statistics")
    sp.add_argument("work")

    sp = add("fmt", cmd_fmt, "normalise chart.json (fill defaults, convert beats to triples, sort, pretty layout)")
    sp.add_argument("work")

    sp = add("notes", cmd_notes, "list notes in a beat range")
    sp.add_argument("work")
    sp.add_argument("--from", dest="start", default="0")
    sp.add_argument("--to", dest="end", default="100000")
    sp.add_argument("--line", type=int)

    sp = add("splice", cmd_splice, "replace the notes of one line inside [from,to) with notes from a JSON file")
    sp.add_argument("work")
    sp.add_argument("--from", dest="start", required=True)
    sp.add_argument("--to", dest="end", required=True)
    sp.add_argument("--file", required=True)
    sp.add_argument("--line", type=int, default=0)

    sp = add("checkpoint", cmd_checkpoint, "save a copy of chart.json into history/")
    sp.add_argument("work")
    sp.add_argument("-m", "--message")

    sp = add("history", cmd_history, "list checkpoints")
    sp.add_argument("work")

    sp = add("export", cmd_export, "write the final strict RPE json (and optional .pez for Phira)")
    sp.add_argument("work")
    sp.add_argument("--out")
    sp.add_argument("--pez", action="store_true")
    sp.add_argument("--force", action="store_true")

    sp = add("video", cmd_video, "render an mp4 preview with music + hit ticks (for humans)")
    sp.add_argument("work")
    sp.add_argument("--from", dest="start")
    sp.add_argument("--to", dest="end")
    sp.add_argument("--fps", type=int, default=30)
    sp.add_argument("--out")

    sp = add("guide", cmd_guide, "print the charting guide")
    sp.add_argument("--path", action="store_true")

    sp = add("make", cmd_make, "audio in -> chart out: init + run the model + export")
    sp.add_argument("audio")
    sp.add_argument("--out", required=True)
    sp.add_argument("--final", help="final json path (default <out>/export/chart.json)")
    sp.add_argument("--backend", default="claude-code", choices=["claude-code", "api", "manual"])
    sp.add_argument("--model", default="claude-opus-5-5")
    sp.add_argument("--effort", default="high")
    sp.add_argument("--max-turns", type=int, default=400)
    sp.add_argument("--name")
    sp.add_argument("--composer")
    sp.add_argument("--level", default="IN Lv.12")
    sp.add_argument("--force", action="store_true")
    audio_opts(sp)

    a = p.parse_args(argv)
    r = a.fn(a)
    sys.exit(r or 0)


if __name__ == "__main__":
    main()
