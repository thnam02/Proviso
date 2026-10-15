"""Extract replayable Python probes from Claude Code transcripts."""
import json, glob, os, re
RUNS = sorted(glob.glob('/home/claude/eval-claude/runs/98bedf649b-*/*/*'))
PYBIN = r'(?:python3?|\S*venv/bin/python|\$V/python|\$V)'
HEREDOC = re.compile(PYBIN + r"\s+-\s+(?:2>&1\s*)?<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\1[ \t]*(?:\n|$)", re.S)
DASHC = re.compile(PYBIN + r"\s+-c\s+")
WRITES = re.compile(r"open\([^)]*['\"][wa]['\"]|\.write_text\(|\.write\(")

def quoted(s, i):
    q = s[i]
    if q not in '"\'':
        return None
    j, buf = i + 1, []
    while j < len(s):
        c = s[j]
        if q == '"' and c == '\\' and j + 1 < len(s) and s[j+1] in '"\\$`':
            buf.append(s[j+1]); j += 2; continue
        if c == q:
            return ''.join(buf)
        buf.append(c); j += 1
    return None

def extract(cmd):
    out = []
    for m in HEREDOC.finditer(cmd):
        out.append(m.group(2))
    for m in DASHC.finditer(cmd):
        code = quoted(cmd, m.end())
        if code:
            out.append(code)
    return [c for c in out if 'sqlglot' in c and not WRITES.search(c)]

def is_source_edit(name, inp):
    if name in ('Edit', 'Write', 'MultiEdit'):
        return '/tests/' not in inp.get('file_path', '')
    if 'replace_symbol' in name or 'insert_symbol' in name:
        return True
    if name == 'Bash':
        c = inp.get('command', '')
        for code in [m.group(2) for m in HEREDOC.finditer(c)]:
            if WRITES.search(code) and re.search(r"sqlglot/[\w/]+\.py", code):
                return True
        if re.search(r"(sed -i|cat >>?)[^\n|;]*sqlglot/[\w/]+\.py", c):
            return True
    return False

def load(run):
    events, results = [], {}
    for l in open(os.path.join(run, 'stream.jsonl')):
        try: d = json.loads(l)
        except: continue
        if d.get('type') == 'assistant':
            for b in d['message'].get('content', []):
                if b.get('type') == 'tool_use':
                    events.append((b['id'], b['name'], b.get('input', {})))
        elif d.get('type') == 'user':
            for b in (d.get('message', {}).get('content') or []):
                if isinstance(b, dict) and b.get('type') == 'tool_result':
                    c = b.get('content')
                    if isinstance(c, list): c = '\n'.join(x.get('text', '') for x in c if isinstance(x, dict))
                    results[b.get('tool_use_id')] = str(c or '')
    return events, results

def probes_for(run):
    events, results = load(run)
    edits_so_far, out, tests = 0, [], 0
    for i, (tid, name, inp) in enumerate(events):
        if is_source_edit(name, inp):
            edits_so_far += 1
            continue
        if name != 'Bash':
            continue
        c = inp.get('command', '')
        if re.search(r'make unit|pytest|unittest', c):
            tests += 1
        for code in extract(c):
            out.append({'step': i, 'phase': 'after' if edits_so_far else 'before',
                        'code': code, 'seen': results.get(tid, '')})
    return out, tests, edits_so_far

if __name__ == '__main__':
    allp = {}
    for run in RUNS:
        key = '/'.join(run.split('/')[-2:])
        ps, tests, edits = probes_for(run)
        allp[key] = ps
        b = sum(p['phase'] == 'before' for p in ps); a = len(ps) - b
        print(f"{key}: probes before-edit {b}, after-edit {a}, test-suite commands {tests}, source edits {edits}")
    json.dump(allp, open('probes.json', 'w'), indent=1)
