"""Label mined divergent ripples (true_ripples.json from mine.py + filtering) automatically:
  crash        the child now raises, the parent's output on the same input does not
  cosmetic     before and after are equal once identifier quoting and letter case are ignored
  declared     the child's generator flags the construct as unsupported (unsupported_level=RAISE raises at commit P),
               i.e. dropping it is sqlglot's documented behaviour
  semantic     anything else: the child's output means something different now (candidate regression)
plus whether the child's changed output is still there at the newest replayed commit.
Usage: python label.py MINE_DIR REPO"""
import json, os, re, subprocess, sys, tempfile, shutil, bisect, collections
M, REPO = sys.argv[1], sys.argv[2]
rip = json.load(open(os.path.join(M, "true_ripples.json")))
probes = json.load(open(os.path.join(M, "probes.json")))
commits = json.load(open(os.path.join(M, "commits.json")))
key = {(p[0], p[1], p[2]): str(i) for i, p in enumerate(probes)}
timeline = collections.defaultdict(list)
for f in sorted(x for x in os.listdir(M) if x[:5].isdigit()):
    d = json.load(open(os.path.join(M, f)))
    for k, v in d.get("outputs", {}).items():
        timeline[k].append((int(f[:5]), v))
last = len(commits) - 1
def at(k, i):
    tl = timeline[k]; j = bisect.bisect_right([x[0] for x in tl], i) - 1
    return tl[j][1] if j >= 0 else None
norm = lambda s: re.sub(r"[`\"\[\]]", "", s or "").lower()
CODE = r'''
import json, sys, logging, warnings
logging.disable(logging.CRITICAL); warnings.filterwarnings("ignore")
from sqlglot import parse_one
from sqlglot.errors import ErrorLevel
out = []
for d, sql in json.loads(sys.argv[1]):
    try:
        parse_one(sql, read=d).sql(dialect=d, unsupported_level=ErrorLevel.RAISE)
        out.append("ok")
    except Exception as e:
        out.append(type(e).__name__)
print(json.dumps(out))
'''
by_commit = collections.defaultdict(list)
for x in rip:
    by_commit[x["commit"]].append(x)
for c, xs in by_commit.items():
    d = tempfile.mkdtemp(prefix="lab-")
    arch = subprocess.run(["git", "-C", REPO, "archive", c, "sqlglot"], capture_output=True)
    subprocess.run(["tar", "-x", "-C", d], input=arch.stdout)
    r = subprocess.run([sys.executable, "-c", CODE, json.dumps([[x["child"], x["input"]] for x in xs])], cwd=d,
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": d, "HOME": "/tmp"})
    strict = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else ["?"] * len(xs)
    shutil.rmtree(d, ignore_errors=True)
    for x, s in zip(xs, strict):
        k = key[(x["parent"], x["child"], x["input"])]
        x["at_newest"] = at(k, last)
        x["still_present"] = at(k, last) == x["child_after"]
        after, before = x["child_after"] or "", x["child_before"] or ""
        if after.startswith("EXC") and not before.startswith("EXC") and not (x["parent_after"] or "").startswith("EXC"):
            x["label"] = "crash"
        elif norm(after) == norm(before):
            x["label"] = "cosmetic"
        elif s == "UnsupportedError":
            x["label"] = "declared"
        else:
            # compare words (identifiers and keywords, quoting and case ignored) with a reference: the child's own
            # previous output, or the parent's output when the child could not handle the input before
            ref = x["parent_after"] if before.startswith("EXC") else before
            words = lambda t: collections.Counter(re.findall(r"[a-z_][a-z0-9_]*", norm(t)))
            lost = words(ref) - words(after) if ref and not ref.startswith("EXC") else collections.Counter()
            x["lost_words"] = sorted(lost)
            kind = "newly_parses" if before.startswith("EXC") else "changed"
            x["label"] = f"{kind}_lossy" if lost else kind
json.dump(rip, open(os.path.join(M, "labelled_ripples.json"), "w"), indent=1)
cnt = collections.Counter(x["label"] for x in rip)
print(dict(cnt))
g = collections.defaultdict(list)
for x in rip:
    g[(x["commit"][:10], x["child"], x["label"])].append(x)
print(len(g), "commit x child groups")
for (c, ch, lab), xs in sorted(g.items(), key=lambda kv: kv[0][2]):
    x = xs[0]
    print(f"{lab:18s} {c} {ch:11s} n={len(xs)} still={sum(y['still_present'] for y in xs)} restored={sum(bool(y['restored_at']) for y in xs)} lost={x.get('lost_words', [])[:6]}")
