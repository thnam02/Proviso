import json, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompt_spec4 import SPEC
V = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify.json')))
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
        root = f'/home/claude/p4/{V[pre]["fix"][:10]}/{side}'
        p = subprocess.run(['python3', '-c', RUNNER, json.dumps(exprs)], cwd=root, capture_output=True, text=True,
                           env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': root, 'HOME': '/tmp'}, timeout=60)
        r[side] = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else [p.stderr[-200:]] * len(exprs)
    res[pre] = r
    print(pre)
    for e, b, f in zip(exprs, r['base'], r['fix']):
        print('  ', 'SAME ' if b == f else 'ok   ', e[:80], '\n        base:', b[:150], '\n        fix: ', f[:150])
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'examples4.json'), 'w'), indent=1)
