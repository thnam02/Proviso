import json, subprocess, sys
sys.path.insert(0, '/home/claude/p2')
from prompt_spec import SPEC
RUNNER = r'''
import sys, json, warnings, logging
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
from sqlglot import parse_one, transpile, exp
out = []
for e in json.loads(sys.argv[1]):
    try: v = eval(e); out.append(str(v))
    except Exception as x: out.append(f"{type(x).__name__}: {str(x).splitlines()[0][:160]}")
print(json.dumps(out))
'''
res = {}
for pre, (desc, exprs) in SPEC.items():
    r = {}
    for side in ('base', 'fix'):
        root = f'/home/claude/p2/wt/{pre}/{side}'
        p = subprocess.run(['python3', '-c', RUNNER, json.dumps(exprs)], cwd=root, capture_output=True, text=True,
                           env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': root, 'HOME': '/tmp'}, timeout=60)
        r[side] = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else [p.stderr[-200:]] * len(exprs)
    res[pre] = r
    same = sum(a == b for a, b in zip(r['base'], r['fix']))
    print(pre, f'{len(exprs)} examples, {same} unchanged by the fix')
    for e, b, f in zip(exprs, r['base'], r['fix']):
        if b == f: print('   UNCHANGED:', e[:90], '->', b[:80])
json.dump(res, open('/home/claude/p2/examples.json', 'w'), indent=1)
