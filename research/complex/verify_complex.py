"""Verify multi-file candidates: hidden tests = tests in the fix's changed test files that fail with the base source
and pass with the fix source (both run with the fix's test files). Usage: verify_complex.py SHA[,SHA...] OUT.json"""
import json, os, re, shutil, subprocess, sys, xml.etree.ElementTree as ET
SRC = '/home/claude/sources/sqlglot'
WORK = '/home/claude/p3'
G = lambda *a: subprocess.run(['git', *a], cwd=SRC, capture_output=True, text=True)
ENV = lambda r: {'PATH': '/usr/bin:/bin:/usr/local/bin', 'PYTHONPATH': r, 'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'}

def tree(sha, dest):
    shutil.rmtree(dest, ignore_errors=True); os.makedirs(dest)
    p = subprocess.run(['git', 'archive', sha], cwd=SRC, stdout=subprocess.PIPE, check=True)
    subprocess.run(['tar', 'x', '-C', dest], input=p.stdout, check=True)

def junit(root, targets, tag):
    x = f'{WORK}/junit-{tag}.xml'
    if os.path.exists(x): os.remove(x)
    r = subprocess.run(['python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--tb=no', '--continue-on-collection-errors',
                        f'--junitxml={x}', *targets], cwd=root, env=ENV(root), capture_output=True, text=True, timeout=900)
    res = {}
    if not os.path.exists(x): return res, r.stdout[-500:]
    for c in ET.parse(x).iter('testcase'):
        parts = (c.get('classname') or '').split('.')
        node = f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{c.get('name')}"
        res[node] = not any(ch.tag in ('failure', 'error', 'skipped') for ch in c)
    return res, r.stdout[-300:]

if __name__ == '__main__':
    out = {}
    for pre in sys.argv[1].split(','):
        fix = G('rev-parse', pre).stdout.strip(); base = G('rev-parse', fix + '^').stdout.strip()
        tfiles = [p for p in G('diff', '--name-only', base, fix, '--', 'tests/').stdout.split() if p.endswith('.py')]
        d = f'{WORK}/{fix[:10]}'
        tree(fix, d + '/fix'); tree(base, d + '/base')
        for f in tfiles:  # base source + fix tests
            os.makedirs(os.path.dirname(f'{d}/base/{f}'), exist_ok=True)
            shutil.copy(f'{d}/fix/{f}', f'{d}/base/{f}')
        rf, sf = junit(d + '/fix', tfiles, fix[:10] + '-f')
        rb, sb = junit(d + '/base', tfiles, fix[:10] + '-b')
        hidden = sorted(n for n, ok in rf.items() if ok and not rb.get(n, False))
        broken_fix = sorted(n for n, ok in rf.items() if not ok)
        out[fix[:10]] = {'fix': fix, 'base': base, 'test_files': tfiles, 'hidden': hidden, 'n_fix_tests': len(rf),
                         'fix_failing': broken_fix[:10], 'n_fix_failing': len(broken_fix), 'tail_fix': sf}
        print(fix[:10], 'tests', len(rf), 'hidden', len(hidden), 'fix-failing', len(broken_fix), tfiles, flush=True)
    json.dump(out, open(sys.argv[2], 'w'), indent=1)
