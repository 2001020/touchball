"""Model backends: one model writes the whole chart inside the workspace.

backends
  claude-code : headless Claude Code (`claude -p`) with Read/Write/Edit + `phichart` shell access.
  api         : Anthropic Messages API manual tool loop (phichart / read / write / edit / view_image tools).
  manual      : only print the task prompt (run any agent yourself in the workspace).
"""
from __future__ import annotations

import base64
import io
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

TASK_PROMPT = """You are an expert Phigros/Phira chart designer. Your job: write the complete Phira chart (RPE json) for the song in this workspace, alone, from start to finish.

Workspace: {work}
- GUIDE.md            <- READ IT FIRST, COMPLETELY. It is the rulebook (format, sampling, flow speed, review loop).
- analysis/summary.md, analysis/bars.txt, analysis/overview.png  <- audio analysis
- PLAN.md             <- you fill this in before charting
- chart.json          <- the chart you edit (relaxed RPE allowed, see GUIDE)
- `phichart <cmd> .`  <- tool CLI (run from the workspace; `phichart -h`)

Mandatory workflow (details in GUIDE.md):
1. Read GUIDE.md, analysis/summary.md, look at analysis/overview.png and skim analysis/bars.txt.
2. Verify the timing grid: chart a few test notes on strong kicks/snares in the first section, render
   `phichart timeline` (notes vs onsets) and confirm notes sit on onsets. Fix BPM/offset first if wrong.
3. Write PLAN.md: sections, which sound layer each section follows, density targets, flow speed per section,
   motifs, what you deliberately leave out (sampling is SELECTIVE).
4. Chart section by section. After EVERY creation or modification: render the changed region with
   `phichart timeline` AND real-engine frames before and after the changed position
   (`phichart snap . --around <beat>`; use `--compare @prev` after edits) and LOOK at the images, then fix problems.
5. Run `phichart lint .` regularly; at the end it must report 0 errors and you must have resolved or
   consciously justified every warning.
6. Finish with `phichart export . --pez` and a short summary of the chart (sections, note count, design ideas).
Do not stop early: the deliverable is a complete, playable chart covering the whole song.
"""


def task_prompt(work: Path) -> str:
    return TASK_PROMPT.format(work=work.resolve())


# ------------------------------------------------------------------ claude code backend
def _run_claude_code(work: Path, model: str, max_turns: int, effort: str) -> int:
    exe = shutil.which("claude")
    if not exe:
        print("claude CLI not found. Install Claude Code or use --backend api / manual.")
        return 127
    phichart_exe = shutil.which("phichart") or f"{sys.executable} -m phichart"
    prompt = task_prompt(work) + f"\nThe CLI is invoked as: {phichart_exe}\n"
    cmd = [exe, "-p", prompt, "--model", model, "--max-turns", str(max_turns),
           "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Bash(phichart:*)", f"Bash({phichart_exe}:*)"]
    log = (work / "agent.log").open("a", encoding="utf-8")
    print(f"[agent] claude-code: model={model} cwd={work}")
    proc = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        log.write(line)
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            print(line.rstrip())
            continue
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "text" and block["text"].strip():
                    print("[model]", block["text"].strip()[:400])
                elif block.get("type") == "tool_use":
                    inp = block.get("input", {})
                    desc = inp.get("command") or inp.get("file_path") or ""
                    print(f"[tool] {block['name']} {str(desc)[:160]}")
        elif ev.get("type") == "result":
            print(f"[agent] done: {ev.get('subtype')} turns={ev.get('num_turns')} cost=${ev.get('total_cost_usd', 0):.2f}")
    return proc.wait()


# ------------------------------------------------------------------ messages api backend
TOOLS = [
    {"name": "phichart", "eager_input_streaming": True,
     "description": "Run the phichart CLI inside the workspace, e.g. args='lint .' or "
                    "'snap . --around 32 --compare @prev'. Returns stdout/stderr. Commands that create images print the image path; "
                    "look at it with view_image.",
     "input_schema": {"type": "object", "properties": {"args": {"type": "string"}}, "required": ["args"]}},
    {"name": "read_file", "eager_input_streaming": True,
     "description": "Read a text file in the workspace (optionally a line window).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"},
                                                         "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "eager_input_streaming": True,
     "description": "Create/overwrite a text file in the workspace (chart.json, PLAN.md, note fragment files ...).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "eager_input_streaming": True,
     "description": "Replace one exact, unique occurrence of old_text with new_text in a workspace file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"},
                                                         "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "view_image", "eager_input_streaming": True,
     "description": "Look at a PNG/JPG image in the workspace (renders, timelines, overview).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "finish", "eager_input_streaming": True,
     "description": "Call once the chart is complete, lint has 0 errors and `phichart export . --pez` succeeded.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
]


def _inside(work: Path, p: str) -> Path:
    path = (work / p).resolve()
    if work.resolve() not in path.parents and path != work.resolve():
        raise ValueError(f"path {p} is outside the workspace")
    return path


def _validate(name: str, inp) -> str | None:
    schema = next((t["input_schema"] for t in TOOLS if t["name"] == name), None)
    if schema is None:
        return f"unknown tool {name}"
    if not isinstance(inp, dict):
        return "input must be an object"
    for k in schema["required"]:
        if k not in inp:
            return f"missing field {k}"
    for k, v in inp.items():
        typ = schema["properties"].get(k, {}).get("type")
        if typ == "string" and not isinstance(v, str) or typ == "integer" and not isinstance(v, int):
            return f"field {k} must be {typ}"
    return None


def _exec_tool(work: Path, name: str, inp: dict):
    from PIL import Image
    if name == "phichart":
        args = shlex.split(inp["args"])
        if args and args[0] == "phichart":
            args = args[1:]
        if args and args[0] == "make":
            return "the make command is not available inside the agent"
        proc = subprocess.run([sys.executable, "-m", "phichart", *args], cwd=work, capture_output=True, text=True, timeout=1800)
        out = (proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr.strip() else "")).strip()
        return f"[exit {proc.returncode}]\n" + (out[-20000:] if len(out) > 20000 else out)
    if name == "read_file":
        text = _inside(work, inp["path"]).read_text(encoding="utf-8").splitlines()
        off = max(0, inp.get("offset", 1) - 1)
        lim = inp.get("limit", 2000)
        chunk = text[off:off + lim]
        return "\n".join(f"{i + off + 1}\t{l}" for i, l in enumerate(chunk)) + (
            f"\n... ({len(text) - off - lim} more lines)" if len(text) > off + lim else "")
    if name == "write_file":
        p = _inside(work, inp["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(inp["content"], encoding="utf-8")
        return f"wrote {p.relative_to(work.resolve())} ({len(inp['content'])} chars)"
    if name == "edit_file":
        p = _inside(work, inp["path"])
        s = p.read_text(encoding="utf-8")
        n = s.count(inp["old_text"])
        if n != 1:
            return f"error: old_text found {n} times (must be exactly once)"
        p.write_text(s.replace(inp["old_text"], inp["new_text"]), encoding="utf-8")
        return "edited"
    if name == "view_image":
        p = _inside(work, inp["path"])
        im = Image.open(p).convert("RGB")
        if im.width > 1800:
            im = im.resize((1800, int(im.height * 1800 / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(buf.getvalue()).decode()}},
                {"type": "text", "text": f"{p.name} {im.width}x{im.height}"}]
    return f"unknown tool {name}"


def _run_api(work: Path, model: str, max_turns: int, effort: str) -> int:
    import anthropic

    client = anthropic.Anthropic()
    system = ("You are a meticulous rhythm-game chart designer working autonomously with tools. "
              "Always look at the images you render before deciding the next step.")
    messages = [{"role": "user", "content": task_prompt(work)}]
    log = (work / "agent.log").open("a", encoding="utf-8")
    for turn in range(max_turns):
        try:
            with client.beta.messages.stream(
                model=model, max_tokens=64000, system=system, tools=TOOLS, messages=messages,
                thinking={"type": "adaptive"}, output_config={"effort": effort},
                betas=["compact-2026-01-12", "server-side-fallback-2026-07-01"],
                fallbacks="default",
                context_management={"edits": [{"type": "compact_20260112"}]},
                cache_control={"type": "ephemeral"},
            ) as stream:
                resp = stream.get_final_message()
        except ValueError as exc:  # unparseable streamed tool json: re-issue
            print(f"[agent] bad tool json from stream ({exc}); retrying")
            continue
        messages.append({"role": "assistant", "content": resp.content})
        for b in resp.content:
            if b.type == "text" and b.text.strip():
                print("[model]", b.text.strip()[:400])
                log.write(b.text + "\n")
        if resp.stop_reason == "refusal":
            print("[agent] model refused; stopping")
            return 3
        if resp.stop_reason == "pause_turn":
            continue
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "max_tokens" and uses:
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": u.id, "is_error": True,
                 "content": "output was cut off (max_tokens); split the work into smaller tool calls"} for u in uses]})
            continue
        if not uses:
            messages.append({"role": "user", "content": "Continue with the workflow. Call `finish` only when the chart is complete, lint-clean and exported."})
            continue
        results = []
        finished = None
        for u in uses:
            err = _validate(u.name, u.input)
            if err:
                results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True,
                                "content": json.dumps({"INVALID_INPUT": err})})
                continue
            print(f"[tool] {u.name} {json.dumps(u.input, ensure_ascii=False)[:160]}")
            if u.name == "finish":
                finished = u.input["summary"]
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": "ok"})
                continue
            try:
                out = _exec_tool(work, u.name, u.input)
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": out})
            except Exception as exc:
                results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True, "content": f"{type(exc).__name__}: {exc}"})
        messages.append({"role": "user", "content": results})
        if finished is not None:
            print("[agent] finished:", finished)
            (work / "SUMMARY.md").write_text(finished, encoding="utf-8")
            return 0
    print("[agent] max turns reached")
    return 4


def run_agent(work: Path, backend: str = "claude-code", model: str = "claude-opus-5-5", max_turns: int = 400,
              effort: str = "high") -> int:
    work = Path(work)
    if backend == "manual":
        print("=== task prompt (give this to any coding agent running in the workspace) ===")
        print(task_prompt(work))
        return 0
    if backend == "claude-code":
        return _run_claude_code(work, model, max_turns, effort)
    if backend == "api":
        return _run_api(work, model, max_turns, effort)
    raise ValueError(backend)
