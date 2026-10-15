import json, os, re, difflib, subprocess, sys, xml.etree.ElementTree as ET
sys.path.insert(0, '.')
from replay import run_probe, BASE, FINAL, FINALT, norm
from probes import load, is_source_edit, RUNS
ERR = re.compile(r'(EXC: |Error|Invalid expression|Expecting|Required keyword|\bERR\b|Traceback)')
ANSI = re.compile(r'\x1b\[|\[4m|\[0m')

def clean(lines):
    return [l for l in lines if not ANSI.search(l)]

def err(l): return bool(ERR.search(l))

def later_seen(run):
    """All tool output the agent saw after its first source edit, normalised."""
    events, results = load(run)
    edited, texts = False, []
    for tid, name, inp in events:
        if is_source_edit(name, inp): edited = True; continue
        if edited and tid in results: texts.append('\n'.join(norm(results[tid])))
    return '\n'.join(texts)

def classify_lines(b, f, seen_after):
    b, f = clean(b), clean(f)
    sm = difflib.SequenceMatcher(a=b, b=f, autojunk=False)
    blocks, cur = [], None
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            if cur: blocks.append(cur); cur = None
            continue
        if cur is None: cur = [[], []]
        cur[0] += b[i1:i2]; cur[1] += f[j1:j2]
    if cur: blocks.append(cur)
    out = []
    for olds, news in blocks:
        oe, ne = any(err(l) for l in olds), any(err(l) for l in news)
        if oe and not ne: c = 'intended (error fixed)'
        elif oe and ne: c = 'preserved (error both)'
        elif ne and not oe: c = 'REGRESSION (now errors)'
        elif news and all(n.strip() in seen_after for n in news if n.strip()): c = 'intended (agent saw it after editing)'
        else: c = 'UNINTENDED (A changed to B, never seen)'
        out.append((c, ' / '.join(olds)[:160], ' / '.join(news)[:160]))
    return out

if __name__ == '__main__':
    P = json.load(open('probes.json'))
    summary = {}
    for run_dir in RUNS:
        run = '/'.join(run_dir.split('/')[-2:])
        seen_after = later_seen(run_dir)
        flags_v2, flags_v3, intended, changed_blocks, flaky = [], [], 0, 0, 0
        for p in P[run]:
            b1 = run_probe(p['code'], BASE); b2 = run_probe(p['code'], BASE)
            if clean(b1) != clean(b2): flaky += 1; continue
            f = run_probe(p['code'], os.path.join(FINAL, run))
            for c, o, n in classify_lines(b1, f, seen_after):
                changed_blocks += 1
                if c.startswith('intended'): intended += 1
                if c.startswith('UNINTENDED') or c.startswith('REGRESSION'): flags_v2.append((p['step'], c, o, n))
                if c.startswith('REGRESSION'): flags_v3.append((p['step'], c, o, n))
        summary[run] = {'probes': len(P[run]), 'flaky': flaky, 'changed_blocks': changed_blocks, 'intended': intended,
                        'flags_v2': flags_v2, 'flags_v3': flags_v3}
        print(f"{run}: probes {len(P[run])}, flaky {flaky}, changed blocks {changed_blocks}, intended {intended}, "
              f"v2 flags {len(flags_v2)}, v3 flags {len(flags_v3)}")
        for x in flags_v2: print('     ', x)
    json.dump(summary, open('classify2.json', 'w'), indent=1)
