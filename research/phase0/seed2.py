import json, os, shutil, subprocess, sys, xml.etree.ElementTree as ET
sys.path.insert(0, '.')
from mutants import MUTANTS
from replay import run_probe
from classify2 import clean
from suites import suite
RUN = 'baseline/3'; SRC = f'/home/claude/phase0/final/{RUN}'
probes = json.load(open('probes.json'))[RUN]
finalc = {i: clean(run_probe(p['code'], SRC)) for i, p in enumerate(probes)}
base_tests = {}
for c in ET.parse('/home/claude/phase0/junit-base.xml').iter('testcase'):
    base_tests[(c.get('classname') or '') + '::' + (c.get('name') or '')] = not any(ch.tag in ('failure', 'error') for ch in c)
res = json.load(open('seed_probes.json'))
for r in res:
    d = f'/home/claude/phase0/mutants/{r["id"]}'
    r['trajectory_v4'] = any(clean(run_probe(p['code'], d)) != finalc[i] for i, p in enumerate(probes))
    t = f'/home/claude/phase0/mutantsT/{r["id"]}'
    shutil.rmtree(t, ignore_errors=True); os.makedirs(t)
    shutil.copytree(os.path.join(d, 'sqlglot'), os.path.join(t, 'sqlglot'))
    shutil.copytree('/home/claude/phase0/base/tests', os.path.join(t, 'tests'))
    tr, secs = suite(t, 'mut-' + r['id'])
    fails = [k for k, ok in base_tests.items() if ok and k in tr and not tr[k]]
    r['test_suite_catch'] = len(fails) > 0; r['test_failures'] = len(fails); r['example_test'] = fails[:2]
    print(r['id'], r['where'], '| v2', r['trajectory_v2'], '| v4', r['trajectory_v4'], '| tests', r['test_suite_catch'], f"({len(fails)})", '| hidden', r['hidden_tests_catch'], flush=True)
json.dump(res, open('seed_results.json', 'w'), indent=1, default=str)
