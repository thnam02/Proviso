# dc-eval report

## dc-engine versions

Runs grouped by dc-engine commit:

| commit | dirty | path | runs |
|---|---|---|---:|
| 4276c9edc71d | e3b0c44298fc | /home/agentrun/Proviso/src/dc_engine | 72 |

## Per-arm summary

| arm | runs | resolved | hidden checks | requests | tokens | tokens/request | time | read calls | dc-engine calls | contracts created | contract retries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 24 | 2 | 93% | 21.042 | 4325989 | 7590.842 | 2333.4 | 0 | 0 | 0 | 0 |
| impact | 24 | 3 | 93% | 21.083 | 4278711 | 7704.032 | 2450.5 | 0 | 0 | 0 | 0 |
| impact-noreport | 24 | 3 | 92% | 21.125 | 4239404 | 7467.764 | 2257.5 | 0 | 0 | 0 | 0 |

## Tool result sizes

Size of the result text returned to the agent for each completed tool call (chars, ~tokens = chars/4). MCP calls are grouped by dc-engine tool name. Totals are summed over the runs below (including contaminated).

### baseline

Total returned chars: **559260** (~139815 tokens).

| tool | chars | ~tokens |
|---|---:|---:|
| Bash | 558903 | 139726 |
| bash | 357 | 90 |

### impact

Total returned chars: **573804** (~143451 tokens).

| tool | chars | ~tokens |
|---|---:|---:|
| Bash | 573804 | 143451 |

### impact-noreport

Total returned chars: **569204** (~142301 tokens).

| tool | chars | ~tokens |
|---|---:|---:|
| Bash | 569204 | 142301 |

### Layer: largest dc-engine responses

No dc-engine tool results on the layer arm.

## Model requests

A request is a distinct `model_call_id` when the stream has one, otherwise an assistant event. tokens/request = run tokens / requests.

| task | arm | rep | requests | tokens | tokens/request |
|---|---|---:|---:|---:|---:|
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | baseline | 1 | 13 | 66243 | 5095.615 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact | 1 | 15 | 81954 | 5463.600 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact-noreport | 1 | 16 | 101863 | 6366.438 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact | 2 | 15 | 112359 | 7490.600 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | impact-noreport | 2 | 10 | 57566 | 5756.600 |
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | baseline | 2 | 9 | 60469 | 6718.778 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | baseline | 1 | 19 | 101083 | 5320.158 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact-noreport | 1 | 20 | 107018 | 5350.900 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact | 1 | 25 | 163934 | 6557.360 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | baseline | 2 | 19 | 108526 | 5711.895 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact | 2 | 21 | 147119 | 7005.667 |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | impact-noreport | 2 | 31 | 214704 | 6925.935 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | baseline | 1 | 15 | 109929 | 7328.600 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact | 1 | 23 | 203032 | 8827.478 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact-noreport | 1 | 19 | 156225 | 8222.368 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact-noreport | 2 | 16 | 121359 | 7584.938 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | baseline | 2 | 28 | 246637 | 8808.464 |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | impact | 2 | 19 | 164479 | 8656.789 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact-noreport | 1 | 14 | 113466 | 8104.714 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | baseline | 1 | 16 | 112944 | 7059 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact | 1 | 19 | 150229 | 7906.789 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact | 2 | 11 | 60951 | 5541 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | baseline | 2 | 14 | 97113 | 6936.643 |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | impact-noreport | 2 | 22 | 173348 | 7879.455 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact | 1 | 31 | 253875 | 8189.516 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact-noreport | 1 | 25 | 167138 | 6685.520 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | baseline | 1 | 21 | 149382 | 7113.429 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact-noreport | 2 | 21 | 166580 | 7932.381 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | baseline | 2 | 22 | 136431 | 6201.409 |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | impact | 2 | 30 | 209752 | 6991.733 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact | 1 | 14 | 62660 | 4475.714 |
| 646295528c-fix-postgres-transpile-day-month-year-to | baseline | 1 | 17 | 77336 | 4549.176 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact-noreport | 1 | 12 | 49087 | 4090.583 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact-noreport | 2 | 10 | 46531 | 4653.100 |
| 646295528c-fix-postgres-transpile-day-month-year-to | baseline | 2 | 11 | 34328 | 3120.727 |
| 646295528c-fix-postgres-transpile-day-month-year-to | impact | 2 | 11 | 47726 | 4338.727 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | baseline | 1 | 23 | 220314 | 9578.870 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact-noreport | 1 | 29 | 286455 | 9877.759 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact | 1 | 34 | 392882 | 11555.353 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact | 2 | 19 | 160242 | 8433.789 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | baseline | 2 | 33 | 334843 | 10146.758 |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | impact-noreport | 2 | 27 | 216471 | 8017.444 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | baseline | 1 | 40 | 591700 | 14792.500 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact | 1 | 20 | 237205 | 11860.250 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact-noreport | 1 | 29 | 363596 | 12537.793 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact | 2 | 26 | 290354 | 11167.462 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | baseline | 2 | 28 | 348146 | 12433.786 |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | impact-noreport | 2 | 37 | 508143 | 13733.595 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | baseline | 1 | 32 | 365870 | 11433.438 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact-noreport | 1 | 29 | 258891 | 8927.276 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact | 1 | 42 | 621190 | 14790.238 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | baseline | 2 | 43 | 478742 | 11133.535 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact | 2 | 29 | 265175 | 9143.966 |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | impact-noreport | 2 | 40 | 575083 | 14377.075 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact-noreport | 1 | 18 | 103474 | 5748.556 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact | 1 | 14 | 97619 | 6972.786 |
| 9114355463-feat-mysql-allow-constraints-without-nam | baseline | 1 | 15 | 114812 | 7654.133 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact | 2 | 19 | 126115 | 6637.632 |
| 9114355463-feat-mysql-allow-constraints-without-nam | impact-noreport | 2 | 11 | 63201 | 5745.545 |
| 9114355463-feat-mysql-allow-constraints-without-nam | baseline | 2 | 12 | 82792 | 6899.333 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact-noreport | 1 | 14 | 46773 | 3340.929 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | baseline | 1 | 16 | 64439 | 4027.438 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact | 1 | 17 | 67418 | 3965.765 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | baseline | 2 | 17 | 59204 | 3482.588 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact-noreport | 2 | 15 | 55710 | 3714 |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | impact | 2 | 14 | 50381 | 3598.643 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact | 1 | 12 | 74069 | 6172.417 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | baseline | 1 | 25 | 256028 | 10241.120 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact-noreport | 1 | 21 | 122926 | 5853.619 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | baseline | 2 | 17 | 108678 | 6392.824 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact-noreport | 2 | 21 | 163796 | 7799.810 |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | impact | 2 | 26 | 237991 | 9153.500 |

| arm | mean requests | mean tokens | mean tokens/request |
|---|---:|---:|---:|
| baseline | 21.042 | 180249.542 | 7590.842 |
| impact | 21.083 | 178279.625 | 7704.032 |
| impact-noreport | 21.125 | 176641.833 | 7467.764 |

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
| 03744a2a83-fix-hive-spark-parse-alter-table-replace | 0 | — | 0 | — | 63356 | — | $0.0637 | — | 56.140 | — |
| 1e6c6c58e1-fix-tsql-stop-json-query-json-value-doub | 0 | — | 0 | — | 104804.500 | — | $0.0826 | — | 56.724 | — |
| 2aae7f7605-feat-postgres-preserve-x-is-not-null-ins | 0 | — | 0 | — | 178283 | — | $0.1267 | — | 98.489 | — |
| 47b94d424a-feat-parser-mysql-accepts-non-csv-table | 0 | — | 0 | — | 105028.500 | — | $0.0787 | — | 60.740 | — |
| 5e6887adc8-fix-tsql-parse-bare-table-hints-gpt-6-1 | 0 | — | 0 | — | 142906.500 | — | $0.1036 | — | 73.137 | — |
| 646295528c-fix-postgres-transpile-day-month-year-to | 0 | — | 0 | — | 55832 | — | $0.0583 | — | 42.750 | — |
| 6581f8c38b-fix-hive-parse-month-day-without-leading | 0 | — | 0 | — | 277578.500 | — | $0.1915 | — | 124.034 | — |
| 66316e335f-fix-hive-parse-single-digit-hour-minute | 0 | — | 0 | — | 469923 | — | $0.2393 | — | 177.122 | — |
| 7f1cf60c88-feat-parser-make-alter-actions-optional | 0 | — | 1 | — | 422306 | — | $0.2338 | — | 146.835 | — |
| 9114355463-feat-mysql-allow-constraints-without-nam | 1 | — | 0 | — | 98802 | — | $0.0852 | — | 63.793 | — |
| 930f1a32f7-fix-postgres-duckdb-preserve-json-extrac | 0 | — | 0 | — | 61821.500 | — | $0.0482 | — | 61.365 | — |
| eeece5a564-fix-preserve-pagination-scope-in-set-ope | 0 | — | 0 | — | 182353 | — | $0.1300 | — | 205.555 | — |

## Paired difference (impact − baseline) with 95% bootstrap CI

Resamples: 10000 with `random.choices`, seed 0. Each observation is one task (median/rate over its reps). Negative cost or tokens means the impact arm was cheaper/smaller.

| metric | n | mean(L−B) | 95% CI low | 95% CI high |
|---|---:|---:|---:|---:|
| resolved rate | 12 | 0.0417 | 0.0000 | 0.1250 |
| hidden checks passed | 12 | 0.0017 | -0.0013 | 0.0060 |
| regressions | 12 | 0.0000 | 0.0000 | 0.0000 |
| tokens (all-in, incl. cache) | 12 | -1969.9167 | -45605.0833 | 30318.9167 |
| requests | 12 | 0.0417 | -2.6250 | 2.6667 |
| tokens/request | 12 | 113.1899 | -412.9981 | 562.2999 |
| cost (USD) | 12 | 0.0048 | -0.0076 | 0.0143 |
| wall time (s) | 12 | 4.8795 | -14.5788 | 21.0967 |
| read chars | 12 | 0.0000 | 0.0000 | 0.0000 |
| read calls | 12 | 0.0000 | 0.0000 | 0.0000 |
| dc-engine calls | 12 | 0.0000 | 0.0000 | 0.0000 |
| contracts created | 12 | 0.0000 | 0.0000 | 0.0000 |
| contract retries | 12 | 0.0000 | 0.0000 | 0.0000 |
| turns | 12 | 0.0000 | -1.5833 | 1.5417 |

## Paired difference (impact-noreport − baseline) with 95% bootstrap CI

Resamples: 10000 with `random.choices`, seed 0. Each observation is one task (median/rate over its reps). Negative cost or tokens means the impact-noreport arm was cheaper/smaller.

| metric | n | mean(L−B) | 95% CI low | 95% CI high |
|---|---:|---:|---:|---:|
| resolved rate | 12 | 0.0417 | 0.0000 | 0.1250 |
| hidden checks passed | 12 | -0.0103 | -0.0379 | 0.0065 |
| regressions | 12 | 0.0000 | 0.0000 | 0.0000 |
| tokens (all-in, incl. cache) | 12 | -3607.7083 | -19661.6250 | 13858.4583 |
| requests | 12 | 0.0833 | -1.4167 | 1.7500 |
| tokens/request | 12 | -123.0785 | -586.1745 | 312.3662 |
| cost (USD) | 12 | 0.0031 | -0.0036 | 0.0105 |
| wall time (s) | 12 | -3.1593 | -20.5769 | 12.4171 |
| read chars | 12 | 0.0000 | 0.0000 | 0.0000 |
| read calls | 12 | 0.0000 | 0.0000 | 0.0000 |
| dc-engine calls | 12 | 0.0000 | 0.0000 | 0.0000 |
| contracts created | 12 | 0.0000 | 0.0000 | 0.0000 |
| contract retries | 12 | 0.0000 | 0.0000 | 0.0000 |
| turns | 12 | -0.2500 | -1.0417 | 0.6250 |
