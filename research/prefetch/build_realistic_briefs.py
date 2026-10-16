"""Realistic pre-fetch briefs: built from the prompt and the code only (no agent runs on the task).

1. Run the prompt's code examples at the base commit and trace which package functions execute; rank functions
   that run in the example but not in a plain query of the same dialects (plus a lexical tie-break), and include
   their bodies with line numbers (about 14,000 characters).
2. grep lines for names in the prompt (SQL function names, exp.* classes) and for expression classes the examples
   executed: where registry entries such as TRANSFORMS / FUNCTIONS live (about 6,000 characters).
3. Tests that already fail at the base commit.
The example outputs themselves are not repeated: the prompt already shows them.

Usage: python research/prefetch/build_realistic_briefs.py TASK_DIR OUT_DIR [TASK_PREFIX...]
"""

from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coverage as C  # noqa: E402

BODY_BUDGET = 14000
GREP_BUDGET = 6000
MAX_LINES = 40
FAIL_HEAD = "Tests that already fail at this commit, before any change (not caused by you):\n"


def base_failures(task: dict, python: str) -> list[str]:
    wt = os.path.join(C.SCRATCH, "wt-" + task["id"][:10])
    if not os.path.isdir(wt):
        C.git("worktree", "add", "-q", "--detach", wt, task["commit"])
    import subprocess
    r = subprocess.run([python, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=wt,
                       capture_output=True, text=True, timeout=1200)
    bad = sorted(set(re.findall(r"^(?:ERROR|FAIL): (\S+) \(([^)]*)\)", r.stderr, re.M)))
    out = []
    for name, where in bad:
        where = where.replace("unittest.loader._FailedTest.", "")
        out.append(where if name == where.split(".")[-1] or "_FailedTest" in name else f"{where}")
    reason = re.search(r"No module named '(\w+)'", r.stderr)
    if out and reason:
        out.append(f"Cause: the {reason.group(1)} module is not installed in this environment. These exist before "
                   "any change and are not caused by your work.")
    return out


def build(task: dict, python: str) -> tuple[str, dict]:
    files = [f for f in C.git("ls-tree", "-r", "--name-only", task["commit"], C.PKG).split() if f.endswith(".py")]
    dialects = {os.path.splitext(os.path.basename(f))[0] for f in files if f.startswith(C.PKG + "dialects/")}
    dialects -= {"dialect", "__init__"}
    units, by_file = [], collections.defaultdict(list)
    for f in files:
        for u in C.units_of(f, C.git("show", f"{task['commit']}:{f}")):
            units.append(u)
            by_file[f].append(u)
    prompt = task["prompt"]
    named = sorted(d for d in dialects if re.search(rf"\b{re.escape(d)}\b", prompt, re.I))
    ex = C.executed_units(by_file, C.traced(task, C.prompt_code(prompt), "ex"))
    co = C.executed_units(by_file, C.traced(task, C.contrast_code(named), "co"))
    boiler = {"parse_one", "parse", "one", "transpile", "exp", "read", "write", "sql", "select", "from", "currently",
              "expected", "args", "get", "type", "name", "true", "false", "none"}
    lex = C.bm25_scores(units, [t for t in C.terms(prompt) if t not in boiler])
    lex = [s * (3.0 if os.path.splitext(os.path.basename(u["file"]))[0] in named else 1.0) for s, u in zip(lex, units)]
    mx = max(lex) or 1.0
    score = []
    for u, s in zip(units, lex):
        k = (u["file"], u["name"])
        t = 0.0 if k not in ex else (1.0 if k not in co else 0.15) * (1.0 + s / mx)
        score.append(t + 0.3 * s / mx)
    # long bodies are cut to their first MAX_LINES lines (the signature and the start of the logic)
    for u in units:
        lines = u["text"].splitlines()
        if len(lines) > MAX_LINES:
            u["text"] = "\n".join(lines[:MAX_LINES] + [f"    ... ({len(lines) - MAX_LINES} more lines)"])
    chosen = C.pack(units, score, budget=BODY_BUDGET)
    order = sorted((u for u in units if (u["file"], u["name"]) in chosen), key=lambda u: (u["file"], u["start"]))
    parts = []
    for u in order:
        lines = u["text"].splitlines()
        numbered = "\n".join((f"{u['start'] + i:>6}\t{line}" if not line.lstrip().startswith("... (") else line)
                             for i, line in enumerate(lines))
        parts.append(f"[{u['file']} lines {u['start']}-{u['end']}: {u['name']}]\n{numbered}\n")
    syms = C.symbols(prompt, by_file, ex)
    grep_parts, size = [], 0
    hits = []
    for sym in syms:
        res = C.git("grep", "-n", "-w", "-e", sym, task["commit"], "--", C.PKG).splitlines()
        if 0 < len(res) <= 40:
            hits.append((len(res), sym, res))
    for _, sym, res in sorted(hits):
        block = [f"[grep -nw {sym} sqlglot/]"]
        for line in res:
            _, f, ln, body = line.split(":", 3)
            block.append(f"{f}:{ln}:{body.rstrip()[:160]}")
        text = "\n".join(block) + "\n"
        if size + len(text) > GREP_BUDGET:
            continue
        grep_parts.append(text)
        size += len(text)
    fails = base_failures(task, python)
    tail = [FAIL_HEAD + "\n".join(f"- {f}" for f in fails) + "\n"] if fails else []
    brief = "\n".join(parts + grep_parts + tail)
    meta = {"bodies": [f"{u['file']}:{u['name']}" for u in order], "symbols": syms, "named": named,
            "executed": len(ex), "executed_not_in_contrast": len(ex - co), "chars": len(brief)}
    return brief, meta


if __name__ == "__main__":
    task_dir, out_dir, prefixes = sys.argv[1], sys.argv[2], sys.argv[3:]
    python = os.environ.get("BRIEF_PYTHON", sys.executable)
    os.makedirs(out_dir, exist_ok=True)
    metas = {}
    for f in sorted(glob.glob(os.path.join(task_dir, "*.json"))):
        t = json.load(open(f))
        if prefixes and not any(t["id"].startswith(p) for p in prefixes):
            continue
        brief, meta = build(t, python)
        open(os.path.join(out_dir, t["id"] + ".md"), "w").write(brief)
        metas[t["id"]] = meta
        print(t["id"][:10], meta["chars"], "chars,", len(meta["bodies"]), "bodies,", meta["symbols"][:8], flush=True)
    json.dump(metas, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)
