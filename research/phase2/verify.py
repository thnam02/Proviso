import json, os, re, subprocess, shutil, sys, random, xml.etree.ElementTree as ET
SRC = '/home/claude/sources/sqlglot'
TASKDIR = '/home/claude/proviso-dev/eval/tasks'
CANDS = sys.argv[1].split(',')
G = lambda *a, cwd=SRC: subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True)
ENV = lambda r: {'PATH': '/usr/bin:/bin:/usr/local/bin', 'PYTHONPATH': r, 'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'}

def task_file(prefix):
    return next(os.path.join(TASKDIR, f) for f in os.listdir(TASKDIR) if f.startswith(prefix))

def tree(sha, dest):
    shutil.rmtree(dest, ignore_errors=True); os.makedirs(dest)
    p = subprocess.run(['git', 'archive', sha], cwd=SRC, stdout=subprocess.PIPE, check=True)
    subprocess.run(['tar', 'x', '-C', dest], input=p.stdout, check=True)

def junit(root, targets, tag):
    x = f'/home/claude/p2/junit-{tag}.xml'
    if os.path.exists(x): os.remove(x)
    subprocess.run(['python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--tb=no', '--continue-on-collection-errors',
                    f'--junitxml={x}', *targets], cwd=root, env=ENV(root), capture_output=True, text=True, timeout=600)
    res = {}
    if not os.path.exists(x): return res
    for c in ET.parse(x).iter('testcase'):
        cls = c.get('classname') or ''
        parts = cls.split('.')
        path = '/'.join(parts[:-1]) + '.py'
        node = f"{path}::{parts[-1]}::{c.get('name')}"
        res[node] = not any(ch.tag in ('failure', 'error', 'skipped') for ch in c)
    return res

out = {}
for pre in CANDS:
    tf = task_file(pre); t = json.load(open(tf))
    fix = G('rev-parse', pre).stdout.strip(); base = G('rev-parse', fix + '^').stdout.strip()
    tfiles = re.findall(r'^diff --git a/(\S+)', t['test_patch'], re.M)
    src = [l.split('\t')[2] for l in G('diff', '--numstat', base, fix).stdout.strip().splitlines()]
    dialect_tests = []
    for p in src:
        m = re.match(r'sqlglot/(?:dialects|parsers|generators)/(\w+)\.py$', p)
        if m and m.group(1) not in ('dialect',):
            cand = f'tests/dialects/test_{m.group(1)}.py'
            if cand not in tfiles: dialect_tests.append(cand)
    files = sorted(set(tfiles + dialect_tests))
    B = f'/home/claude/p2/wt/{pre}/base'; F = f'/home/claude/p2/wt/{pre}/fix'
    tree(base, B); tree(fix, F)
    for rel in tfiles:  # base code + fix-commit test files (what grading uses)
        os.makedirs(os.path.dirname(os.path.join(B, rel)), exist_ok=True)
        if os.path.exists(os.path.join(F, rel)): shutil.copy(os.path.join(F, rel), os.path.join(B, rel))
    files = [f for f in files if os.path.exists(os.path.join(F, f))]
    rb = junit(B, files, pre + '-b'); rf = junit(F, files, pre + '-f')
    hidden = t['hidden_tests']
    h_base = {h: rb.get(h) for h in hidden}; h_fix = {h: rf.get(h) for h in hidden}
    f2p = all(v is False for v in h_base.values()) and all(v is True for v in h_fix.values())
    pool = sorted(k for k in rf if k not in hidden and rf.get(k) and rb.get(k))
    random.Random(0).shuffle(pool)
    same_file = [k for k in pool if k.split('::')[0] in tfiles]
    other = [k for k in pool if k.split('::')[0] not in tfiles]
    regr = sorted((same_file[:12] + other[:20])[:20])
    out[pre] = {'id': t['id'], 'fix': fix, 'base': base, 'fail_to_pass': f2p, 'hidden_base': h_base, 'hidden_fix': h_fix,
                'regression_tests': regr, 'pool': len(pool), 'test_files': files}
    print(pre, 'F2P' if f2p else 'NOT-F2P', 'hidden base', list(h_base.values()), 'fix', list(h_fix.values()),
          '| regression', len(regr), 'of pool', len(pool), '| files', files, flush=True)
json.dump(out, open(f'/home/claude/p2/verify-{CANDS[0]}.json', 'w'), indent=1)
