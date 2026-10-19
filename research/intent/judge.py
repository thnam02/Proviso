"""LLM intent check: given the task and a view of the patch, does the patch change behaviour the task did not ask
for? Three views of the same patch:
  code       the code diff only (what an LLM reviewer sees today)
  behaviour  the behavioural diff only (Proviso: import-time values and test-input outputs that changed)
  both       code diff + behavioural diff
The model has no tools (claude -p --tools ""), runs in an empty directory, and answers in JSON.
Usage: python judge.py MODEL VIEW OUT.jsonl [MAX_CASES]"""
import glob, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

SYSTEM = ("You review patches written by an AI coding agent for sqlglot, a Python SQL parser and transpiler that "
          "supports many SQL dialects; some dialects inherit behaviour from others (e.g. Redshift from Postgres, "
          "Doris and StarRocks from MySQL). Your job: decide whether the patch changes behaviour that the task did "
          "not ask for -- an unintended side effect or regression. Changes the task needs, including necessary "
          "consequences of them, are fine.")

ASK = ('Answer with JSON only: {"verdict": "clean" or "unintended", "evidence": "the specific change you consider '
       'unintended, or empty"}. Say "unintended" only if some concrete change goes beyond what the task requires.')


def render_behaviour(c, max_keys=12, max_entries=8, max_groups=12, per_group=3):
    lines = []
    ic = c["import_changes"]
    lines.append(f"Values computed at import time that changed ({len(ic)}):" if ic else
                 "Values computed at import time: none changed.")
    for it in ic[:max_keys]:
        k = it["key"]
        if it["kind"] == "dict":
            parts = [f"+ {kk}: {v}" for kk, v in list(it["added"].items())[:max_entries]]
            parts += [f"- {kk}: {v}" for kk, v in list(it["removed"].items())[:max_entries]]
            parts += [f"~ {kk}: {a} -> {b}" for kk, (a, b) in list(it["changed"].items())[:max_entries]]
            lines.append(f"  {k} (dict): " + "; ".join(parts))
        elif it["kind"] == "value":
            lines.append(f"  {k}: {it['before']} -> {it['after']}")
        else:
            parts = [f"+ {v}" for v in it["added"][:max_entries]] + [f"- {v}" for v in it["removed"][:max_entries]]
            lines.append(f"  {k} ({it['kind']}): " + "; ".join(parts))
    oc = c["output_changes"]
    if not oc:
        lines.append("Outputs on the test inputs (each input generated in its dialect and in dialects inheriting from "
                     "it): none changed.")
    else:
        groups = {}
        for o in oc:
            groups.setdefault((o["source"], o["dialect"]), []).append(o)
        lines.append(f"Outputs that changed on the test inputs ({len(oc)} input/dialect pairs; an input is generated "
                     f"in its own dialect and in dialects inheriting from it):")
        for (src, dia), os_ in sorted(groups.items(), key=lambda g: -len(g[1]))[:max_groups]:
            where = dia if src == dia else f"{dia} (input written for {src})"
            lines.append(f"  {where}: {len(os_)} changed")
            for o in os_[:per_group]:
                lines.append(f"    input:  {o['input'][:200]}\n    before: {str(o['before'])[:200]}\n"
                             f"    after:  {str(o['after'])[:200]}")
    text = "\n".join(lines)
    return text if len(text) < 20000 else text[:20000] + "\n[... behavioural diff truncated]"


def prompt(c, view):
    p = [f"TASK given to the agent:\n{c['prompt'].strip()}\n"]
    if view in ("code", "both"):
        diff = c["code_diff"]
        p.append("CODE DIFF of the agent's patch:\n" + (diff if len(diff) < 14000 else diff[:14000] + "\n[...]") + "\n")
    if view in ("behaviour", "both"):
        p.append("BEHAVIOURAL DIFF of the agent's patch (measured by running the code before and after the patch):\n"
                 + render_behaviour(c) + "\n")
    p.append(ASK)
    return "\n".join(p)


def ask(model, text):
    with tempfile.TemporaryDirectory() as d:
        # the prompt goes through stdin: a large behavioural diff exceeds the argument-length limit
        r = subprocess.run(["claude", "-p", "--model", model, "--tools", "", "--output-format", "json",
                            "--system-prompt", SYSTEM, "--no-session-persistence"], cwd=d, capture_output=True,
                           text=True, timeout=600, input=text)
    out = json.loads(r.stdout)
    res = out.get("result", "")
    s, e = res.find("{"), res.rfind("}")
    try:
        ans = json.loads(res[s:e + 1])
    except ValueError:
        ans = {"verdict": "unparsed", "evidence": res[:300]}
    return ans, out.get("total_cost_usd", 0)


def cases():
    for p in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        for i, c in enumerate(json.load(open(p))):
            if c["label"] in ("intended", "unintended"):
                yield f"{c['task']}:{i}", c


def main():
    model, view, out = sys.argv[1], sys.argv[2], sys.argv[3]
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 10 ** 9
    done = set()
    if os.path.exists(out):
        done = {json.loads(l)["id"] for l in open(out)}
    n = 0
    for cid, c in cases():
        if n >= limit:
            break
        n += 1
        if cid in done:
            continue
        ans, cost = ask(model, prompt(c, view))
        row = {"id": cid, "model": model, "view": view, "label": c["label"], "caught_by_tests": c.get("caught_by_tests"),
               "verdict": ans.get("verdict"), "evidence": ans.get("evidence", ""), "cost": cost}
        open(out, "a").write(json.dumps(row) + "\n")
        print(cid, c["label"], "->", row["verdict"], f"${cost:.4f}", flush=True)


if __name__ == "__main__":
    main()
