import json, os, re, random, shutil, subprocess, glob
from concurrent.futures import ThreadPoolExecutor
SRC='/home/claude/sources/sqlglot'
OPS=[(r' == ', ' != '), (r' != ', ' == '), (r' and ', ' or '), (r' or ', ' and '), (r'\bTrue\b', 'False'), (r'\bFalse\b', 'True'), (r'\bnot ', ''), (r' \+ 1\b', ' - 1'), (r' < ', ' <= '), (r' > ', ' >= ')]
ENV=lambda r: {'PATH':'/usr/bin:/bin','PYTHONPATH':r,'HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1'}
def pytest(root, args):
    p=subprocess.run(['python3','-m','pytest','-q','-x','-p','no:cacheprovider','--tb=no',*args],cwd=root,env=ENV(root),capture_output=True,text=True,timeout=600)
    return p.returncode
def changed_lines(base, fix, path):
    d=subprocess.run(['git','-C',SRC,'diff','-U0',base,fix,'--',path],capture_output=True,text=True).stdout
    s=set()
    for m in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', d, re.M):
        a=int(m.group(1)); n=int(m.group(2) or 1); s.update(range(a, a+n))
    return s
def task_mutants(pre, v, n=6):
    fixroot=f'/home/claude/p2/wt/{pre}/fix'
    files=[l.split('\t')[2] for l in subprocess.run(['git','-C',SRC,'diff','--numstat',v['base'],v['fix']],capture_output=True,text=True).stdout.strip().splitlines()]
    files=[f for f in files if f.startswith('sqlglot/') and f.endswith('.py')]
    cands=[]
    for f in files:
        lines=open(os.path.join(fixroot,f)).read().split('\n'); ch=changed_lines(v['base'],v['fix'],f)
        for i,l in enumerate(lines,1):
            s=l.strip()
            if i in ch or not s or s.startswith(('#','"','\'','def ','class ','import','from ')): continue
            for pat,rep in OPS:
                if re.search(pat,l): cands.append((f,i,pat,rep)); break
    random.Random(pre).shuffle(cands)
    return cands[:n]
def run_task(pre):
    v=json.load(open(glob.glob(f'/home/claude/p2/verify-*.json')[0])) if False else None
    ver={}
    for f in glob.glob('/home/claude/p2/verify-*.json'): ver.update(json.load(open(f)))
    v=ver[pre]; fixroot=f'/home/claude/p2/wt/{pre}/fix'
    regr=json.load(open('/home/claude/p2/pools.json'))[pre]; files=v['test_files']
    res=[]
    for k,(f,i,pat,rep) in enumerate(task_mutants(pre,v)):
        d=f'/home/claude/p2/a8/{pre}/{k}'; shutil.rmtree(d,ignore_errors=True); shutil.copytree(fixroot,d)
        p=os.path.join(d,f); lines=open(p).read().split('\n'); lines[i-1]=re.sub(pat,rep,lines[i-1],count=1); open(p,'w').write('\n'.join(lines))
        full_kill = pytest(d, files)!=0
        regr_kill = pytest(d, regr)!=0
        res.append({'file':f,'line':i,'op':pat.strip(),'full_files_kill':full_kill,'regression_kill':regr_kill})
        shutil.rmtree(d,ignore_errors=True)
    return pre,res
if __name__=='__main__':
    ids=[x.split('-')[0] for x in sorted(os.listdir('/home/claude/eval-screen/tasks'))]
    with ThreadPoolExecutor(4) as ex: out=dict(ex.map(run_task, ids))
    json.dump(out,open('/home/claude/p2/a8_full.json','w'),indent=1)
    tk=tf=tr=0
    for pre,res in out.items():
        valid=[r for r in res if r['full_files_kill']]; caught=[r for r in valid if r['regression_kill']]
        tk+=len(res); tf+=len(valid); tr+=len(caught)
        print(pre, f'mutants {len(res)}, killed by full test files {len(valid)}, caught by regression set {len(caught)}')
    print(f'TOTAL mutants {tk}, killed by full files {tf}, caught by regression set {tr} ({tr/max(tf,1):.0%})')
