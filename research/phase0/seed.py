import json, os, shutil, subprocess, sys
sys.path.insert(0, '.')
from mutants import MUTANTS
from replay import run_probe, BASE
from classify2 import classify_lines, later_seen, clean
RUN = 'baseline/3'
SRC = f'/home/claude/phase0/final/{RUN}'
RUNDIR = f'/home/claude/eval-claude/runs/98bedf649b-fix-oracle-parse-partition-clauses-and-f/{RUN}'
HIDDEN_TEST = f'{RUNDIR}/repo/tests/dialects/test_oracle.py'
HIDDEN = ['tests/dialects/test_oracle.py::TestOracle::test_partition_selection',
          'tests/dialects/test_oracle.py::TestOracle::test_insert_partition',
          'tests/dialects/test_oracle.py::TestOracle::test_flashback']
probes = json.load(open('probes.json'))[RUN]
seen_after = later_seen(RUNDIR)
basec = {i: run_probe(p['code'], BASE) for i, p in enumerate(probes)}
def flags(root):
    v2, v3 = set(), set()
    for i, p in enumerate(probes):
        f = run_probe(p['code'], root)
        for c, o, n in classify_lines(basec[i], f, seen_after):
            if c.startswith(('UNINTENDED', 'REGRESSION')): v2.add((i, c, n))
            if c.startswith('REGRESSION'): v3.add((i, c, n))
    return v2, v3
f2, f3 = flags(SRC)
out = []
for mid, where, path, old, new, desc in MUTANTS:
    d = f'/home/claude/phase0/mutants/{mid}'
    shutil.rmtree(d, ignore_errors=True); shutil.copytree(SRC, d)
    p = os.path.join(d, path); s = open(p).read()
    assert s.count(old) == 1, (mid, s.count(old))
    open(p, 'w').write(s.replace(old, new))
    v2, v3 = flags(d)
    new2, new3 = v2 - f2, v3 - f3
    h = os.path.join(d, 'hidden'); shutil.copytree(d, h, ignore=shutil.ignore_patterns('hidden'))
    shutil.copy(HIDDEN_TEST, os.path.join(h, 'tests/dialects/test_oracle.py'))
    r = subprocess.run(['python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--tb=no', *HIDDEN], cwd=h,
                       env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': h, 'HOME': '/tmp'}, capture_output=True, text=True, timeout=300)
    hidden_catches = r.returncode != 0
    out.append({'id': mid, 'where': where, 'desc': desc, 'trajectory_v2': len(new2) > 0, 'trajectory_v3': len(new3) > 0,
                'hidden_tests_catch': hidden_catches, 'example': sorted(new2)[:1]})
    print(mid, where, '| v2', len(new2) > 0, '| v3', len(new3) > 0, '| hidden tests fail:', hidden_catches, '|', desc, flush=True)
json.dump(out, open('seed_probes.json', 'w'), indent=1, default=str)
