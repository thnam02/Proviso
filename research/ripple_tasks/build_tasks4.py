"""Build eval/tasks_complex/*.json: prompt from prompt_spec4 + examples3, hidden tests from verify.json, regression tests =
every test passing at the base commit (base tests) and at the fix commit (fix tests), minus hidden."""
import json, os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from prompt_spec4 import SPEC
from verify_rt import tree, junit, G  # noqa: E402  (module runs nothing at import when argv is short)
V = json.load(open(os.path.join(HERE, 'verify.json')))
EX = json.load(open(os.path.join(HERE, 'examples4.json')))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'eval', 'tasks_ripple')
os.makedirs(OUT, exist_ok=True)

def slug(s):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', re.sub(r'\(#\d+\)|\[\w+\]|CLAUDE|CODEX', '', s).lower())).strip('-')[:40].strip('-')

def pool(v):
    d = f"/home/claude/p4/{v['fix'][:10]}"
    tree(v['base'], d + '/base0')
    for side, root in (('b', d + '/base0'), ('f', d + '/fix')):
        for _ in range(3):
            res, _tail = junit(root, ['tests'], v['fix'][:10] + '-full' + side)
            if len(res) > 500:
                break
        yield res

for pre, (desc, exprs) in SPEC.items():
    v = V[pre]; ex = EX[pre]
    body = "\n\n".join(f"{e}\n# currently: {b}\n# expected:  {f}" for e, b, f in zip(exprs, ex['base'], ex['fix']) if b != f)
    prompt = (f"{desc}\n\nFor example:\n\n```python\nfrom sqlglot import parse_one, transpile, exp\n\n{body}\n```\n\n"
              "Other forms of the same constructs described above should work as well.")
    rb, rf = pool(v)
    hidden = set(v['hidden'])
    regression = sorted(n for n, ok in rb.items() if ok and rf.get(n) and n not in hidden)
    subject = G('log', '-1', '--format=%s', v['fix']).stdout.strip()
    tid = f"{pre}-{slug(subject)}"
    task = {"id": tid, "repo": "https://github.com/tobymao/sqlglot.git", "commit": v['base'], "prompt": prompt,
            "hidden_tests": sorted(hidden), "test_patch": G('diff', v['base'], v['fix'], '--', 'tests').stdout,
            "regression_tests": regression, "setup": "python -m pip install -e . -q", "prompt_original": subject,
            "fix_commit": v['fix'], "verified": True,
            "source_files_changed": len([p for p in G('diff', '--name-only', v['base'], v['fix'], '--', 'sqlglot').stdout.split() if p.endswith('.py')]),
            "hidden_tests_note": "hidden tests = tests in the fix's changed test files that fail with the base source and pass with the fix source; regression tests = every existing test in the repository that passes at both commits"}
    json.dump(task, open(os.path.join(OUT, tid + '.json'), 'w'), indent=2)
    print(tid, 'hidden', len(hidden), 'regression', len(regression), 'base tests', len(rb), 'fix tests', len(rf), flush=True)
