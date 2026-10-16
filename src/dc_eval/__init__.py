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
ALL_ARMS = ("baseline", "tools", "contracts", "layer", "proviso", "replay-only", "tests-only")
DEFAULT_ARMS = "baseline,layer"
DEFAULT_ARM_SEED = 0
DEFAULT_REPS = 3
DEFAULT_TIMEOUT_S = 20 * 60
DEFAULT_BUDGET_USD = 2.0
DEFAULT_MODEL = "sonnet"
MAX_NON_TEST_LINES = 60
MAX_REGRESSION_TESTS = 40
MAX_HIDDEN_VERIFY = 40
MINE_PYTEST_TIMEOUT = 60
BOOTSTRAP_SEED = 0
BOOTSTRAP_RESAMPLES = 10_000
CONSECUTIVE_SETUP_STOP = 2
SETUP_LOG = "setup.log"
