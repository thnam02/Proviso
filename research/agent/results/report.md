# dc-eval report

## dc-engine versions

Runs grouped by dc-engine commit:

| commit | dirty | path | runs |
|---|---|---|---:|
| 5b92940350cf | e3b0c44298fc | /home/agentrun/Proviso/src/dc_engine | 72 |

## Per-arm summary

| arm | runs | resolved | hidden checks | requests | tokens | tokens/request | time | read calls | dc-engine calls | contracts created | contract retries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 24 | 3 | 93% | 24.875 | 13888215 | 22338.620 | 2852.6 | 122 | 0 | 0 | 0 |
| impact | 24 | 4 | 93% | 24.500 | 12520158 | 20747.051 | 2113.4 | 146 | 0 | 0 | 0 |
| impact-noreport | 24 | 6 | 94% | 20.958 | 10826215 | 21220.175 | 1887.9 | 109 | 0 | 0 | 0 |

## Tool result sizes

Size of the result text returned to the agent for each completed tool call (chars, ~tokens = chars/4). MCP calls are grouped by dc-engine tool name. Totals are summed over the runs below (including contaminated).

### baseline

Total returned chars: **647702** (~161926 tokens).

| tool | chars | ~tokens |
|---|---:|---:|
| Bash | 376165 | 94042 |
| Read | 157460 | 39365 |
| Grep | 111364 | 27841 |
| Edit | 2594 | 649 |
| bash | 119 | 30 |

### impact

Total returned chars: **613296** (~153324 tokens).

| tool | chars | ~tokens |
|---|---:|---:|
| Bash | 318618 | 79655 |
| Read | 156359 | 39090 |
| Grep | 133611 | 33403 |
| Edit | 4589 | 1148 |
| bash | 119 | 30 |

### impact-noreport

Total returned chars: **490033** (~122509 tokens).

| tool | chars | ~tokens |
|---|---:|---:|
| Bash | 275459 | 68865 |
| Read | 120904 | 30226 |
| Grep | 92663 | 23166 |
| Edit | 888 | 222 |
| bash | 119 | 30 |

### Layer: largest dc-engine responses

No dc-engine tool results on the layer arm.

## Model requests

A request is a distinct `model_call_id` when the stream has one, otherwise an assistant event. tokens/request = run tokens / requests.

| task | arm | rep | requests | tokens | tokens/request |
|---|---|---:|---:|---:|---:|
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact | 1 | 23 | 409187 | 17790.739 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact-noreport | 1 | 16 | 309593 | 19349.562 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact | 2 | 15 | 271780 | 18118.667 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact-noreport | 2 | 28 | 660071 | 23573.964 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact-noreport | 1 | 14 | 351441 | 25102.929 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact | 1 | 15 | 330524 | 22034.933 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact | 2 | 22 | 506290 | 23013.182 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact-noreport | 2 | 14 | 306796 | 21914 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact | 1 | 44 | 727416 | 16532.182 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact-noreport | 1 | 34 | 769101 | 22620.618 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact-noreport | 2 | 25 | 537093 | 21483.720 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact | 2 | 31 | 776521 | 25049.065 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact-noreport | 1 | 12 | 228260 | 19021.667 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact | 1 | 14 | 310011 | 22143.643 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact | 2 | 24 | 453292 | 18887.167 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact-noreport | 2 | 25 | 577738 | 23109.520 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact | 1 | 36 | 634574 | 17627.056 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact-noreport | 1 | 27 | 535516 | 19833.926 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact-noreport | 2 | 22 | 390058 | 17729.909 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact | 2 | 25 | 430999 | 17239.960 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact | 1 | 19 | 314600 | 16557.895 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact-noreport | 1 | 16 | 346639 | 21664.938 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact-noreport | 2 | 11 | 214364 | 19487.636 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact | 2 | 11 | 213213 | 19383 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact-noreport | 1 | 31 | 674503 | 21758.161 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact | 1 | 44 | 1072439.000 | 24373.614 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact | 2 | 35 | 989623 | 28274.943 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact-noreport | 2 | 32 | 693144 | 21660.750 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact | 1 | 20 | 387372 | 19368.600 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact-noreport | 1 | 25 | 615283 | 24611.320 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact | 2 | 27 | 704190 | 26081.111 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact-noreport | 2 | 21 | 470550 | 22407.143 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact-noreport | 1 | 25 | 560385 | 22415.400 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact | 1 | 41 | 1104063.000 | 26928.366 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact | 2 | 30 | 738609 | 24620.300 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact-noreport | 2 | 28 | 633568 | 22627.429 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact-noreport | 1 | 14 | 265950 | 18996.429 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact | 1 | 16 | 288001 | 18000.062 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact | 2 | 17 | 317530 | 18678.235 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact-noreport | 2 | 21 | 386322 | 18396.286 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact-noreport | 1 | 14 | 251829 | 17987.786 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact | 1 | 14 | 236761 | 16911.500 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact-noreport | 2 | 10 | 175471 | 17547.100 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact | 2 | 22 | 346754 | 15761.545 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact | 1 | 24 | 527488 | 21978.667 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact-noreport | 1 | 20 | 448278 | 22413.900 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact-noreport | 2 | 18 | 424262 | 23570.111 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact | 2 | 19 | 428921 | 22574.789 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | baseline | 1 | 20 | 278567 | 13928.350 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | baseline | 2 | 20 | 411098 | 20554.900 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | baseline | 1 | 14 | 349031 | 24930.786 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | baseline | 2 | 26 | 682285 | 26241.731 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | baseline | 1 | 30 | 698672 | 23289.067 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | baseline | 2 | 28 | 690368 | 24656 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | baseline | 1 | 21 | 424749 | 20226.143 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | baseline | 2 | 18 | 369360 | 20520 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | baseline | 1 | 37 | 764666 | 20666.649 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | baseline | 2 | 29 | 551459 | 19015.828 |
| 646295528c-fix-postgres-transpile-day-month-year-to | baseline | 1 | 17 | 391502 | 23029.529 |
| 646295528c-fix-postgres-transpile-day-month-year-to | baseline | 2 | 11 | 215339 | 19576.273 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | baseline | 1 | 42 | 1186777.000 | 28256.595 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | baseline | 2 | 40 | 1017781.000 | 25444.525 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | baseline | 1 | 40 | 1215446.000 | 30386.150 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | baseline | 2 | 28 | 822041 | 29358.607 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | baseline | 1 | 43 | 1041637.000 | 24224.116 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | baseline | 2 | 31 | 713510 | 23016.452 |
| 9114355463-feat-mysql-allow-constraints-without-nam | baseline | 1 | 11 | 221256 | 20114.182 |
| 9114355463-feat-mysql-allow-constraints-without-nam | baseline | 2 | 20 | 443511 | 22175.550 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | baseline | 1 | 13 | 206859 | 15912.231 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | baseline | 2 | 14 | 245833 | 17559.500 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | baseline | 1 | 23 | 489326 | 21275.043 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | baseline | 2 | 21 | 457142 | 21768.667 |

| arm | mean requests | mean tokens | mean tokens/request |
|---|---:|---:|---:|
| baseline | 24.875 | 578675.625 | 22338.620 |
| impact | 24.500 | 521673.250 | 20747.051 |
| impact-noreport | 20.958 | 451092.292 | 21220.175 |

## Tool surface (static)

Exact text dc-engine exposes: server instructions plus each tool's name, description, and input schema. ~tokens = chars/4.

Before (full): **8246** chars (~2062 tokens, 20 tools). After (slim): **3543** chars (~886 tokens, 5 tools).

### full

instructions: 594 chars (~149 tokens, 84 words)

| tool | chars | ~tokens |
|---|---:|---:|
| (instructions) | 594 | 149 |
| dc_start | 401 | 101 |
| dc_get_symbol | 236 | 59 |
| dc_replace_symbol | 479 | 120 |
| dc_contract | 1553 | 389 |
| dc_find | 270 | 68 |
| dc_repo_map | 242 | 61 |
| dc_find_symbol | 242 | 61 |
| dc_get_slice | 643 | 161 |
| dc_find_references | 242 | 61 |
| dc_file_outline | 155 | 39 |
| dc_insert_symbol | 361 | 91 |
| dc_index_status | 115 | 29 |
| dc_create_contract | 1053 | 264 |
| dc_check_contract | 232 | 58 |
| dc_get_contract | 161 | 41 |
| dc_list_contracts | 92 | 23 |
| dc_close_contract | 271 | 68 |
| dc_amend_contract | 408 | 102 |
| dc_list_checkpoints | 166 | 42 |
| dc_restore_checkpoint | 290 | 73 |
| TOTAL | 8246 | 2062 |

```
Call dc_start(task) FIRST. Output is the exact current source of shown
symbols; do not re-read those files unless something was omitted.

Then dc_contract(action=create) before any Python edit. Edit with
dc_replace_symbol; its result includes contract status. dc_find looks up
symbols or (mode=references) call sites. dc_get_symbol loads one symbol;
include_body=true for source.

Fix every ✗. Amend or close via dc_contract. Hooks deny Python edits without
an active contract. Do not stop while the score is below 1.0. Names:
pkg.mod.Class.method or a unique suffix; @L<line> picks duplicates.
```

#### dc_start

```
dc_start
First call on a task. One response: repo size, compressed map,
slices for hint_symbols or best-matching names/docs, a contract
template, and a complete JSON example. On a small repo, skip
exploration and read files directly.
{"type":"object","properties":{"task":{"type":"string"},"hint_symbols":{"type":"array","items":{"type":"string"}},"max_tokens":{"type":"integer"}},"required":["task"]}
```

#### dc_get_symbol

```
dc_get_symbol
One symbol's signature, docstring, what it calls, who calls it, and
(with include_body=true) its exact source.
{"type":"object","properties":{"name":{"type":"string"},"include_body":{"type":"boolean"}},"required":["name"]}
```

#### dc_replace_symbol

```
dc_replace_symbol
Replace one function/method/class with `new_code` (its complete new
definition, decorators included; indentation is fixed automatically).
Rejected without changes if the file would not parse. Reports only
lint/type errors the edit introduced and callers a signature change
may break. Result includes contract status.
{"type":"object","properties":{"name":{"type":"string"},"new_code":{"type":"string"},"check":{"type":"boolean"}},"required":["name","new_code"]}
```

#### dc_contract

```
dc_contract
Create, amend, check, or close a delta contract. action is create | amend | check | close. create needs task, targets, must_change (must_preserve optional). amend, check, and close need contract_id; amend takes add_targets / add_must_change / add_must_preserve. Declare a delta contract before editing. `must_change` / `must_preserve` are JSON objects: {id, setup?, call, expect_old?, expect_new?}. Expect values are JSON objects: {"returns": "<repr>"} for a normalised return value, or {"raises": "ValueError"} for an exception class name. must_change probes require expect_new. Probe setup auto-imports each target (`from pkg.mod import func` or `from pkg.mod import Class` for a method). Returns the contract id, one line per probe, and the validation verdict. Full probe code is echoed only when validation fails. ✗ with a corrected example if a target does not resolve or expect_old does not match the baseline. A complete JSON example is in the dc_start response.
{"type":"object","properties":{"action":{"type":"string"},"task":{"type":"string"},"targets":{"type":"array","items":{"type":"string"}},"must_change":{"type":"array","items":{"type":"object"}},"must_preserve":{"type":"array","items":{"type":"object"}},"pytest_ids":{"type":"array","items":{"type":"string"}},"contract_id":{"type":"string"},"add_targets":{"type":"array","items":{"type":"string"}},"add_must_change":{"type":"array","items":{"type":"object"}},"add_must_preserve":{"type":"array","items":{"type":"object"}},"reason":{"type":"string"}},"required":["action"]}
```

#### dc_find

```
dc_find
Find symbols by (partial) name, or with mode=references every
resolved call site of a symbol (plus name-matched unresolved sites).
{"type":"object","properties":{"query":{"type":"string"},"mode":{"type":"string"},"limit":{"type":"integer"}},"required":["query"]}
```

#### dc_repo_map

```
dc_repo_map
Outline of the repo: files with class/function signatures and line
numbers, compressed to fit max_tokens. Use path_prefix to zoom in.
{"type":"object","properties":{"path_prefix":{"type":"string"},"max_tokens":{"type":"integer"}}}
```

#### dc_find_symbol

```
dc_find_symbol
Find functions, methods and classes by (partial) name. Returns
qualified names, locations, signatures and one-line docs.
{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer"}},"required":["query"]}
```

#### dc_get_slice

```
dc_get_slice
Context for changing `targets`: their source, plus signatures of
their callees and callers up to `depth` hops, class context, and calls
whose target could not be resolved statically. Bodies are included
only for the targets unless include_test_bodies=true. include_tests=true
adds test functions that call the targets (name-matched). Fits max_tokens.
{"type":"object","properties":{"targets":{"type":"array","items":{"type":"string"}},"depth":{"type":"integer"},"max_tokens":{"type":"integer"},"include_bodies":{"type":"boolean"},"include_tests":{"type":"boolean"},"include_test_bodies":{"type":"boolean"}},"required":["targets"]}
```

#### dc_find_references

```
dc_find_references
Every resolved call site of a symbol, plus possible call sites
where the receiver's type is unknown (matched by name).
{"type":"object","properties":{"name":{"type":"string"},"limit":{"type":"integer"}},"required":["name"]}
```

#### dc_file_outline

```
dc_file_outline
Signatures and line ranges of everything defined in one file.
{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}
```

#### dc_insert_symbol

```
dc_insert_symbol
Add new definitions: after=<symbol> inserts right after it at the
same indentation (e.g. a new method after an existing one);
path=<file> appends at the end of a file (created if missing).
{"type":"object","properties":{"code":{"type":"string"},"after":{"type":"string"},"path":{"type":"string"},"check":{"type":"boolean"}},"required":["code"]}
```

#### dc_index_status

```
dc_index_status
Index size, call-graph coverage and which checkers are available.
{"type":"object","properties":{}}
```

#### dc_create_contract

```
dc_create_contract
Declare a delta contract before editing. `must_change` / `must_preserve` are JSON objects: {id, setup?, call, expect_old?, expect_new?}. Expect values are JSON objects: {"returns": "<repr>"} for a normalised return value, or {"raises": "ValueError"} for an exception class name. must_change probes require expect_new. Probe setup auto-imports each target (`from pkg.mod import func` or `from pkg.mod import Class` for a method). Returns the contract id, one line per probe, and the validation verdict. Full probe code is echoed only when validation fails. ✗ with a corrected example if a target does not resolve or expect_old does not match the baseline. A complete JSON example is in the dc_start response.
{"type":"object","properties":{"task":{"type":"string"},"targets":{"type":"array","items":{"type":"string"}},"must_change":{"type":"array","items":{"type":"object"}},"must_preserve":{"type":"array","items":{"type":"object"}},"pytest_ids":{"type":"array","items":{"type":"string"}}},"required":["task","targets","must_change"]}
```

#### dc_check_contract

```
dc_check_contract
Compare baseline vs the working tree for one contract. Compact
✓/✗ report and a score (satisfied / scorable). Fix every ✗.
{"type":"object","properties":{"contract_id":{"type":"string"}},"required":["contract_id"]}
```

#### dc_get_contract

```
dc_get_contract
Show a saved contract: task, targets, probes, status.
{"type":"object","properties":{"contract_id":{"type":"string"}},"required":["contract_id"]}
```

#### dc_list_contracts

```
dc_list_contracts
List saved contracts (id, status, task).
{"type":"object","properties":{}}
```

#### dc_close_contract

```
dc_close_contract
Mark a contract closed. If the score is below 1.0, `reason` is
required. The contract JSON is kept; only the baseline tree is removed.
{"type":"object","properties":{"contract_id":{"type":"string"},"reason":{"type":"string"}},"required":["contract_id"]}
```

#### dc_amend_contract

```
dc_amend_contract
Add targets or probes to an open contract. New probes are validated
against the frozen baseline, same as at creation.
{"type":"object","properties":{"contract_id":{"type":"string"},"add_targets":{"type":"array","items":{"type":"string"}},"add_must_change":{"type":"array","items":{"type":"object"}},"add_must_preserve":{"type":"array","items":{"type":"object"}}},"required":["contract_id"]}
```

#### dc_list_checkpoints

```
dc_list_checkpoints
List score checkpoints for a contract (n, score, ref).
{"type":"object","properties":{"contract_id":{"type":"string"}},"required":["contract_id"]}
```

#### dc_restore_checkpoint

```
dc_restore_checkpoint
Roll the working tree back to checkpoint n. Only files that differ
are overwritten; untracked files the checkpoint doesn't know about
are left alone.
{"type":"object","properties":{"contract_id":{"type":"string"},"n":{"type":"integer"}},"required":["contract_id","n"]}
```

### slim

instructions: 594 chars (~149 tokens, 84 words)

| tool | chars | ~tokens |
|---|---:|---:|
| (instructions) | 594 | 149 |
| dc_start | 401 | 101 |
| dc_get_symbol | 236 | 59 |
| dc_replace_symbol | 479 | 120 |
| dc_contract | 1553 | 389 |
| dc_find | 270 | 68 |
| TOTAL | 3543 | 886 |

```
Call dc_start(task) FIRST. Output is the exact current source of shown
symbols; do not re-read those files unless something was omitted.

Then dc_contract(action=create) before any Python edit. Edit with
dc_replace_symbol; its result includes contract status. dc_find looks up
symbols or (mode=references) call sites. dc_get_symbol loads one symbol;
include_body=true for source.

Fix every ✗. Amend or close via dc_contract. Hooks deny Python edits without
an active contract. Do not stop while the score is below 1.0. Names:
pkg.mod.Class.method or a unique suffix; @L<line> picks duplicates.
```

#### dc_start

```
dc_start
First call on a task. One response: repo size, compressed map,
slices for hint_symbols or best-matching names/docs, a contract
template, and a complete JSON example. On a small repo, skip
exploration and read files directly.
{"type":"object","properties":{"task":{"type":"string"},"hint_symbols":{"type":"array","items":{"type":"string"}},"max_tokens":{"type":"integer"}},"required":["task"]}
```

#### dc_get_symbol

```
dc_get_symbol
One symbol's signature, docstring, what it calls, who calls it, and
(with include_body=true) its exact source.
{"type":"object","properties":{"name":{"type":"string"},"include_body":{"type":"boolean"}},"required":["name"]}
```

#### dc_replace_symbol

```
dc_replace_symbol
Replace one function/method/class with `new_code` (its complete new
definition, decorators included; indentation is fixed automatically).
Rejected without changes if the file would not parse. Reports only
lint/type errors the edit introduced and callers a signature change
may break. Result includes contract status.
{"type":"object","properties":{"name":{"type":"string"},"new_code":{"type":"string"},"check":{"type":"boolean"}},"required":["name","new_code"]}
```

#### dc_contract

```
dc_contract
Create, amend, check, or close a delta contract. action is create | amend | check | close. create needs task, targets, must_change (must_preserve optional). amend, check, and close need contract_id; amend takes add_targets / add_must_change / add_must_preserve. Declare a delta contract before editing. `must_change` / `must_preserve` are JSON objects: {id, setup?, call, expect_old?, expect_new?}. Expect values are JSON objects: {"returns": "<repr>"} for a normalised return value, or {"raises": "ValueError"} for an exception class name. must_change probes require expect_new. Probe setup auto-imports each target (`from pkg.mod import func` or `from pkg.mod import Class` for a method). Returns the contract id, one line per probe, and the validation verdict. Full probe code is echoed only when validation fails. ✗ with a corrected example if a target does not resolve or expect_old does not match the baseline. A complete JSON example is in the dc_start response.
{"type":"object","properties":{"action":{"type":"string"},"task":{"type":"string"},"targets":{"type":"array","items":{"type":"string"}},"must_change":{"type":"array","items":{"type":"object"}},"must_preserve":{"type":"array","items":{"type":"object"}},"pytest_ids":{"type":"array","items":{"type":"string"}},"contract_id":{"type":"string"},"add_targets":{"type":"array","items":{"type":"string"}},"add_must_change":{"type":"array","items":{"type":"object"}},"add_must_preserve":{"type":"array","items":{"type":"object"}},"reason":{"type":"string"}},"required":["action"]}
```

#### dc_find

```
dc_find
Find symbols by (partial) name, or with mode=references every
resolved call site of a symbol (plus name-matched unresolved sites).
{"type":"object","properties":{"query":{"type":"string"},"mode":{"type":"string"},"limit":{"type":"integer"}},"required":["query"]}
```

### contracts

instructions: 367 chars (~92 tokens, 54 words)

| tool | chars | ~tokens |
|---|---:|---:|
| (instructions) | 367 | 92 |
| dc_contract | 1885 | 472 |
| dc_replace_symbol | 479 | 120 |
| TOTAL | 2735 | 684 |

```
Call dc_contract(action=create) before any Python edit. Use Read and Grep
for context.

Edit with dc_replace_symbol; its result includes contract status. Fix every
✗. Amend or close via dc_contract. Hooks deny Python edits without an
active contract. Do not stop while the score is below 1.0. Names:
pkg.mod.Class.method or a unique suffix; @L<line> picks duplicates.
```

#### dc_contract

```
dc_contract
Create, amend, check, or close a delta contract. action is create | amend | check | close. create needs task, targets, must_change (must_preserve optional). amend, check, and close need contract_id; amend takes add_targets / add_must_change / add_must_preserve. Declare a delta contract before editing. `must_change` / `must_preserve` are JSON objects: {id, setup?, call, expect_old?, expect_new?}. Expect values are JSON objects: {"returns": "<repr>"} for a normalised return value, or {"raises": "ValueError"} for an exception class name. must_change probes require expect_new. Probe setup auto-imports each target (`from pkg.mod import func` or `from pkg.mod import Class` for a method). Returns the contract id, one line per probe, and the validation verdict. Full probe code is echoed only when validation fails. ✗ with a corrected example if a target does not resolve or expect_old does not match the baseline. Example: {"action":"create","task":"reject zero charges","targets":["shop.billing.validate_amount"],"must_change":[{"id":"zero","setup":"from decimal import Decimal","call":"validate_amount(Decimal('0'))","expect_old":{"returns":"None"},"expect_new":{"raises":"ValueError"}}],"must_preserve":[{"id":"pos","setup":"from decimal import Decimal","call":"validate_amount(Decimal('5'))"}]}
{"type":"object","properties":{"action":{"type":"string"},"task":{"type":"string"},"targets":{"type":"array","items":{"type":"string"}},"must_change":{"type":"array","items":{"type":"object"}},"must_preserve":{"type":"array","items":{"type":"object"}},"pytest_ids":{"type":"array","items":{"type":"string"}},"contract_id":{"type":"string"},"add_targets":{"type":"array","items":{"type":"string"}},"add_must_change":{"type":"array","items":{"type":"object"}},"add_must_preserve":{"type":"array","items":{"type":"object"}},"reason":{"type":"string"}},"required":["action"]}
```

#### dc_replace_symbol

```
dc_replace_symbol
Replace one function/method/class with `new_code` (its complete new
definition, decorators included; indentation is fixed automatically).
Rejected without changes if the file would not parse. Reports only
lint/type errors the edit introduced and callers a signature change
may break. Result includes contract status.
{"type":"object","properties":{"name":{"type":"string"},"new_code":{"type":"string"},"check":{"type":"boolean"}},"required":["name","new_code"]}
```

Resolved rate is the fraction of runs where every hidden test passed. Other per-task numbers below are **medians over repetitions** (resolved rate per task is the mean of 0/1 over reps).

## Paired per-task (median over reps)

| task | resolved B | resolved L | regr B | regr L | tokens B | tokens L | cost B | cost L | time B | time L |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | 0 | — | 0 | — | 344832.500 | — | $0.1629 | — | 51.701 | — |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | 0 | — | 0 | — | 515658 | — | $0.1777 | — | 99.456 | — |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | 0 | — | 0 | — | 694520 | — | $0.2342 | — | 147.077 | — |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | 0 | — | 0 | — | 397054.500 | — | $0.1651 | — | 85.918 | — |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | 0 | — | 0 | — | 658062.500 | — | $0.2355 | — | 122.239 | — |
| 646295528c-fix-postgres-transpile-day-month-year-to | 0 | — | 0 | — | 303420.500 | — | $0.1284 | — | 49.488 | — |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | 0 | — | 0 | — | 1102279.000 | — | $0.4193 | — | 183.383 | — |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | 0.500 | — | 0 | — | 1018743.500 | — | $0.3203 | — | 185.935 | — |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | 0 | — | 0 | — | 877573.500 | — | $0.3073 | — | 230.372 | — |
| 9114355463-feat-mysql-allow-constraints-without-nam | 1 | — | 0 | — | 332383.500 | — | $0.1439 | — | 104.712 | — |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | 0 | — | 0 | — | 226346 | — | $0.1043 | — | 31.525 | — |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | 0 | — | 0 | — | 473234 | — | $0.2201 | — | 134.469 | — |

## Paired difference (impact − baseline) with 95% bootstrap CI

Resamples: 10000 with `random.choices`, seed 0. Each observation is one task (median/rate over its reps). Negative cost or tokens means the impact arm was cheaper/smaller.

| metric | n | mean(L−B) | 95% CI low | 95% CI high |
|---|---:|---:|---:|---:|
| resolved rate | 12 | 0.0417 | 0.0000 | 0.1250 |
| hidden checks passed | 12 | -0.0037 | -0.0112 | 0.0011 |
| regressions | 12 | 0.0000 | 0.0000 | 0.0000 |
| tokens (all-in, incl. cache) | 12 | -57002.3750 | -146293.4167 | 6030.5417 |
| requests | 12 | -0.3750 | -2.8333 | 2.0000 |
| tokens/request | 12 | -1591.5689 | -3030.7593 | -280.2411 |
| cost (USD) | 12 | -0.0113 | -0.0346 | 0.0067 |
| wall time (s) | 12 | -30.7965 | -55.5800 | -7.1828 |
| read chars | 12 | -45.8750 | -2322.9167 | 1813.3333 |
| read calls | 12 | 1.0000 | -0.3333 | 2.3750 |
| dc-engine calls | 12 | 0.0000 | 0.0000 | 0.0000 |
| contracts created | 12 | 0.0000 | 0.0000 | 0.0000 |
| contract retries | 12 | 0.0000 | 0.0000 | 0.0000 |
| turns | 12 | -0.1667 | -1.8333 | 1.7083 |

## Paired difference (impact-noreport − baseline) with 95% bootstrap CI

Resamples: 10000 with `random.choices`, seed 0. Each observation is one task (median/rate over its reps). Negative cost or tokens means the impact-noreport arm was cheaper/smaller.

| metric | n | mean(L−B) | 95% CI low | 95% CI high |
|---|---:|---:|---:|---:|
| resolved rate | 12 | 0.1250 | 0.0000 | 0.2500 |
| hidden checks passed | 12 | 0.0094 | 0.0009 | 0.0235 |
| regressions | 12 | 0.0000 | 0.0000 | 0.0000 |
| tokens (all-in, incl. cache) | 12 | -127583.3333 | -231947.6250 | -30825.8750 |
| requests | 12 | -3.9167 | -6.6250 | -1.3333 |
| tokens/request | 12 | -1118.4446 | -2658.7969 | 436.2906 |
| cost (USD) | 12 | -0.0358 | -0.0658 | -0.0109 |
| wall time (s) | 12 | -40.1919 | -65.1441 | -16.7336 |
| read chars | 12 | -1523.1667 | -4124.9583 | 671.0000 |
| read calls | 12 | -0.5417 | -1.5833 | 0.5417 |
| dc-engine calls | 12 | 0.0000 | 0.0000 | 0.0000 |
| contracts created | 12 | 0.0000 | 0.0000 | 0.0000 |
| contract retries | 12 | 0.0000 | 0.0000 | 0.0000 |
| turns | 12 | -2.7500 | -4.4583 | -1.0833 |
