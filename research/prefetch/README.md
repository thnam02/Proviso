# Pre-fetch ceiling (oracle) test

Question: if an agent is given, up front, exactly what baseline agents read and ran before their first edit, does it
skip exploration, and how much does that save? This is the upper bound for the pre-fetch redesign.

Setup: same 4 tasks as the pilot (08f2405cfd, 1f8d15bbd6, 7d9a6cd599, 818483464b), 2 reps, `oracle` arm, Claude Code
with claude-sonnet-5-5, offline, host auth. Compared against the pilot's 8 baseline runs (same day, same harness).
8 new runs, $1.80. Eval dirs `/home/claude/eval-oracle-a`, `/home/claude/eval-oracle-b`.

- Briefs (`oracle_briefs/`, `build_oracle_briefs.py`): every main-agent tool call and result before the first
  editing request, from all 4 baseline runs of the task (2 screening + 2 pilot), paths made repo-relative,
  duplicates and failed tool calls dropped, capped at 36,000 characters (about 15.6k tokens); plus the 4 tests that
  already fail at the base commit (pytz not installed). All content is from the base commit; nothing from the fix.
- Delivery: Claude Code replaces any hook output over about 10,000 characters with a 2 KB preview and a file path
  (found with a marker probe before the runs). Briefs are therefore split on block boundaries into up to 5 parts of
  at most 9,000 characters, each from its own UserPromptSubmit hook (`proviso-brief-1..5`). A probe confirmed all
  parts reach the model intact.

## Result

| mean per run | baseline | oracle pre-fetch | paired change (95% CI) |
|---|---|---|---|
| model requests | 11.4 | 6.3 | −45% (−52% to −38%) |
| request of the first edit | 5.6 | 1.5 | |
| exploration requests | 6.1 | 1.6 | |
| all-in tokens | 435k | 294k | −32% (−42% to −19%) |
| cost | $0.249 | $0.225 | −9% (−18% to −3%) |
| wall time | 113 s | 57 s | −45% (−55% to −36%) |
| hidden-test score | 0.948 | 0.941 | |
| existing tests broken | 0 | 0 | |
| full-suite runs by the agent | 1.1 | 0.0 | |

Cost split per run: cache writes $0.125 → $0.138, cache reads $0.118 → $0.076, output $0.013 → $0.011.

## Reading

1. Exploration collapses when the information is there: the first edit moves from request 5.6 to 1.5, and the one
   remaining read is mostly Claude Code's Edit tool requiring a file to be read before it can be edited.
2. Tokens and time fall by a third to a half. Dollars fall less (−9%) because the brief itself is cached once at
   write price (first request 41k tokens vs 25k): a 15.6k-token brief costs about as much to write as the requests
   it removes save in cache reads.
3. So the product brief must be compact. At about 5k tokens with the same request reduction, the estimated cost
   change is about −25 to −30%. The design problem becomes budgeted selection: which reads remove the most requests
   per brief token. That is what trajectory mining has to learn.
4. Correctness unchanged within noise on 8 runs (one 1f8d15bbd6 rep scored 0.76; baseline reps 0.82 and 0.88).
   Listing the pre-existing failures removed every full-suite run.

Caveat: this is a ceiling. The briefs come from baseline runs on the same task (no solution content, but the exact
reads that task needed). The real system must choose reads for an unseen task from other tasks' trajectories.

# Checks A-C: does the method (not just the ceiling) work?

## A. Offline coverage of prompt-only briefs (all 26 tasks, free) — `coverage.py`, `coverage.json`

Ground truth: code units (functions, or class/module statements such as `TRANSFORMS = {...}`) the reference fix
changes ("gold"), and units baseline agents changed. Brief budget 20,000 characters (about 5k tokens).

| brief built from | gold units touched | gold files touched | tasks fully covered |
|---|---|---|---|
| prompt words only (BM25) | 26% (bodies only) | 47% | 2 / 26 |
| prompt examples executed + traced (functions that run in the example but not in a plain query) | 35% (bodies only) | 61% | 5 / 26 |
| realistic brief: traced bodies + grep lines for names in the prompt and executed expression classes | 47% | 77% | 5 / 26 |
| reference: what agents themselves had seen before their first edit | 79% | 87% | 12 / 26 |

Running the prompt's examples is the strongest signal (word search cannot connect "CAST ... CHAR(4)" to
`Parser._parse_cast`), but the realistic brief reaches about 60% of the agents' own pre-edit view. Most misses are
registry entries or new methods that never execute in the example (e.g. a `TRANSFORMS` dict entry, a new
`*_sql` method). A first category prior learned from other tasks' agent edits made ranking worse.

## B. Compact oracle (~3-4k tokens) and C. failures-only, 8 runs each — `build_variant_briefs.py`, `abc_results.json`

| mean per run | baseline | oracle (15.6k tok) | compact (3-4k tok) | failures only |
|---|---|---|---|---|
| cost | $0.249 | $0.225 | $0.214 | $0.232 |
| cost change (95% CI) | | −9% (−18, −3) | −14% (−19, −9) | −8% (−14, +1) |
| tokens change | | −32% | −14% | −10% |
| model requests | 11.4 | 6.3 | 9.9 | 10.3 |
| request of first edit | 5.6 | 1.5 | 3.5 | 5.3 |
| wall time | 113 s | 57 s | 73 s | 75 s |
| full-suite runs by the agent | 1.1 | 0 | 0 | 0 |
| hidden-test score | 0.948 | 0.941 | 0.946 | 0.948 |
| existing tests broken | 0 | 0 | 0 | 0 |

Reading:
- The compact brief kept only reads of files agents later edited, plus their snippets. It is cheap to deliver and
  gives the best dollar change (−14%), but it removes far fewer requests than the oracle (−13% vs −45%): the
  searches and listings that were dropped were doing much of the locating.
- The failures line alone removes every full-suite run and gives about half the compact brief's cost effect
  (−8%, CI crosses zero) and a quarter less wall time. It is simple and not novel.
- So the code content adds roughly 6 points of cost and 4 points of requests over the failures line, with the
  compact selection used here. The estimated −25-30% for a 5k brief is not supported.
