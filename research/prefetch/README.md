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
