"""Run code from a task prompt at the base commit and record which package lines execute.

Usage (cwd = a checkout of the base commit): python trace_probe.py PKG_DIR SNIPPET_FILE OUT_JSON
Each top-level statement of the snippet runs on its own (an exception in one does not stop the rest).
Output: {"lines": {"rel/path.py": [line, ...]}, "errors": n}
"""

import ast
import json
import os
import sys
import threading

pkg_dir, snippet_file, out = sys.argv[1], sys.argv[2], sys.argv[3]
pkg_abs = os.path.abspath(pkg_dir)
root = os.path.dirname(pkg_abs)
sys.path.insert(0, root)
hits = {}


def tracer(frame, event, arg):
    fn = frame.f_code.co_filename
    if not fn.startswith(pkg_abs):
        return None
    code = frame.f_code
    # module and class bodies run once at import; only count code that runs inside functions
    if code.co_name == "<module>" or "__qualname__" in frame.f_locals and "__module__" in frame.f_locals:
        return tracer
    if event in ("call", "line"):
        hits.setdefault(os.path.relpath(fn, root), set()).add(frame.f_lineno)
    return tracer


src = open(snippet_file).read()
try:
    stmts = ast.parse(src).body
except SyntaxError:
    stmts = []
env, errors = {}, 0
for st in stmts:
    code = compile(ast.Module(body=[st], type_ignores=[]), "<prompt>", "exec")
    sys.settrace(tracer)
    threading.settrace(tracer)
    try:
        exec(code, env)
    except BaseException:  # noqa: BLE001 - failing examples are expected (that is the bug)
        errors += 1
    finally:
        sys.settrace(None)
json.dump({"lines": {k: sorted(v) for k, v in hits.items()}, "errors": errors}, open(out, "w"))
