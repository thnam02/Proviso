"""dc-eval mine | run | report"""

from __future__ import annotations

import argparse
import os
import sys

from . import DEFAULT_BUDGET_USD, DEFAULT_MODEL, DEFAULT_REPS, DEFAULT_TIMEOUT_S, MAX_NON_TEST_LINES
from .report import write_report
from .run import SafetyError, run_eval
from .mine import mine_repo


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="dc-eval",
        description="Measure whether dc-engine makes Claude Code cheaper and more correct.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def _eval_dir(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--eval-dir", default="eval",
            help="tasks/ runs/ report.md live here (default: ./eval)",
        )

    m = sub.add_parser("mine", help="list candidate tasks from git history")
    m.add_argument("repo", help="local git checkout (path)")
    _eval_dir(m)
    m.add_argument("--max-non-test-lines", type=int, default=MAX_NON_TEST_LINES)
    m.add_argument("--max-commits", type=int, default=200)
    m.add_argument("--no-verify", action="store_true", help="skip fail-on-parent / pass-on-commit pytest")

    r = sub.add_parser("run", help="run baseline vs layer (interleaved)")
    _eval_dir(r)
    r.add_argument("--task", action="append", dest="tasks", help="task id (repeatable). default: all")
    r.add_argument("--reps", type=int, default=DEFAULT_REPS)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--max-budget-usd", type=float, default=DEFAULT_BUDGET_USD)
    r.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="wall-clock seconds per run")
    r.add_argument("--arm", choices=("both", "baseline", "layer"), default="both")
    r.add_argument("--claude", default="claude", help="Claude Code binary")

    rp = sub.add_parser("report", help="write eval/report.md from eval/results.jsonl")
    _eval_dir(rp)

    a = p.parse_args(argv)
    eval_dir = os.path.abspath(a.eval_dir)
    try:
        if a.cmd == "mine":
            tasks = mine_repo(
                os.path.abspath(a.repo), eval_dir,
                max_non_test_lines=a.max_non_test_lines,
                max_commits=a.max_commits,
                verify=not a.no_verify,
            )
            if not tasks:
                print("no candidates (need a small non-test diff, plus tests that fail on the parent and pass on the commit)")
                sys.exit(0)
            for t in tasks:
                print(f"wrote {t.id}  base={t.commit[:10]}  hidden={len(t.hidden_tests)}  regr={len(t.regression_tests) if isinstance(t.regression_tests, list) else t.regression_tests}")
            return
        if a.cmd == "run":
            arms = ("baseline", "layer") if a.arm == "both" else (a.arm,)
            code = run_eval(
                eval_dir,
                task_ids=a.tasks,
                arms=arms,
                reps=a.reps,
                dry_run=a.dry_run,
                model=a.model,
                budget_usd=a.max_budget_usd,
                timeout_s=a.timeout,
                claude_bin=a.claude,
            )
            sys.exit(code)
        if a.cmd == "report":
            path = write_report(eval_dir)
            print(path)
            return
    except SafetyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
