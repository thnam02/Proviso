"""dc-eval mine | run | report | probe-overhead"""

from __future__ import annotations

import argparse
import os
import sys

from . import (
    ALL_ARMS,
    DEFAULT_ARMS,
    DEFAULT_ARM_SEED,
    DEFAULT_BUDGET_USD,
    DEFAULT_MODEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_S,
    MAX_NON_TEST_LINES,
)
from .arms import parse_arms
from .report import write_report
from .run import SafetyError, grade_runs, run_eval
from .mine import mine_repo
from .usage_import import import_usage


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
    m.add_argument(
        "--no-verify", action="store_true",
        help="skip pytest (fast; use on large repos). Default verify caps tests and times out at 60s",
    )

    def _task_select(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--tasks", nargs="+", metavar="ID", dest="tasks",
            help="only tasks whose id starts with one of these prefixes "
                 "(each prefix must match exactly one task)",
        )
        sp.add_argument(
            "--exclude", nargs="+", metavar="ID", dest="exclude",
            help="drop tasks whose id starts with one of these prefixes "
                 "(each prefix must match exactly one task)",
        )

    r = sub.add_parser("run", help="run baseline vs layer (interleaved)")
    _eval_dir(r)
    _task_select(r)
    r.add_argument("--reps", type=int, default=DEFAULT_REPS)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--max-budget-usd", type=float, default=DEFAULT_BUDGET_USD)
    r.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="wall-clock seconds per run")
    r.add_argument(
        "--arm", choices=("both",) + ALL_ARMS, default="both",
        help="legacy single-arm selector (default: both = baseline,layer)",
    )
    r.add_argument(
        "--arms", default=None,
        help=f"comma-separated arms (default: {DEFAULT_ARMS}). "
             f"Known: {', '.join(ALL_ARMS)}",
    )
    r.add_argument(
        "--seed", type=int, default=DEFAULT_ARM_SEED,
        help="shuffle arm order within each (task, rep); default 0",
    )
    r.add_argument("--claude", default="claude", help="Claude Code binary")
    r.add_argument("--runner", choices=("claude", "cursor"), default="claude")
    r.add_argument(
        "--resume", action="store_true",
        help="skip finished agents; re-grade runs whose status is grading_error",
    )
    r.add_argument(
        "--fresh", action="store_true",
        help="archive existing run dirs for the selected tasks under "
             "eval/runs_archive/<timestamp>/, then start",
    )
    r.add_argument("--agent", default="agent", help="Cursor CLI binary (default: agent)")

    rp = sub.add_parser("report", help="write eval/report.md from eval/results.jsonl")
    _eval_dir(rp)
    _task_select(rp)

    g = sub.add_parser("grade", help="re-grade saved run copies without launching an agent")
    _eval_dir(g)
    _task_select(g)

    iu = sub.add_parser("import-usage", help="match a Cursor dashboard usage CSV to runs")
    iu.add_argument("csv")
    _eval_dir(iu)

    po = sub.add_parser(
        "probe-overhead",
        help="cheap live runs that isolate dc-engine's fixed per-session tokens",
    )
    _eval_dir(po)
    po.add_argument("--runner", choices=("claude", "cursor"), default="cursor")
    po.add_argument("--model", required=True)
    po.add_argument("--reps", type=int, default=2)
    po.add_argument("--timeout", type=int, default=180)
    po.add_argument("--agent", default="agent")
    po.add_argument("--claude", default="claude")

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
            try:
                arms = parse_arms(a.arms, a.arm)
            except ValueError as exc:
                raise SafetyError(str(exc)) from exc
            code = run_eval(
                eval_dir,
                task_ids=a.tasks,
                exclude_ids=a.exclude,
                arms=arms,
                reps=a.reps,
                dry_run=a.dry_run,
                model=a.model,
                budget_usd=a.max_budget_usd,
                timeout_s=a.timeout,
                claude_bin=a.claude,
                runner=a.runner,
                resume=a.resume,
                fresh=a.fresh,
                agent_bin=a.agent,
                seed=a.seed,
            )
            sys.exit(code)
        if a.cmd == "report":
            path = write_report(eval_dir, task_ids=a.tasks, exclude_ids=a.exclude)
            print(path)
            return
        if a.cmd == "grade":
            code = grade_runs(eval_dir, task_ids=a.tasks, exclude_ids=a.exclude)
            sys.exit(code)
        if a.cmd == "import-usage":
            summary = import_usage(a.csv, eval_dir)
            print(
                f"assigned {summary['assigned']}/{summary['csv_rows']} rows; "
                f"ignored {summary['ignored']}; ambiguous {summary['ambiguous']}"
            )
            if summary["ambiguous_dates"]:
                print("ambiguous dates (not guessed): " + ", ".join(summary["ambiguous_dates"]))
            path = write_report(eval_dir)
            print(path)
            return
        if a.cmd == "probe-overhead":
            from .probe import probe_overhead
            payload = probe_overhead(
                eval_dir,
                model=a.model,
                runner=a.runner,
                reps=a.reps,
                timeout_s=a.timeout,
                agent_bin=a.agent,
                claude_bin=a.claude,
            )
            path = os.path.join(eval_dir, "overhead.md")
            with open(path, encoding="utf-8") as fh:
                sys.stdout.write(fh.read())
            oh = payload.get("fixed_overhead_tokens")
            print(
                f"fixed overhead (layer − baseline): {oh} tokens/session",
                file=sys.stderr,
            )
            return
    except SafetyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
