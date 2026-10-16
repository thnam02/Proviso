import json, os, re, subprocess, sys, glob, shutil, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
SRC='/home/claude/sources/sqlglot'
ENV=lambda r: {'PATH':'/usr/bin:/bin:/usr/local/bin','PYTHONPATH':r,'HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1'}
TASKDIR='/home/claude/proviso-dev/eval/tasks'
def junit(root, tag, tries=3):
    x=f'/home/claude/p2/fp-{tag}.xml'
    if os.path.exists(x): os.remove(x)
    for _ in range(tries):
      subprocess.run(['python3','-m','pytest','-q','-p','no:cacheprovider','--tb=no','--continue-on-collection-errors',f'--junitxml={x}','tests'],cwd=root,env=ENV(root),capture_output=True,text=True,timeout=900)
      if os.path.exists(x): break
    res={}
    for c in ET.parse(x).iter('testcase'):
        parts=(c.get('classname') or '').split('.')
        res[f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{c.get('name')}"]=not any(ch.tag in ('failure','error','skipped') for ch in c)
    return res
def one(pre):
    t=json.load(open(next(os.path.join(TASKDIR,f) for f in os.listdir(TASKDIR) if f.startswith(pre))))
    fix=subprocess.run(['git','-C',SRC,'rev-parse',pre],capture_output=True,text=True).stdout.strip()
    base=subprocess.run(['git','-C',SRC,'rev-parse',fix+'^'],capture_output=True,text=True).stdout.strip()
    B=f'/home/claude/p2/wt/{pre}/base'; F=f'/home/claude/p2/wt/{pre}/fix'
    rb=junit(B, pre+'-b'); rf=junit(F, pre+'-f')
    tfiles=set(re.findall(r'^diff --git a/(\S+)', t['test_patch'], re.M))
    def existed(node):
        path,cls,name=node.split('::')
        if path not in tfiles: return True
        src=subprocess.run(['git','-C',SRC,'show',f'{base}:{path}'],capture_output=True,text=True).stdout
        return bool(re.search(rf"def {re.escape(name)}\(", src))
    hidden=set(t['hidden_tests'])
    both=[k for k in rf if rf.get(k) and rb.get(k) and k not in hidden]
    existing=sorted(k for k in both if existed(k)); new=sorted(k for k in both if not existed(k))
    return pre, {'existing':existing,'new_pass_at_base':new,'base_total':len(rb),'fix_total':len(rf)}
ids=sys.argv[1].split(',')
with ThreadPoolExecutor(2) as ex: out=dict(ex.map(one, ids))
prev=json.load(open('/home/claude/p2/fullpools.json')) if os.path.exists('/home/claude/p2/fullpools.json') else {}
prev.update(out); json.dump(prev,open('/home/claude/p2/fullpools.json','w'),indent=1)
for pre,v in out.items(): print(pre,'existing regression tests',len(v['existing']),'new-in-fix passing at base',len(v['new_pass_at_base']),[n.split('::')[-1] for n in v['new_pass_at_base']][:4])
