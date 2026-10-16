[grep 'ArraySlice|def _array_slice|SLICE' in sqlglot]
sqlglot/parsers/snowflake.py:450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/starrocks.py:15:    # TIME_SLICE(dt, INTERVAL n unit [, FLOOR | CEIL])
sqlglot/parsers/starrocks.py:69:        "TIME_SLICE": _build_time_slice,
sqlglot/generators/snowflake.py:564:            "TIME_SLICE",
sqlglot/generators/starrocks.py:387:        return self.func("TIME_SLICE", expression.this, interval, boundary)
sqlglot/generators/duckdb.py:2333:        Transform Snowflake's TIME_SLICE to DuckDB's time_bucket.
sqlglot/generators/duckdb.py:2335:        Snowflake: TIME_SLICE(date_expr, slice_length, 'UNIT' [, 'START'|'END'])
sqlglot/generators/duckdb.py:3590:    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
sqlglot/generators/duckdb.py:3592:        Spark's SLICE uses a length, so normalize negative starts before computing
sqlglot/generators/duckdb.py:3595:        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
sqlglot/generators/duckdb.py:3596:        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
sqlglot/generators/duckdb.py:3637:        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
sqlglot/generators/presto.py:327:        exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/spark2.py:142:            exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/clickhouse.py:291:        exp.ArraySlice: rename_func("arraySlice"),
sqlglot/expressions/array.py:87:class ArraySlice(Expression, Func):
sqlglot/typing/__init__.py:313:            exp.ArraySlice,
sqlglot/parsers/clickhouse.py:294:        "ARRAYSLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/spark2.py:80:        "SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/presto.py:125:        "SLICE": exp.ArraySlice.from_arg_list,

[read sqlglot/generators/duckdb.py lines 3585-3639]
3585	            return self._array_bag_sql(self.ARRAY_EXCEPT_CONDITION, arr1, arr2)
3586	        return self.sql(
3587	            exp.replace_placeholders(self.ARRAY_EXCEPT_SET_TEMPLATE, arr1=arr1, arr2=arr2)
3588	        )
3589	
3590	    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
3591	        """
3592	        Spark's SLICE uses a length, so normalize negative starts before computing
3593	        the inclusive end index. Starts before the array produce an empty slice.
3594	
3595	        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
3596	        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
3597	        expressions that adjust the index at query time:
3598	          - start: CASE WHEN start >= 0 THEN start + 1 ELSE start END
3599	          - end:   CASE WHEN end < 0 THEN end - 1 ELSE end END
3600	        """
3601	        start, end = expression.args.get("start"), expression.args.get("end")
3602	
3603	        if expression.args.get("zero_based"):
3604	            if start is not None:
3605	                start = (
3606	                    exp.case()
3607	                    .when(
3608	                        exp.GTE(this=start.copy(), expression=exp.Literal.number(0)),
3609	                        exp.Add(this=start.copy(), expression=exp.Literal.number(1)),
3610	                    )
3611	                    .else_(start)
3612	                )
3613	            if end is not None and not expression.args.get("is_length"):
3614	                end = (
3615	                    exp.case()
3616	                    .when(
3617	                        exp.LT(this=end.copy(), expression=exp.Literal.number(0)),
3618	                        exp.Sub(this=end.copy(), expression=exp.Literal.number(1)),
3619	                    )
3620	                    .else_(end)
3621	                )
3622	
3623	        if expression.args.get("is_length") and start is not None and end is not None:
3624	            if not start.is_int or start.to_py() < 0:
3625	                size = exp.ArraySize(this=expression.this.copy())
3626	                start = (
3627	                    exp.case()
3628	                    .when(start < -size, size + 1)
3629	                    .when(start < 0, size + start + 1)
3630	                    .else_(start)
3631	                )
3632	
3633	            if start.is_int and end.is_int:
3634	                end = exp.Literal.number(start.to_py() + end.to_py() - 1)
3635	            else:
3636	                end = start + exp.cast(end, "BIGINT") - 1
3637	        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
3638	
3639	    def arrayszip_sql(self, expression: exp.ArraysZip) -> str:

[read sqlglot/parsers/spark2.py lines 70-99]
70	            zone=seq_get(args, 1),
71	        ),
72	        "LTRIM": lambda args: build_trim(args, reverse_args=True),
73	        "INT": build_as_cast("int"),
74	        "MAP_FROM_ARRAYS": exp.Map.from_arg_list,
75	        "RLIKE": exp.RegexpLike.from_arg_list,
76	        "RTRIM": lambda args: build_trim(args, is_left=False, reverse_args=True),
77	        "SHIFTLEFT": binary_from_function(exp.BitwiseLeftShift),
78	        "SHIFTRIGHT": binary_from_function(exp.BitwiseRightShift),
79	        "STRING": build_as_cast("string"),
80	        "SLICE": lambda args: exp.ArraySlice(
81	            this=seq_get(args, 0),
82	            start=seq_get(args, 1),
83	            end=seq_get(args, 2),
84	            is_length=True,
85	        ),
86	        "TIMESTAMP": build_as_cast("timestamp"),
87	        "TO_TIMESTAMP": lambda args, dialect: (
88	            build_as_cast("timestamp")(args)
89	            if len(args) == 1
90	            else build_formatted_time(exp.StrToTime)(args, dialect)
91	        ),
92	        "TO_UNIX_TIMESTAMP": exp.StrToUnix.from_arg_list,
93	        "TO_UTC_TIMESTAMP": lambda args, dialect: exp.FromTimeZone(
94	            this=exp.cast(
95	                seq_get(args, 0) or exp.Var(this=""),
96	                exp.DType.TIMESTAMP,
97	                dialect=dialect,
98	            ),
99	            zone=seq_get(args, 1),

[read sqlglot/expressions/array.py lines 84-95]
84	    pass
85	
86	
87	class ArraySlice(Expression, Func):
88	    """Slice by end index, or by length when is_length is set."""
89	
90	    arg_types = {
91	        "this": True,
92	        "start": True,
93	        "end": False,
94	        "step": False,
95	        "zero_based": False,

[grep 'ARRAY_SLICE|arrayslice|ArraySlice' in sqlglot/parsers/duckdb.py]
No matches found

[grep 'is_length|zero_based' in . (!tests/**)]
sqlglot/parsers/snowflake.py:448:            zero_based=True,
sqlglot/parsers/snowflake.py:454:            zero_based=True,
sqlglot/parsers/spark2.py:84:            is_length=True,
sqlglot/parsers/clickhouse.py:319:            exp.JSONExtract, zero_based_indexing=False, arrow_req_json_type=True
sqlglot/parsers/clickhouse.py:322:            exp.JSONExtractScalar, zero_based_indexing=False, arrow_req_json_type=True
sqlglot/dialects/dialect.py:2360:    zero_based_indexing: bool = True,
sqlglot/dialects/dialect.py:2379:                    exp.JSONPathSubscript(this=index if zero_based_indexing else index - 1)
sqlglot/expressions/array.py:88:    """Slice by end index, or by length when is_length is set."""
sqlglot/expressions/array.py:95:        "zero_based": False,
sqlglot/expressions/array.py:96:        "is_length": False,
sqlglot/expressions/array.py:151:    arg_types = {"this": True, "expression": True, "zero_based": False}
sqlglot/generators/duckdb.py:1621:            if e.args.get("zero_based")
sqlglot/generators/duckdb.py:3603:        if expression.args.get("zero_based"):
sqlglot/generators/duckdb.py:3613:            if end is not None and not expression.args.get("is_length"):
sqlglot/generators/duckdb.py:3623:        if expression.args.get("is_length") and start is not None and end is not None:

[grep 'SLICE\\(' in tests]
tests/fixtures/optimizer/annotate_functions.sql:55:ARRAY_SLICE([1, 1.5], 1, 2);
tests/fixtures/optimizer/annotate_functions.sql:5577:TIME_SLICE(tbl.timestamp_col, 15, 'minute');
tests/fixtures/optimizer/annotate_functions.sql:5581:TIME_SLICE(tbl.date_col, 1, 'day', 'start');
tests/dialects/test_duckdb.py:1473:        self.validate_identity("ARRAY_SLICE(x, 1, 3, 2)")
tests/dialects/test_duckdb.py:1749:        source = "SELECT SLICE(SPLIT('abcdef', ''), 2, 4) AS chars"
tests/dialects/test_duckdb.py:1750:        target = "SELECT ARRAY_SLICE(STR_SPLIT_REGEX('abcdef', ''), 2, 5) AS chars"
tests/dialects/test_duckdb.py:1761:            ("SLICE(ARRAY(1, 2, 3), 1, 2)", "ARRAY_SLICE([1, 2, 3], 1, 2)"),
tests/dialects/test_duckdb.py:1762:            ("SLICE(ARRAY(1, 2, 3), 2, 4)", "ARRAY_SLICE([1, 2, 3], 2, 5)"),
tests/dialects/test_duckdb.py:1763:            ("SLICE(ARRAY(1, 2, 3), 3, 0)", "ARRAY_SLICE([1, 2, 3], 3, 2)"),
tests/dialects/test_duckdb.py:1764:            ("SLICE(ARRAY(1, 2, 3), 2, 2147483647)", "ARRAY_SLICE([1, 2, 3], 2, 2147483648)"),
tests/dialects/test_duckdb.py:1766:                "SLICE(ARRAY(1, 2, 3), -2, 2)",
tests/dialects/test_duckdb.py:1767:                "ARRAY_SLICE([1, 2, 3], CASE WHEN -2 < -ARRAY_LENGTH([1, 2, 3]) THEN ARRAY_LENGTH([1, 2, 3]) + 1 WHEN -2 < 0 THEN ARRAY_LENGTH([1, 2, 3]) + -2 + 1 ELSE -2 END, (CASE WHEN -2 < -ARRAY_LENGTH([1, 2, 3]) THEN ARRAY_LENGTH([1, 2, 3]) + 1 WHEN -2 < 0 THEN ARRAY_LENGTH([1, 2, 3]) + -2 + 1 ELSE -2 END + CAST(2 AS BIGINT)) - 1)",
tests/dialects/test_duckdb.py:1770:                "SLICE(ARRAY(1, 2, 3), -4, 2)",
tests/dialects/test_duckdb.py:1771:                "ARRAY_SLICE([1, 2, 3], CASE WHEN -4 < -ARRAY_LENGTH([1, 2, 3]) THEN ARRAY_LENGTH([1, 2, 3]) + 1 WHEN -4 < 0 THEN ARRAY_LENGTH([1, 2, 3]) + -4 + 1 ELSE -4 END, (CASE WHEN -4 < -ARRAY_LENGTH([1, 2, 3]) THEN ARRAY_LENGTH([1, 2, 3]) + 1 WHEN -4 < 0 THEN ARRAY_LENGTH([1, 2, 3]) + -4 + 1 ELSE -4 END + CAST(2 AS BIGINT)) - 1)",
tests/dialects/test_duckdb.py:1774:                "SLICE(NULL, 2, 1)",
tests/dialects/test_duckdb.py:1775:                "ARRAY_SLICE(NULL, 2, 2)",
tests/dialects/test_duckdb.py:1778:                "SLICE(a, s, n)",
tests/dialects/test_duckdb.py:1779:                "ARRAY_SLICE(a, CASE WHEN s < -ARRAY_LENGTH(a) THEN ARRAY_LENGTH(a) + 1 WHEN s < 0 THEN ARRAY_LENGTH(a) + s + 1 ELSE s END, (CASE WHEN s < -ARRAY_LENGTH(a) THEN ARRAY_LENGTH(a) + 1 WHEN s < 0 THEN ARRAY_LENGTH(a) + s + 1 ELSE s END + CAST(n AS BIGINT)) - 1)",
tests/dialects/test_duckdb.py:1782:                "SLICE(a, 2, n)",
tests/dialects/test_duckdb.py:1783:                "ARRAY_SLICE(a, 2, (2 + CAST(n AS BIGINT)) - 1)",
tests/dialects/test_duckdb.py:1786:                "SLICE(a, s, 2)",
tests/dialects/test_duckdb.py:1787:                "ARRAY_SLICE(a, CASE WHEN s < -ARRAY_LENGTH(a) THEN ARRAY_LENGTH(a) + 1 WHEN s < 0 THEN ARRAY_LENGTH(a) + s + 1 ELSE s END, (CASE WHEN s < -ARRAY_LENGTH(a) THEN ARRAY_LENGTH(a) + 1 WHEN s < 0 THEN ARRAY_LENGTH(a) + s + 1 ELSE s END + CAST(2 AS BIGINT)) - 1)",
tests/dialects/test_starrocks.py:491:            "SELECT TIME_SLICE(dt, 5, 'minute', 'floor')",
tests/dialects/test_starrocks.py:492:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, FLOOR)",
tests/dialects/test_starrocks.py:495:            "SELECT TIME_SLICE(dt, 5, 'minute', 'ceil')",
tests/dialects/test_starrocks.py:496:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, CEIL)",
tests/dialects/test_starrocks.py:498:        self.validate_identity("SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE)")
tests/dialects/test_starrocks.py:500:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, floor)",
tests/dialects/test_starrocks.py:501:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, FLOOR)",
tests/dialects/test_starrocks.py:504:            "CREATE TABLE t (dt DATETIME) PARTITION BY TIME_SLICE(dt, INTERVAL 7 DAY) DISTRIBUTED BY HASH (dt)"
tests/dialects/test_starrocks.py:508:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, CEIL)",
tests/dialects/test_starrocks.py:510:                "snowflake": "SELECT TIME_SLICE(dt, 5, 'MINUTE', 'END')",
tests/dialects/test_starrocks.py:513:                "starrocks": "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, CEIL)",
tests/dialects/test_starrocks.py:514:                "snowflake": "SELECT TIME_SLICE(dt, 5, 'MINUTE', 'END')",
tests/dialects/test_starrocks.py:519:            "SELECT TIME_SLICE(dt, INTERVAL 1 DAY, FLOOR)",
tests/dialects/test_starrocks.py:521:                "snowflake": "SELECT TIME_SLICE(dt, 1, 'DAY', 'START')",
tests/dialects/test_starrocks.py:524:                "starrocks": "SELECT TIME_SLICE(dt, INTERVAL 1 DAY, FLOOR)",
tests/dialects/test_starrocks.py:525:                "snowflake": "SELECT TIME_SLICE(dt, 1, 'DAY', 'START')",
tests/dialects/test_dialect.py:1528:            "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1531:                "bigquery": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1532:                "snowflake": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1533:                "duckdb": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1534:                "spark2": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1535:                "spark": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1536:                "databricks": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1537:                "presto": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1538:                "trino": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1542:                "bigquery": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1543:                "snowflake": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1544:                "duckdb": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1545:                "spark2": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1546:                "spark": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1547:                "databricks": "SL
… (2657 more characters)

[read tests/dialects/test_dialect.py lines 1520-1554]
1520	                "clickhouse": "arrayReverse(x)",
1521	                "bigquery": "ARRAY_REVERSE(x)",
1522	                "snowflake": "ARRAY_REVERSE(x)",
1523	                "duckdb": "ARRAY_REVERSE(x)",
1524	            },
1525	        )
1526	
1527	        self.validate_all(
1528	            "ARRAY_SLICE(x, 1, 3)",
1529	            read={
1530	                "clickhouse": "arraySlice(x, 1, 3)",
1531	                "bigquery": "ARRAY_SLICE(x, 1, 3)",
1532	                "snowflake": "ARRAY_SLICE(x, 1, 3)",
1533	                "duckdb": "ARRAY_SLICE(x, 1, 3)",
1534	                "spark2": "SLICE(x, 1, 3)",
1535	                "spark": "SLICE(x, 1, 3)",
1536	                "databricks": "SLICE(x, 1, 3)",
1537	                "presto": "SLICE(x, 1, 3)",
1538	                "trino": "SLICE(x, 1, 3)",
1539	            },
1540	            write={
1541	                "clickhouse": "arraySlice(x, 1, 3)",
1542	                "bigquery": "ARRAY_SLICE(x, 1, 3)",
1543	                "snowflake": "ARRAY_SLICE(x, 1, 3)",
1544	                "duckdb": "ARRAY_SLICE(x, 1, 3)",
1545	                "spark2": "SLICE(x, 1, 3)",
1546	                "spark": "SLICE(x, 1, 3)",
1547	                "databricks": "SLICE(x, 1, 3)",
1548	                "presto": "SLICE(x, 1, 3)",
1549	                "trino": "SLICE(x, 1, 3)",
1550	            },
1551	        )
1552	
1553	        self.validate_all(
1554	            "SORT_ARRAY(x)",

[grep 'FUNCTIONS = \\{|"LIST_|ARRAY_|ArraySize|ARRAY_LENGTH' in sqlglot/parsers/duckdb.py]
78:    NO_PAREN_FUNCTIONS = {
118:    FUNCTIONS = {
121:        "ARRAY_PREPEND": _build_array_prepend,
122:        "ARRAY_REVERSE_SORT": _build_sort_array_desc,
123:        "ARRAY_INTERSECT": lambda args: exp.ArrayIntersect(expressions=args),
124:        "ARRAY_SORT": exp.SortArray.from_arg_list,
154:        "LIST_DISTINCT": exp.ArrayDistinct.from_arg_list,
155:        "LIST_APPEND": exp.ArrayAppend.from_arg_list,
156:        "LIST_CONCAT": parser.build_array_concat,
157:        "LIST_CONTAINS": exp.ArrayContains.from_arg_list,
158:        "LIST_COSINE_DISTANCE": exp.CosineDistance.from_arg_list,
159:        "LIST_DISTANCE": exp.EuclideanDistance.from_arg_list,
160:        "LIST_FILTER": exp.ArrayFilter.from_arg_list,
161:        "LIST_HAS": exp.ArrayContains.from_arg_list,
162:        "LIST_HAS_ANY": exp.ArrayOverlaps.from_arg_list,
163:        "LIST_MAX": exp.ArrayMax.from_arg_list,
164:        "LIST_MIN": exp.ArrayMin.from_arg_list,
165:        "LIST_PREPEND": _build_array_prepend,
166:        "LIST_REVERSE_SORT": _build_sort_array_desc,
167:        "LIST_SORT": exp.SortArray.from_arg_list,
168:        "LIST_TRANSFORM": exp.Transform.from_arg_list,
169:        "LIST_VALUE": lambda args: exp.Array(

[grep 'ArraySize|ArraySlice' in sqlglot/generators]
sqlglot/generators/duckdb.py:564:            this=exp.NEQ(this=exp.ArraySize(this=this), expression=exp.func("LIST_COUNT", this)),
sqlglot/generators/duckdb.py:592:            this=exp.ArraySize(this=arr1.copy()),
sqlglot/generators/duckdb.py:596:            this=exp.ArraySize(this=arr2.copy()),
sqlglot/generators/duckdb.py:3564:                        this=exp.ArraySize(this=arr), expression=exp.func("LIST_COUNT", arr)
sqlglot/generators/duckdb.py:3590:    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
sqlglot/generators/duckdb.py:3625:                size = exp.ArraySize(this=expression.this.copy())
sqlglot/generators/presto.py:327:        exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/spark2.py:142:            exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/clickhouse.py:291:        exp.ArraySlice: rename_func("arraySlice"),

$ python -c "
import sqlglot
for q in ['SELECT x[1:2]','SELECT LIST_SLICE(x,1,2)','SELECT ARRAY_SLICE(x,1,2)','SELECT x[2:]']:
  e=sqlglot.parse_one(q,read='duckdb'); print(repr(e.selects[0])[:200]); print(e.sql('spark'))
"; sed -n 115,125p sqlglot/parsers/duckdb.py; grep -n "^from\|^import" sqlglot/generators/spark2.py sqlglot/generators/presto.py | head -40
Unable to set __version__, run `pip install -e .` or `python setup.py develop` first.
Bracket(
  this=Column(
    this=Identifier(this=x, quoted=False, _type=DataType(this=DType.UNKNOWN)),
    _type=DataType(this=DType.UNKNOWN)),
  expressions=[
    Slice(
      this=Literal(this=1, is
SELECT x[1:2]
Anonymous(
  this=LIST_SLICE,
  expressions=[
    Column(
      this=Identifier(this=x, quoted=False)),
    Literal(this=1, is_string=False),
    Literal(this=2, is_string=False)])
SELECT LIST_SLICE(x, 1, 2)
ArraySlice(
  this=Column(
    this=Identifier(this=x, quoted=False)),
  start=Literal(this=1, is_string=False),
  end=Literal(this=2, is_string=False))
SELECT SLICE(x, 1, 2)
Bracket(
  this=Column(
    this=Identifier(this=x, quoted=False, _type=DataType(this=DType.UNKNOWN)),
    _type=DataType(this=DType.UNKNOWN)),
  expressions=[
    Slice(
      this=Literal(this=2, is
SELECT x[2:]
        "ALL TABLES": _show_parser("ALL TABLES"),
    }

    FUNCTIONS = {
        **{k: v for k, v in parser.Parser.FUNCTIONS.items() if k not in ("DATE_SUB", "GLOB")},
        "ANY_VALUE": lambda args: exp.IgnoreNulls(this=exp.AnyValue.from_arg_list(args)),
        "ARRAY_PREPEND": _build_array_prepend,
        "ARRAY_REVERSE_SORT": _build_sort_array_desc,
        "ARRAY_INTERSECT": lambda args: exp.ArrayIntersect(expressions=args),
        "ARRAY_SORT": exp.SortArray.from_arg_list,
        "BIT_AND": exp.BitwiseAndAgg.from_arg_list,
sqlglot/generators/spark2.py:1:from __future__ import annotations
sqlglot/generators/spark2.py:3:import typing as t
sqlglot/generators/spark2.py:5:from sqlglot import exp, transforms
sqlglot/generators/spark2.py:6:from sqlglot.dialects.dialect import (
sqlglot/generators/spark2.py:13:from sqlglot.generators.hive import HIVE_DATE_FORMAT, HiveGenerator, HIVE_TS_OR_DS_EXPRESSIONS
sqlglot/generators/spark2.py:14:from sqlglot.transforms import (
sqlglot/generators/presto.py:1:from __future__ import annotations
sqlglot/generators/presto.py:3:import typing as t
sqlglot/generators/presto.py:5:from sqlglot import exp, generator, transforms
sqlglot/generators/presto.py:6:from sqlglot.dialects.dialect import (
sqlglot/generators/presto.py:29:from sqlglot.dialects.hive import Hive
sqlglot/generators/presto.py:30:from sqlglot.generator import unsupported_args
sqlglot/generators/presto.py:31:from sqlglot.optimizer.scope import find_all_in_scope
sqlglot/generators/presto.py:32:from sqlglot.transforms import unqualify_columns

$ grep -n "^def rename_func" dialects/dialect.py; sed -n 136,146p generators/spark2.py; sed -n 6,28p generators/presto.py; grep -n "unsupported_args" generators/spark2.py | head -3; grep -n "^from\|^import" dialects/dialect.py | head -30
1290:def rename_func(name: str) -> t.Callable[[Generator, exp.Expr], str]:
            **HiveGenerator.TRANSFORMS,
            exp.ApproxDistinct: rename_func("APPROX_COUNT_DISTINCT"),
            exp.ArraySum: lambda self, e: (
                f"AGGREGATE({self.sql(e, 'this')}, 0, (acc, x) -> acc + x, acc -> acc)"
            ),
            exp.ArrayToString: rename_func("ARRAY_JOIN"),
            exp.ArraySlice: rename_func("SLICE"),
            exp.AtTimeZone: lambda self, e: self.func(
                "FROM_UTC_TIMESTAMP", e.this, e.args.get("zone")
            ),
            exp.BitwiseLeftShift: rename_func("SHIFTLEFT"),
from sqlglot.dialects.dialect import (
    bool_xor_sql,
    bracket_to_element_at_sql,
    datestrtodate_sql,
    encode_decode_sql,
    if_sql,
    left_to_substring_sql,
    no_ilike_sql,
    no_pivot_sql,
    no_timestamp_sql,
    regexp_extract_sql,
    rename_func,
    right_to_substring_sql,
    strposition_sql,
    struct_extract_sql,
    timestamptrunc_sql,
    timestrtotime_sql,
    ts_or_ds_add_cast,
    unit_to_str,
    week_unit_to_dow,
    sequence_sql,
    explode_to_unnest_sql,
)
1:from __future__ import annotations
3:import importlib
4:import logging
5:import string
6:import typing as t
7:import sys
8:from collections.abc import Iterable, MutableSequence
9:from enum import Enum, auto
10:from functools import reduce
11:from builtins import type as Type
13:from sqlglot import exp
14:from sqlglot.dialects import DIALECT_MODULE_NAMES
15:from sqlglot.errors import ParseError, TokenError
16:from sqlglot.generator import Generator, unsupported_args
17:from sqlglot.expressions import apply_index_offset
18:from sqlglot.helper import (
27:from sqlglot.jsonpath import ALL_JSON_PATH_PARTS, JSONPathTokenizer, parse as parse_json_path
28:from sqlglot.optimizer.scope import find_all_in_scope
29:from sqlglot.parser import Parser
30:from sqlglot.parsers.base import BaseParser
31:from sqlglot.time import TIMEZONES, format_time, subsecond_precision
32:from sqlglot.tokens import Token, Tokenizer, TokenType
33:from sqlglot.trie import new_trie
34:from sqlglot.typing import EXPRESSION_METADATA
36:from importlib.metadata import entry_points

[grep 'ArraySlice|ARRAY_SLICE|"SLICE"' in sqlglot]
sqlglot/parsers/snowflake.py:450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/presto.py:125:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/spark2.py:80:        "SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/clickhouse.py:294:        "ARRAYSLICE": exp.ArraySlice.from_arg_list,
sqlglot/expressions/array.py:87:class ArraySlice(Expression, Func):
sqlglot/typing/__init__.py:313:            exp.ArraySlice,
sqlglot/generators/duckdb.py:3590:    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
sqlglot/generators/duckdb.py:3595:        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
sqlglot/generators/duckdb.py:3596:        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
sqlglot/generators/duckdb.py:3637:        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
sqlglot/generators/presto.py:327:        exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/spark2.py:142:            exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/clickhouse.py:291:        exp.ArraySlice: rename_func("arraySlice"),

[read sqlglot/expressions/array.py lines 85-96]
85	
86	
87	class ArraySlice(Expression, Func):
88	    """Slice by end index, or by length when is_length is set."""
89	
90	    arg_types = {
91	        "this": True,
92	        "start": True,
93	        "end": False,
94	        "step": False,
95	        "zero_based": False,
96	        "is_length": False,

[grep 'ARRAY_SLICE|SLICE\\(' in tests]
tests/fixtures/optimizer/annotate_functions.sql:55:ARRAY_SLICE([1, 1.5], 1, 2);
tests/fixtures/optimizer/annotate_functions.sql:5577:TIME_SLICE(tbl.timestamp_col, 15, 'minute');
tests/fixtures/optimizer/annotate_functions.sql:5581:TIME_SLICE(tbl.date_col, 1, 'day', 'start');
tests/dialects/test_snowflake.py:3092:            "SELECT TIME_SLICE(CAST('2024-05-09 08:50:57.891' AS TIMESTAMP), 15, 'MINUTE')"
tests/dialects/test_snowflake.py:3094:        self.validate_identity("SELECT TIME_SLICE(CAST('2024-05-09' AS DATE), 1, 'DAY')")
tests/dialects/test_snowflake.py:3096:            "SELECT TIME_SLICE(CAST('2024-05-09 08:50:57.891' AS TIMESTAMP), 1, 'HOUR', 'start')"
tests/dialects/test_snowflake.py:3101:            "SELECT TIME_SLICE(TIMESTAMP '2024-03-15 14:37:42', 1, 'HOUR')",
tests/dialects/test_snowflake.py:3103:                "snowflake": "SELECT TIME_SLICE(CAST('2024-03-15 14:37:42' AS TIMESTAMP), 1, 'HOUR')",
tests/dialects/test_snowflake.py:3108:            "SELECT TIME_SLICE(TIMESTAMP '2024-03-15 14:37:42', 1, 'HOUR', 'END')",
tests/dialects/test_snowflake.py:3110:                "snowflake": "SELECT TIME_SLICE(CAST('2024-03-15 14:37:42' AS TIMESTAMP), 1, 'HOUR', 'END')",
tests/dialects/test_snowflake.py:3115:            "SELECT TIME_SLICE(DATE '2024-03-15', 1, 'DAY')",
tests/dialects/test_snowflake.py:3117:                "snowflake": "SELECT TIME_SLICE(CAST('2024-03-15' AS DATE), 1, 'DAY')",
tests/dialects/test_snowflake.py:3122:            "SELECT TIME_SLICE(DATE '2024-03-15', 1, 'DAY', 'END')",
tests/dialects/test_snowflake.py:3124:                "snowflake": "SELECT TIME_SLICE(CAST('2024-03-15' AS DATE), 1, 'DAY', 'END')",
tests/dialects/test_snowflake.py:3129:            "SELECT TIME_SLICE(TIMESTAMP '2024-03-15 14:37:42', 15, 'MINUTE')",
tests/dialects/test_snowflake.py:3131:                "snowflake": "SELECT TIME_SLICE(CAST('2024-03-15 14:37:42' AS TIMESTAMP), 15, 'MINUTE')",
tests/dialects/test_snowflake.py:3136:            "SELECT TIME_SLICE(TIMESTAMP '2024-03-15 14:37:42', 1, 'QUARTER')",
tests/dialects/test_snowflake.py:3138:                "snowflake": "SELECT TIME_SLICE(CAST('2024-03-15 14:37:42' AS TIMESTAMP), 1, 'QUARTER')",
tests/dialects/test_snowflake.py:3143:            "SELECT TIME_SLICE(DATE '2024-03-15', 1, 'WEEK', 'END')",
tests/dialects/test_snowflake.py:3145:                "snowflake": "SELECT TIME_SLICE(CAST('2024-03-15' AS DATE), 1, 'WEEK', 'END')",
tests/dialects/test_snowflake.py:7012:            "ARRAY_SLICE(arr, s, e)",
tests/dialects/test_snowflake.py:7014:                "snowflake": "ARRAY_SLICE(arr, s, e)",
tests/dialects/test_snowflake.py:7015:                "duckdb": "ARRAY_SLICE(arr, CASE WHEN s >= 0 THEN s + 1 ELSE s END, CASE WHEN e < 0 THEN e - 1 ELSE e END)",
tests/dialects/test_dialect.py:1528:            "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1531:                "bigquery": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1532:                "snowflake": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1533:                "duckdb": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1534:                "spark2": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1535:                "spark": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1536:                "databricks": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1537:                "presto": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1538:                "trino": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1542:                "bigquery": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1543:                "snowflake": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1544:                "duckdb": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1545:                "spark2": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1546:                "spark": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1547:                "databricks": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1548:                "presto": "SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1549:                "trino": "SLICE(x, 1, 3)",
tests/dialects/test_starrocks.py:491:            "SELECT TIME_SLICE(dt, 5, 'minute', 'floor')",
tests/dialects/test_starrocks.py:492:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, FLOOR)",
tests/dialects/test_starrocks.py:495:            "SELECT TIME_SLICE(dt, 5, 'minute', 'ceil')",
tests/dialects/test_starrocks.py:496:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, CEIL)",
tests/dialects/test_starrocks.py:498:        self.validate_identity("SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE)")
tests/dialects/test_starrocks.py:500:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, floor)",
tests/dialects/test_starrocks.py:501:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, FLOOR)",
tests/dialects/test_starrocks.py:504:            "CREATE TABLE t (dt DATETIME) PARTITION BY TIME_SLICE(dt, INTERVAL 7 DAY) DISTRIBUTED BY HASH (dt)"
tests/dialects/test_starrocks.py:508:            "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, CEIL)",
tests/dialects/test_starrocks.py:510:                "snowflake": "SELECT TIME_SLICE(dt, 5, 'MINUTE', 'END')",
tests/dialects/test_starrocks.py:513:                "starrocks": "SELECT TIME_SLICE(dt, INTERVAL 5 MINUTE, CEIL)",
tests/dialects/test_starrocks.py:514:                "snowflake": "SELECT TIME_SLICE(dt, 5, 'MINUTE', 'END')",
tests/dialects/test_starrocks.py:519:            "SELECT TIME_SLICE(dt, INTERVAL 1 DAY, FLOOR)",
tests/dialects/test_starrocks.py:521:                "snowflake": "SELECT TIME_SLICE(dt, 1, 'DAY', 'START')",
tests/dialects/test_starrocks.py:524:                "starrocks": "SELECT TIME_SLICE(dt, INTERVAL 1 DAY, FLOOR)",
tests/dialects/test_starrocks.py:525:                "snowflake": "SELECT TIME_SLICE(dt, 1, 'DAY', 'START')",
tests/dialects/test_duckdb.py:1473:        self.validate_identity("ARRAY_SLICE(x, 1, 3, 2)")
tests/dialects/test_duckdb
… (2657 more characters)

[read sqlglot/parsers/spark2.py lines 76-87]
76	        "RTRIM": lambda args: build_trim(args, is_left=False, reverse_args=True),
77	        "SHIFTLEFT": binary_from_function(exp.BitwiseLeftShift),
78	        "SHIFTRIGHT": binary_from_function(exp.BitwiseRightShift),
79	        "STRING": build_as_cast("string"),
80	        "SLICE": lambda args: exp.ArraySlice(
81	            this=seq_get(args, 0),
82	            start=seq_get(args, 1),
83	            end=seq_get(args, 2),
84	            is_length=True,
85	        ),
86	        "TIMESTAMP": build_as_cast("timestamp"),
87	        "TO_TIMESTAMP": lambda args, dialect: (

[read tests/dialects/test_dialect.py lines 1522-1551]
1522	                "snowflake": "ARRAY_REVERSE(x)",
1523	                "duckdb": "ARRAY_REVERSE(x)",
1524	            },
1525	        )
1526	
1527	        self.validate_all(
1528	            "ARRAY_SLICE(x, 1, 3)",
1529	            read={
1530	                "clickhouse": "arraySlice(x, 1, 3)",
1531	                "bigquery": "ARRAY_SLICE(x, 1, 3)",
1532	                "snowflake": "ARRAY_SLICE(x, 1, 3)",
1533	                "duckdb": "ARRAY_SLICE(x, 1, 3)",
1534	                "spark2": "SLICE(x, 1, 3)",
1535	                "spark": "SLICE(x, 1, 3)",
1536	                "databricks": "SLICE(x, 1, 3)",
1537	                "presto": "SLICE(x, 1, 3)",
1538	                "trino": "SLICE(x, 1, 3)",
1539	            },
1540	            write={
1541	                "clickhouse": "arraySlice(x, 1, 3)",
1542	                "bigquery": "ARRAY_SLICE(x, 1, 3)",
1543	                "snowflake": "ARRAY_SLICE(x, 1, 3)",
1544	                "duckdb": "ARRAY_SLICE(x, 1, 3)",
1545	                "spark2": "SLICE(x, 1, 3)",
1546	                "spark": "SLICE(x, 1, 3)",
1547	                "databricks": "SLICE(x, 1, 3)",
1548	                "presto": "SLICE(x, 1, 3)",
1549	                "trino": "SLICE(x, 1, 3)",
1550	            },
1551	        )

[grep 'ArraySlice|ARRAY_SLICE|SLICE' in sqlglot/parsers/duckdb.py]
No matches found

$ cd  && grep -n "^from\|^import\|    rename_func,\|^def " sqlglot/generators/presto.py | head -50; grep -n "^from sqlglot.dialects.dialect\|^from sqlglot.generators" -A12 sqlglot/generators/spark2.py | head -40; grep -n "ArraySize" sqlglot/generators/*.py | head
1:from __future__ import annotations
3:import typing as t
5:from sqlglot import exp, generator, transforms
6:from sqlglot.dialects.dialect import (
17:    rename_func,
29:from sqlglot.dialects.hive import Hive
30:from sqlglot.generator import unsupported_args
31:from sqlglot.optimizer.scope import find_all_in_scope
32:from sqlglot.transforms import unqualify_columns
37:def _sha2_digest_sql(self: PrestoGenerator, expression: exp.SHA2Digest) -> str:
50:def _initcap_sql(self: PrestoGenerator, expression: exp.Initcap) -> str:
61:def _no_sort_array(self: PrestoGenerator, expression: exp.SortArray) -> str:
69:def _schema_sql(self: PrestoGenerator, expression: exp.Schema) -> str:
92:def _quantile_sql(self: PrestoGenerator, expression: exp.Quantile) -> str:
97:def _str_to_time_sql(
103:def _ts_or_ds_to_date_sql(self: PrestoGenerator, expression: exp.TsOrDsToDate) -> str:
111:def _ts_or_ds_add_sql(self: PrestoGenerator, expression: exp.TsOrDsAdd) -> str:
117:def _ts_or_ds_diff_sql(self: PrestoGenerator, expression: exp.TsOrDsDiff) -> str:
124:def _first_last_sql(self: PrestoGenerator, expression: exp.Func) -> str:
138:def _unix_to_time_sql(self: PrestoGenerator, expression: exp.UnixToTime) -> str:
147:def _to_int(self: PrestoGenerator, expression: exp.Expr) -> exp.Expr:
157:def _date_delta_sql(
172:def _date_diff_sql(
206:def _explode_to_unnest_sql(self: PrestoGenerator, expression: exp.Lateral) -> str:
228:def amend_exploded_column_table(expression: exp.Expr) -> exp.Expr:
6:from sqlglot.dialects.dialect import (
7-    bracket_to_element_at_sql,
8-    is_parse_json,
9-    rename_func,
10-    timestamptrunc_sql,
11-    weekstart_unit_to_str,
12-)
13:from sqlglot.generators.hive import HIVE_DATE_FORMAT, HiveGenerator, HIVE_TS_OR_DS_EXPRESSIONS
14-from sqlglot.transforms import (
15-    preprocess,
16-    remove_unique_constraints,
17-    ctas_with_tmp_tables_to_create_tmp_view,
18-    move_schema_columns_to_partitioned_by,
19-)
20-
21-
22-def _json_format_sql(self: Spark2Generator, expression: exp.JSONFormat) -> str:
23-    this = expression.this
24-
25-    if is_parse_json(this):
sqlglot/generators/duckdb.py:564:            this=exp.NEQ(this=exp.ArraySize(this=this), expression=exp.func("LIST_COUNT", this)),
sqlglot/generators/duckdb.py:592:            this=exp.ArraySize(this=arr1.copy()),
sqlglot/generators/duckdb.py:596:            this=exp.ArraySize(this=arr2.copy()),
sqlglot/generators/duckdb.py:3564:                        this=exp.ArraySize(this=arr), expression=exp.func("LIST_COUNT", arr)
sqlglot/generators/duckdb.py:3625:                size = exp.ArraySize(this=expression.this.copy())

[grep 'ArraySlice|ARRAY_SLICE' in sqlglot/parsers/duckdb.py]
No matches found

[grep 'ARRAY_SLICE|ArraySlice|SLICE\\(' in sqlglot/parsers/duckdb.py]
No matches found

[grep 'ArraySlice|ARRAY_SLICE' in tests/dialects (test_{presto,spark,databricks,trino,hive}.py)]
No matches found

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
