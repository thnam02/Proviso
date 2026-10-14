"""Eval harness: does dc-engine make Claude Code cheaper and more correct?

Stdlib only. Never imports dc_engine. Tests must not call the real Claude CLI.
"""

__version__ = "0.1.0"

SAFETY_WARNING = (
    "WARNING: each run gives the agent Bash (full shell) plus file edits. "
    "A buggy or prompt-injected agent can delete files, leak secrets, or "
    "run anything the OS user can. Run this harness inside a container or VM, "
    "not on a machine with credentials or irreplaceable data."
)

ARMS = ("baseline", "layer")
DEFAULT_REPS = 3
DEFAULT_TIMEOUT_S = 20 * 60
DEFAULT_BUDGET_USD = 2.0
DEFAULT_MODEL = "sonnet"
MAX_NON_TEST_LINES = 60
BOOTSTRAP_SEED = 0
BOOTSTRAP_RESAMPLES = 10_000
