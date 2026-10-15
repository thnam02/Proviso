import json, os, subprocess, xml.etree.ElementTree as ET, time
ENV = lambda r: {'PATH': '/usr/bin:/bin:/usr/local/bin', 'PYTHONPATH': r, 'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'}
def suite(root, tag):
    xmlp = f'/home/claude/phase0/junit-{tag}.xml'
    if os.path.exists(xmlp): os.remove(xmlp)
    t = time.time()
    subprocess.run(['python3', '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider', '--tb=no',
                    '--continue-on-collection-errors', f'--junitxml={xmlp}'], cwd=root, env=ENV(root),
                   capture_output=True, text=True, timeout=600)
    res = {}
    for c in ET.parse(xmlp).iter('testcase'):
        res[(c.get('classname') or '') + '::' + (c.get('name') or '')] = not any(ch.tag in ('failure', 'error') for ch in c)
    return res, time.time() - t
if __name__ == '__main__':
    import sys
    base, tb = suite('/home/claude/phase0/base', 'base')
    out = {'base_time': tb, 'runs': {}}
    for run in ['baseline/1','baseline/2','baseline/3','layer/1','layer/2','layer/3']:
        fr, t = suite(f'/home/claude/phase0/finalT/{run}', run.replace('/', '-'))
        regress = [k for k, ok in base.items() if ok and k in fr and not fr[k]]
        fixed = [k for k, ok in base.items() if not ok and fr.get(k)]
        out['runs'][run] = {'tests': len(base), 'regressions': regress, 'newly_passing': fixed, 'seconds': round(t)}
        print(run, 'tests', len(base), 'regressions', regress, 'newly passing', fixed, f'{t:.0f}s', flush=True)
    json.dump(out, open('suites.json', 'w'), indent=1)
