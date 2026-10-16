"""Check A: can a brief built from the prompt alone contain the code a task needs?

For every verified task (eval/tasks_v2), at the base commit:
  units     every function, and every non-def statement in a class or module body (e.g. TRANSFORMS = {...}),
            in the package (sqlglot/), from Python's ast.
  gold      units the reference fix changes (old-side lines of `git diff -U0 base fix`, non-test files).
  agent     units the baseline agents changed in their runs (their working-tree diffs), any model.
Retrievers, each packing whole units into BUDGET characters (about 5k tokens):
  lexical   BM25 over unit text with identifier-split prompt terms, plus a boost for files of dialects the
            prompt names. Uses nothing but the prompt and the code.
  learned   lexical x a prior per file category (e.g. generators/<named dialect>.py, expressions/*, parser.py)
            estimated leave-one-task-out from which categories baseline agents changed in the OTHER tasks.
Metric: recall of gold units and of agent units inside the brief; also file-level recall.

Usage: python research/prefetch/coverage.py > research/prefetch/coverage.json
"""

from __future__ import annotations

import ast
import collections
import glob
import json
import math
import os
import re
import subprocess
import sys

REPO = "/home/claude/sources/sqlglot"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUDGET = 20000
PKG = "sqlglot/"
EVAL_DIRS = sorted(glob.glob("/home/claude/eval-screen-w*") + glob.glob("/home/claude/eval-haiku-h*")
                   + glob.glob("/home/claude/eval-regr-h*") + ["/home/claude/eval-pilot-a", "/home/claude/eval-pilot-b"])
STOP = set("""a an the and or of to in on for with by is are was be been it its this that these those as at from
into not no but if then else when which what why how all any each can should would will does do did must
only also than such so up out about over more most other some same very just like via per use used using
returns return value values given expected actual currently wrong instead correct correctly sqlglot query
queries sql function functions support supports supported dialect dialects parse parsing parsed generate
generated output input example examples error errors case cases fails fail failing bug fix issue""".split())


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True).stdout


def split_ident(tok: str) -> list[str]:
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", tok)
    out = [tok.lower()] + [p.lower() for p in parts if len(p) > 1]
    return [t for t in out if t not in STOP and len(t) > 1]


def terms(text: str) -> list[str]:
    out = []
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text):
        for piece in tok.split("_"):
            out += split_ident(piece) if piece else []
        if "_" in tok:
            out.append(tok.lower())
    return out


def units_of(path: str, src: str) -> list[dict]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    out = []

    def add(node, name):
        start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
        end = node.end_lineno or node.lineno
        out.append({"file": path, "name": name, "start": start, "end": end,
                    "text": "\n".join(lines[start - 1:end])})

    def walk(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add(node, prefix + node.name)
            elif isinstance(node, ast.ClassDef):
                walk(node.body, prefix + node.name + ".")
            elif not isinstance(node, (ast.Import, ast.ImportFrom)):
                add(node, prefix + f"<stmt@{node.lineno}>")
    walk(tree.body, "")
    return out


def changed_old_lines(diff: str) -> dict[str, set[int]]:
    out, cur = collections.defaultdict(set), None
    for line in diff.splitlines():
        if line.startswith("--- "):
            cur = line[6:] if line.startswith("--- a/") else None
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+", line)
        if m and cur:
            a, b = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            out[cur].update(range(a, a + b) if b else {a, a + 1})
    return out


def unit_keys(units_by_file, changed) -> set[tuple[str, str]]:
    keys = set()
    for f, lines in changed.items():
        for ln in lines:
            best = None
            for u in units_by_file.get(f, []):
                if u["start"] <= ln <= u["end"] and (best is None or u["end"] - u["start"] < best["end"] - best["start"]):
                    best = u
            if best:
                keys.add((best["file"], best["name"]))
    return keys


def category(path: str, dialects: set[str]) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    folder = os.path.dirname(path).replace(PKG, "") or "."
    if stem in dialects:
        return f"{folder}/<named dialect>"
    if folder in ("dialects", "parsers", "generators") and stem != "dialect":
        return f"{folder}/<other dialect>"
    return path.replace(PKG, "")


def agent_changes(task_id: str) -> dict[str, set[int]]:
    total = collections.defaultdict(set)
    for d in EVAL_DIRS:
        for rd in glob.glob(os.path.join(d, "runs", task_id, "baseline", "*", "repo")):
            diff = subprocess.run(["git", "-C", rd, "diff", "-U0", "HEAD", "--", PKG], capture_output=True,
                                  text=True).stdout
            for f, ls in changed_old_lines(diff).items():
                total[f] |= ls
    return total


def bm25_scores(units, query, k1=1.2, b=0.75):
    docs = [collections.Counter(terms(u["name"] + "\n" + u["text"])) for u in units]
    n, avg = len(docs), sum(sum(d.values()) for d in docs) / max(1, len(docs))
    df = collections.Counter(t for d in docs for t in d)
    q = collections.Counter(query)
    scores = []
    for d in docs:
        dl, s = sum(d.values()), 0.0
        for t, qf in q.items():
            if t in d:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * d[t] * (k1 + 1) / (d[t] + k1 * (1 - b + b * dl / avg)) * (1 + math.log(qf))
        scores.append(s)
    return scores


def pack(units, scores, budget=BUDGET):
    chosen, size = set(), 0
    for i in sorted(range(len(units)), key=lambda i: -scores[i]):
        if scores[i] <= 0:
            break
        L = len(units[i]["text"]) + 60
        if size + L > budget:
            continue
        chosen.add((units[i]["file"], units[i]["name"]))
        size += L
    return chosen


SCRATCH = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/cov"


def prompt_code(prompt: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\n(.*?)```", prompt, re.S)
    return "\n".join(blocks)


def contrast_code(named: list[str]) -> str:
    ds = named or ["duckdb"]
    lines = ["from sqlglot import parse_one, transpile, exp"]
    for d in ds:
        lines.append(f'parse_one("SELECT a, b + 1 AS c FROM t WHERE x = 1 ORDER BY a", read="{d}").sql("{d}")')
    for a in ds:
        for b in ds:
            if a != b:
                lines.append(f'transpile("SELECT a, MAX(b) FROM t GROUP BY a", read="{a}", write="{b}")')
    return "\n".join(lines)


def traced(task: dict, code: str, tag: str) -> dict[str, set[int]]:
    os.makedirs(SCRATCH, exist_ok=True)
    wt = os.path.join(SCRATCH, "wt-" + task["id"][:10])
    if not os.path.isdir(wt):
        git("worktree", "add", "-q", "--detach", wt, task["commit"])
    snip = os.path.join(SCRATCH, f"{task['id'][:10]}-{tag}.py")
    out = os.path.join(SCRATCH, f"{task['id'][:10]}-{tag}.json")
    open(snip, "w").write(code)
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "trace_probe.py"), os.path.join(wt, "sqlglot"),
                    snip, out], cwd=wt, capture_output=True, text=True, timeout=600)
    try:
        return {k: set(v) for k, v in json.load(open(out))["lines"].items()}
    except (OSError, ValueError):
        return {}


def executed_units(units_by_file, lines: dict[str, set[int]]) -> set[tuple[str, str]]:
    return unit_keys(units_by_file, lines)


def symbols(prompt: str, units_by_file, ex) -> list[str]:
    """Names to grep: SQL function names and exp.* classes in the prompt, plus expression classes the
    examples executed (their generator/parser hooks are where new entries go)."""
    syms = set(re.findall(r"\bexp\.([A-Z][A-Za-z0-9]+)", prompt))
    for w in re.findall(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{4,})\b", prompt):
        if w.lower() not in STOP and w not in {"SELECT", "FROM", "WHERE", "CAST", "TABLE", "NULL", "WITH", "INTO"}:
            syms.add(w)
            syms.add("".join(p.capitalize() for p in w.split("_")))
    for f, n in ex:
        if f.startswith(PKG + "expressions/") and "." in n:
            syms.add(n.split(".")[0])
    return sorted(syms)


def grep_lines(task, syms, budget):
    """file -> set of lines matching any symbol as a whole word, packed rarest-symbol first."""
    hits, size, out = [], 0, collections.defaultdict(set)
    for sym in syms:
        res = git("grep", "-n", "-w", "-e", sym, task["commit"], "--", PKG).splitlines()
        if 0 < len(res) <= 40:
            hits.append((len(res), sym, res))
    text = []
    for _, sym, res in sorted(hits):
        for line in res:
            _, f, ln, body = line.split(":", 3)
            L = len(f) + len(body) + 8
            if size + L > budget:
                break
            out[f].add(int(ln)); size += L
    return out


def oracle_lines(task_id) -> dict[str, set[int]]:
    """Lines agents saw before their first edit, from baseline runs (Read output, grep hits, sed ranges)."""
    sys.path.insert(0, HERE)
    from build_oracle_briefs import pre_edit_calls
    seen = collections.defaultdict(set)
    for d in EVAL_DIRS:
        for rd in glob.glob(os.path.join(d, "runs", task_id, "baseline", "*")):
            st = os.path.join(rd, "stream.jsonl")
            if not os.path.isfile(st):
                continue
            for head, res in pre_edit_calls(st):
                m = re.match(r"^\[read (\S+)(?: lines (\d+)-(\d+))?\]", head)
                if m:
                    nums = [int(x) for x in re.findall(r"^\s*(\d+)\t", res, re.M)]
                    seen[m.group(1)].update(nums)
                for f, ln in re.findall(r"^(sqlglot/[\w/]+\.py):(\d+)[:-]", res, re.M):
                    seen[f].add(int(ln))
                for a, b, f in re.findall(r"sed -n '?(\d+),(\d+)p'? (sqlglot/[\w/]+\.py)", head):
                    seen[f].update(range(int(a), int(b) + 1))
    return seen


def touched(units_by_file, keys, lines) -> set[tuple[str, str]]:
    """Units with a body in the brief, or at least one of their lines shown (a grep hit)."""
    return set(keys) | unit_keys(units_by_file, lines)


def main():
    tasks = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ROOT, "eval", "tasks_v2", "*.json")))]
    data = {}
    for t in tasks:
        files = [f for f in git("ls-tree", "-r", "--name-only", t["commit"], PKG).split() if f.endswith(".py")]
        dialects = {os.path.splitext(os.path.basename(f))[0] for f in files if f.startswith(PKG + "dialects/")}
        dialects.discard("dialect"); dialects.discard("__init__")
        units = []
        for f in files:
            units += units_of(f, git("show", f"{t['commit']}:{f}"))
        by_file = collections.defaultdict(list)
        for u in units:
            by_file[u["file"]].append(u)
        gold_diff = git("diff", "-U0", t["commit"], t["fix_commit"], "--", PKG)
        gold = unit_keys(by_file, changed_old_lines(gold_diff))
        agent = unit_keys(by_file, agent_changes(t["id"]))
        prompt = t["prompt"]
        named = {d for d in dialects if re.search(rf"\b{re.escape(d)}\b", prompt, re.I)}
        ex = executed_units(by_file, traced(t, prompt_code(prompt), "ex"))
        co = executed_units(by_file, traced(t, contrast_code(sorted(named)), "co"))
        syms = symbols(prompt, by_file, ex)
        data[t["id"]] = dict(units=units, gold=gold, agent=agent, named=named, prompt=prompt, ex=ex, co=co,
                             by_file=by_file, syms=syms, glines=grep_lines(t, syms, 6000),
                             olines=oracle_lines(t["id"]))

    # leave-one-task-out prior: P(unit changed by agents | category), from the other tasks
    cat_hits, cat_all = collections.defaultdict(lambda: collections.Counter()), collections.defaultdict(lambda: collections.Counter())
    for tid, d in data.items():
        for u in d["units"]:
            c = category(u["file"], d["named"])
            cat_all[tid][c] += 1
            if (u["file"], u["name"]) in d["agent"]:
                cat_hits[tid][c] += 1
    rows = []
    for tid, d in data.items():
        units, query = d["units"], terms(d["prompt"])
        lex = bm25_scores(units, query)
        lex = [s * (3.0 if os.path.splitext(os.path.basename(u["file"]))[0] in d["named"] else 1.0)
               for s, u in zip(lex, units)]
        hits, alls = collections.Counter(), collections.Counter()
        for other in data:
            if other != tid:
                hits.update(cat_hits[other]); alls.update(cat_all[other])
        def prior(u):
            c = category(u["file"], d["named"])
            return (hits[c] + 0.1) / (alls[c] + 10.0)
        base = sum(hits.values()) / max(1, sum(alls.values()))
        learned = [s * (prior(u) / base) ** 0.5 for s, u in zip(lex, units)]
        row = {"task": tid, "units": len(units), "gold": len(d["gold"]), "agent": len(d["agent"]),
               "named_dialects": sorted(d["named"])}
        mx = max(lex) or 1.0
        def ex_score(u, s):
            k = (u["file"], u["name"])
            if k not in d["ex"]:
                return 0.0
            return (1.0 if k not in d["co"] else 0.1) * (1.0 + s / mx)
        trace = [ex_score(u, s) for s, u in zip(lex, units)]
        hybrid = [t_ + 0.5 * s / mx for t_, s in zip(trace, lex)]
        row["executed_units"] = len(d["ex"]); row["executed_not_in_contrast"] = len(d["ex"] - d["co"])
        row["gold_executed"] = round(len(d["gold"] & d["ex"]) / len(d["gold"]), 3) if d["gold"] else None
        # realistic brief: traced bodies (14k chars) + symbol grep lines (6k chars) = same 20k budget
        bodies = pack(units, hybrid, budget=BUDGET - 6000)
        real = touched(d["by_file"], bodies, d["glines"])
        orac = touched(d["by_file"], set(), d["olines"])
        for nm, ch in (("brief", real), ("oracle", orac)):
            for gt in ("gold", "agent"):
                g = d[gt]
                row[f"{nm}_{gt}_touched"] = round(len(g & ch) / len(g), 3) if g else None
                gf = {f for f, _ in g}
                row[f"{nm}_{gt}_file_touched"] = round(len(gf & {f for f, _ in ch}) / len(gf), 3) if gf else None
        row["symbols"] = d["syms"][:12]
        for name, sc in (("lexical", lex), ("learned", learned), ("trace", trace), ("hybrid", hybrid)):
            ch = pack(units, sc)
            for gt in ("gold", "agent"):
                g = d[gt]
                row[f"{name}_{gt}_recall"] = round(len(g & ch) / len(g), 3) if g else None
                gf = {f for f, _ in g}
                row[f"{name}_{gt}_file_recall"] = round(len(gf & {f for f, _ in ch}) / len(gf), 3) if gf else None
            row[f"{name}_units_in_brief"] = len(ch)
            row[f"{name}_missed_gold"] = sorted(f"{f}:{n}" for f, n in d["gold"] - ch)[:6]
        rows.append(row)
    summary = {}
    for nm in ("brief", "oracle"):
        for k in ("gold_touched", "agent_touched", "gold_file_touched", "agent_file_touched"):
            v = [r[f"{nm}_{k}"] for r in rows if r[f"{nm}_{k}"] is not None]
            summary[f"{nm}_{k}"] = round(sum(v) / len(v), 3)
            summary[f"{nm}_{k}_full"] = sum(x == 1.0 for x in v)
    vals = [r["gold_executed"] for r in rows if r["gold_executed"] is not None]
    summary["gold_units_executed_by_examples"] = round(sum(vals) / len(vals), 3)
    for name in ("lexical", "learned", "trace", "hybrid"):
        for gt in ("gold", "agent"):
            for lvl in ("recall", "file_recall"):
                vals = [r[f"{name}_{gt}_{lvl}"] for r in rows if r[f"{name}_{gt}_{lvl}"] is not None]
                summary[f"{name}_{gt}_{lvl}"] = round(sum(vals) / len(vals), 3)
                summary[f"{name}_{gt}_{lvl}_full"] = sum(v == 1.0 for v in vals)
    json.dump({"budget_chars": BUDGET, "tasks": len(rows), "summary": summary, "rows": rows}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
