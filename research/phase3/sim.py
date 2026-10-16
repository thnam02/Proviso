import json, os, shutil, subprocess, sys, time
sys.path.insert(0, '/home/claude/phase0')
from mutants import MUTANTS
from dc_engine import proviso as P
SC = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.join(SC, 'repo')
cfg = {"context": True, "trajectory": True, "tests": True, "python": sys.executable}
os.makedirs(os.path.join(REPO, '.dc-engine'), exist_ok=True)
json.dump(cfg, open(os.path.join(REPO, '.dc-engine', 'proviso.json'), 'w'))
task = json.load(open([os.path.join('/home/claude/proviso-dev/eval/tasks', f) for f in os.listdir('/home/claude/proviso-dev/eval/tasks') if f.startswith('98bedf')][0]))
# state as if the agent's session started at the base commit
st = {"base_sha": subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True).stdout.strip(), "base_state": "none", "blocks": 0}
P.save_state(REPO, st)
out = P.handle_event('proviso-context', {"prompt": task['prompt']}, REPO)
ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
print('CONTEXT chars', len(ctx)); print(ctx[:1500]); print('...')
probes = json.load(open('/home/claude/phase0/probes.json'))['baseline/3']
for p in probes:
    cmd = "python - <<'EOF'\n" + p['code'] + "\nEOF"
    P.handle_event('proviso-capture', {"tool_name": "Bash", "tool_input": {"command": cmd}}, REPO)
print('captured', len(P.load_trajectory(REPO)))
t = time.time(); r = P.handle_event('proviso-verify', {}, REPO); print('CLEAN verify:', r or 'silent', f'{time.time()-t:.0f}s')
results = []
for mid, where, path, old, new, desc in MUTANTS:
    src = open(os.path.join(REPO, path)).read(); assert src.count(old) == 1, mid
    open(os.path.join(REPO, path), 'w').write(src.replace(old, new))
    s = P.load_state(REPO); s['blocks'] = 0; P.save_state(REPO, s)
    t = time.time(); r = P.handle_event('proviso-verify', {}, REPO)
    reason = r.get('reason', '') if r else ''
    hard = 'looks unintended' in reason
    results.append((mid, where, bool(r), hard, round(time.time()-t)))
    print(mid, where, 'BLOCK' if r else 'silent', '(hard)' if hard else '(soft)' if r else '', f'{time.time()-t:.0f}s', '|', reason.split('\n')[1][:150] if r else '', flush=True)
    open(os.path.join(REPO, path), 'w').write(src)
print('caught', sum(1 for r in results if r[2]), 'of', len(results))
json.dump(results, open(os.path.join(SC, 'sim_results.json'), 'w'))
