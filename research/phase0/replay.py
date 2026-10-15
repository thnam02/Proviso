import json, os, re, subprocess, sys, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
BASE = '/home/claude/phase0/base'
FINAL = '/home/claude/phase0/final'
FINALT = '/home/claude/phase0/finalT'
probes = json.load(open('probes.json'))

def norm(text, root=None):
    t = text.replace('\r', '')
    t = re.sub(r'/home/claude/[\w./-]*?/repo|/home/claude/phase0/[\w./-]+?(?=/sqlglot|/tests|\b)', '<R>', t)
    if root: t = t.replace(root, '<R>')
    t = re.sub(r'0x[0-9a-fA-F]+', '0x?', t)
    lines = [l for l in t.split('\n') if 'Unable to set __version__' not in l and 'warnings.warn' not in l and l.strip()]
    out, tb = [], False
    for l in lines:
        if l.startswith('Traceback (most recent call last)'):
            tb = True; continue
        if tb and (l.startswith('  ') or l.startswith('    ') or l.strip().startswith('^')):
            continue
        if tb:
            out.append('EXC: ' + l.strip()); tb = False; continue
        out.append(l.rstrip())
    return out

def is_error(lines):
    return any(l.startswith('EXC: ') for l in lines)

def run_probe(code, root):
    env = {'PATH': '/usr/bin:/bin:/usr/local/bin', 'PYTHONPATH': root, 'HOME': '/tmp', 'PYTHONHASHSEED': '0'}
    try:
        p = subprocess.run(['python3', '-c', code], cwd=root, env=env, capture_output=True, text=True, timeout=20)
        return norm(p.stdout + p.stderr, root)
    except subprocess.TimeoutExpired:
        return ['EXC: timeout']

def seen_contains(final_lines, seen):
    s = '\n'.join(norm(seen))
    body = [l[5:] if l.startswith('EXC: ') else l for l in final_lines]
    return all(b.strip() in s for b in body if b.strip())

def classify(p, b1, b2, f):
    if b1 != b2: return 'flaky'
    if b1 == f: return 'preserved'
    if seen_contains(f, p['seen']) and p['phase'] == 'after': return 'intended (agent saw it)'
    if is_error(b1) and not is_error(f) and p['phase'] == 'before': return 'intended (repro fixed)'
    if seen_contains(f, p['seen']): return 'intended (agent saw it)'
    if not is_error(b1) and is_error(f): return 'REGRESSION (now errors)'
    return 'UNINTENDED candidate'

def suite(root, tag):
    xmlp = f'/home/claude/phase0/junit-{tag}.xml'
    subprocess.run(['python3', '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider', '--tb=no',
                    '--continue-on-collection-errors', f'--junitxml={xmlp}'], cwd=root,
                   env={'PATH': '/usr/bin:/bin:/usr/local/bin', 'PYTHONPATH': root, 'HOME': '/tmp'},
                   capture_output=True, text=True, timeout=900)
    res = {}
    for c in ET.parse(xmlp).iter('testcase'):
        k = (c.get('classname') or '') + '::' + (c.get('name') or '')
        res[k] = not any(ch.tag in ('failure', 'error') for ch in c)
    return res

if __name__ == '__main__':
    report = {}
    for run, ps in probes.items():
        rows = []
        for p in ps:
            b1 = run_probe(p['code'], BASE); b2 = run_probe(p['code'], BASE)
            f = run_probe(p['code'], os.path.join(FINAL, run))
            rows.append({'phase': p['phase'], 'step': p['step'], 'class': classify(p, b1, b2, f),
                         'base': b1[:6], 'final': f[:6], 'code': p['code'][:300]})
        report[run] = {'probes': rows}
        print(run, [r['class'] for r in rows], flush=True)
    jobs = {'base': BASE, **{run: os.path.join(FINALT, run) for run in probes}}
    with ThreadPoolExecutor(4) as ex:
        res = dict(zip(jobs, ex.map(lambda kv: suite(kv[1], kv[0].replace('/', '-')), jobs.items())))
    base = res['base']
    for run in probes:
        fr = res[run]
        regress = [k for k, ok in base.items() if ok and k in fr and not fr[k]]
        fixed = [k for k, ok in base.items() if not ok and fr.get(k)]
        report[run]['tests'] = {'total': len(base), 'regressions': regress, 'newly_passing': fixed}
        print(run, 'tests:', len(base), 'regressions:', regress, 'newly passing:', len(fixed), flush=True)
    json.dump(report, open('replay_report.json', 'w'), indent=1)
