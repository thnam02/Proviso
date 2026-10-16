[grep 'ArraySlice|SLICE' in sqlglot]
sqlglot/parsers/snowflake.py:450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/presto.py:125:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/clickhouse.py:294:        "ARRAYSLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/spark2.py:80:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/generators/snowflake.py:561:            "TIME_SLICE",
sqlglot/generators/presto.py:325:        exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/spark2.py:142:            exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/clickhouse.py:291:        exp.ArraySlice: rename_func("arraySlice"),
sqlglot/generators/duckdb.py:2319:        Transform Snowflake's TIME_SLICE to DuckDB's time_bucket.
sqlglot/generators/duckdb.py:2321:        Snowflake: TIME_SLICE(date_expr, slice_length, 'UNIT' [, 'START'|'END'])
sqlglot/generators/duckdb.py:3572:    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
sqlglot/generators/duckdb.py:3574:        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
sqlglot/generators/duckdb.py:3575:        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
sqlglot/generators/duckdb.py:3602:        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
sqlglot/expressions/array.py:86:class ArraySlice(Expression, Func):
sqlglot/typing/__init__.py:266:            exp.ArraySlice,

[read sqlglot/generators/duckdb.py lines 3565-3609]
3565	        arr1, arr2 = expression.this, expression.expression
3566	        if expression.args.get("is_multiset"):
3567	            return self._array_bag_sql(self.ARRAY_EXCEPT_CONDITION, arr1, arr2)
3568	        return self.sql(
3569	            exp.replace_placeholders(self.ARRAY_EXCEPT_SET_TEMPLATE, arr1=arr1, arr2=arr2)
3570	        )
3571	
3572	    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
3573	        """
3574	        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
3575	        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
3576	        expressions that adjust the index at query time:
3577	          - start: CASE WHEN start >= 0 THEN start + 1 ELSE start END
3578	          - end:   CASE WHEN end < 0 THEN end - 1 ELSE end END
3579	        """
3580	        start, end = expression.args.get("start"), expression.args.get("end")
3581	
3582	        if expression.args.get("zero_based"):
3583	            if start is not None:
3584	                start = (
3585	                    exp.case()
3586	                    .when(
3587	                        exp.GTE(this=start.copy(), expression=exp.Literal.number(0)),
3588	                        exp.Add(this=start.copy(), expression=exp.Literal.number(1)),
3589	                    )
3590	                    .else_(start)
3591	                )
3592	            if end is not None:
3593	                end = (
3594	                    exp.case()
3595	                    .when(
3596	                        exp.LT(this=end.copy(), expression=exp.Literal.number(0)),
3597	                        exp.Sub(this=end.copy(), expression=exp.Literal.number(1)),
3598	                    )
3599	                    .else_(end)
3600	                )
3601	
3602	        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
3603	
3604	    def arrayszip_sql(self, expression: exp.ArraysZip) -> str:
3605	        args = expression.expressions
3606	
3607	        if not args:
3608	            # Return [{}] - using MAP([], []) since DuckDB can't represent empty structs
3609	            return self.sql(exp.array(exp.Map(keys=exp.array(), values=exp.array())))

[read sqlglot/expressions/array.py lines 84-95]
84	
85	
86	class ArraySlice(Expression, Func):
87	    arg_types = {"this": True, "start": True, "end": False, "step": False, "zero_based": False}
88	
89	
90	class ArraySort(Expression, Func):
91	    arg_types = {"this": True, "expression": False}
92	
93	
94	class Shuffle(Expression, Func):
95	    pass

[grep 'ArraySlice|ARRAY_SLICE' in tests]
tests/fixtures/optimizer/annotate_functions.sql:55:ARRAY_SLICE([1, 1.5], 1, 2);
tests/dialects/test_snowflake.py:7012:            "ARRAY_SLICE(arr, s, e)",
tests/dialects/test_snowflake.py:7014:                "snowflake": "ARRAY_SLICE(arr, s, e)",
tests/dialects/test_snowflake.py:7015:                "duckdb": "ARRAY_SLICE(arr, CASE WHEN s >= 0 THEN s + 1 ELSE s END, CASE WHEN e < 0 THEN e - 1 ELSE e END)",
tests/dialects/test_dialect.py:1528:            "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1531:                "bigquery": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1532:                "snowflake": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1533:                "duckdb": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1542:                "bigquery": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1543:                "snowflake": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_dialect.py:1544:                "duckdb": "ARRAY_SLICE(x, 1, 3)",
tests/dialects/test_duckdb.py:1473:        self.validate_identity("ARRAY_SLICE(x, 1, 3, 2)")

[grep 'def function_fallback_sql' in sqlglot/generator.py]
4756:    def function_fallback_sql(self, expression: exp.Func) -> str:
4757-        args = []
4758-
4759-        for key in expression.arg_types:
4760-            arg_value = expression.args.get(key)
4761-
4762-            if isinstance(arg_value, list):
4763-                for value in arg_value:
4764-                    args.append(value)
4765-            elif arg_value is not None:
4766-                args.append(arg_value)
4767-
4768-        return self.func(self.function_name(expression), *args)
4769-
4770-    def function_name(self, expression: exp.Func) -> str:
4771-        name_key = self.dialect.ORIGINAL_NAME_META_KEY
4772-        return (expression.meta_get(name_key) if name_key else None) or expression.sql_name()
4773-
4774-    def func(
4775-        self,
4776-        name: str,
4777-        *args: t.Any,
4778-        prefix: str = "(",

[read sqlglot/parsers/spark2.py lines 1-40]
1	from __future__ import annotations
2	
3	import typing as t
4	
5	from sqlglot import exp
6	from sqlglot.dialects.dialect import (
7	    binary_from_function,
8	    build_formatted_time,
9	    pivot_column_names,
10	)
11	from sqlglot.helper import ensure_list, seq_get
12	from sqlglot.parsers.hive import HiveParser
13	from sqlglot.parser import build_trim
14	from sqlglot.tokens import TokenType
15	
16	
17	def build_as_cast(to_type: str) -> t.Callable[[list], exp.Expr]:
18	    return lambda args: exp.Cast(this=seq_get(args, 0), to=exp.DataType.from_str(to_type))
19	
20	
21	def build_int_div(args: list) -> exp.IntDiv | exp.Paren:
22	    this = seq_get(args, 0)
23	    expression = seq_get(args, 1)
24	
25	    if this is None or expression is None:
26	        return exp.IntDiv(this=this, expression=expression)
27	
28	    this = exp.Paren(this=this) if isinstance(this, exp.Binary) else this
29	    expression = exp.Paren(this=expression) if isinstance(expression, exp.Binary) else expression
30	
31	    return exp.Paren(this=exp.IntDiv(this=this, expression=expression))
32	
33	
34	class Spark2Parser(HiveParser):
35	    NORMALIZE_DECIMAL_LITERALS = False
36	    DECIMAL_LITERALS_ALLOW_NEGATIVE_SCALE = True
37	    TRIM_PATTERN_FIRST = True
38	    CHANGE_COLUMN_ALTER_SYNTAX = True
39	    PIVOT_COLUMN_NAMING = "agg_name_if_multiple"
40

[grep 'ArraySlice|ARRAY_SLICE|"SLICE"' in sqlglot]
sqlglot/parsers/snowflake.py:450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/presto.py:125:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/spark2.py:80:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/clickhouse.py:294:        "ARRAYSLICE": exp.ArraySlice.from_arg_list,
sqlglot/generators/duckdb.py:3572:    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
sqlglot/generators/duckdb.py:3574:        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
sqlglot/generators/duckdb.py:3575:        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
sqlglot/generators/duckdb.py:3602:        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
sqlglot/generators/presto.py:325:        exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/spark2.py:142:            exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/clickhouse.py:291:        exp.ArraySlice: rename_func("arraySlice"),
sqlglot/expressions/array.py:86:class ArraySlice(Expression, Func):
sqlglot/typing/__init__.py:266:            exp.ArraySlice,

[read sqlglot/expressions/array.py lines 80-94]
80	
81	
82	class ArrayReverse(Expression, Func):
83	    pass
84	
85	
86	class ArraySlice(Expression, Func):
87	    arg_types = {"this": True, "start": True, "end": False, "step": False, "zero_based": False}
88	
89	
90	class ArraySort(Expression, Func):
91	    arg_types = {"this": True, "expression": False}
92	
93	
94	class Shuffle(Expression, Func):

[grep 'ArraySlice|ARRAY_SLICE' in sqlglot/parsers/snowflake.py]
450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
451-            this=seq_get(args, 0),
452-            start=seq_get(args, 1),
453-            end=seq_get(args, 2),
454-            zero_based=True,
455-        ),
456-        "ARRAY_SORT": _build_array_sort,

$ grep -n "def rename_func" -A12 sqlglot/dialects/dialect.py; sed -n 70,90p sqlglot/parsers/spark2.py; grep -n "SLICE" -r sqlglot/parsers/spark.py sqlglot/parsers/databricks.py tests/dialects/test_spark.py tests/dialects/test_duckdb.py | head -20
1264:def rename_func(name: str) -> t.Callable[[Generator, exp.Expr], str]:
1265-    return lambda self, expression: self.func(name, *flatten(expression.args.values()))
1266-
1267-
1268-def bracket_to_element_at_sql(self: Generator, expression: exp.Bracket) -> str:
1269-    index = seq_get(
1270-        apply_index_offset(
1271-            expression.this,
1272-            expression.expressions,
1273-            1 - expression.args.get("offset", 0),
1274-            dialect=self.dialect,
1275-        ),
1276-        0,
            zone=seq_get(args, 1),
        ),
        "LTRIM": lambda args: build_trim(args, reverse_args=True),
        "INT": build_as_cast("int"),
        "MAP_FROM_ARRAYS": exp.Map.from_arg_list,
        "RLIKE": exp.RegexpLike.from_arg_list,
        "RTRIM": lambda args: build_trim(args, is_left=False, reverse_args=True),
        "SHIFTLEFT": binary_from_function(exp.BitwiseLeftShift),
        "SHIFTRIGHT": binary_from_function(exp.BitwiseRightShift),
        "STRING": build_as_cast("string"),
        "SLICE": exp.ArraySlice.from_arg_list,
        "TIMESTAMP": build_as_cast("timestamp"),
        "TO_TIMESTAMP": lambda args, dialect: (
            build_as_cast("timestamp")(args)
            if len(args) == 1
            else build_formatted_time(exp.StrToTime)(args, dialect)
        ),
        "TO_UNIX_TIMESTAMP": exp.StrToUnix.from_arg_list,
        "TO_UTC_TIMESTAMP": lambda args, dialect: exp.FromTimeZone(
            this=exp.cast(
                seq_get(args, 0) or exp.Var(this=""),
tests/dialects/test_duckdb.py:1473:        self.validate_identity("ARRAY_SLICE(x, 1, 3, 2)")

[grep 'ArraySlice|"SLICE"' in sqlglot]
sqlglot/expressions/array.py:86:class ArraySlice(Expression, Func):
sqlglot/parsers/snowflake.py:450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/presto.py:125:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/spark2.py:80:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/clickhouse.py:294:        "ARRAYSLICE": exp.ArraySlice.from_arg_list,
sqlglot/typing/__init__.py:266:            exp.ArraySlice,
sqlglot/generators/duckdb.py:3572:    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
sqlglot/generators/spark2.py:142:            exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/presto.py:325:        exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/clickhouse.py:291:        exp.ArraySlice: rename_func("arraySlice"),

[read sqlglot/generators/duckdb.py lines 3550-3629]
3550	                )
3551	            )
3552	
3553	        return func
3554	
3555	    def arrayintersect_sql(self, expression: exp.ArrayIntersect) -> str:
3556	        if expression.args.get("is_multiset") and len(expression.expressions) == 2:
3557	            return self._array_bag_sql(
3558	                self.ARRAY_INTERSECTION_CONDITION,
3559	                expression.expressions[0],
3560	                expression.expressions[1],
3561	            )
3562	        return self.function_fallback_sql(expression)
3563	
3564	    def arrayexcept_sql(self, expression: exp.ArrayExcept) -> str:
3565	        arr1, arr2 = expression.this, expression.expression
3566	        if expression.args.get("is_multiset"):
3567	            return self._array_bag_sql(self.ARRAY_EXCEPT_CONDITION, arr1, arr2)
3568	        return self.sql(
3569	            exp.replace_placeholders(self.ARRAY_EXCEPT_SET_TEMPLATE, arr1=arr1, arr2=arr2)
3570	        )
3571	
3572	    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
3573	        """
3574	        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
3575	        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
3576	        expressions that adjust the index at query time:
3577	          - start: CASE WHEN start >= 0 THEN start + 1 ELSE start END
3578	          - end:   CASE WHEN end < 0 THEN end - 1 ELSE end END
3579	        """
3580	        start, end = expression.args.get("start"), expression.args.get("end")
3581	
3582	        if expression.args.get("zero_based"):
3583	            if start is not None:
3584	                start = (
3585	                    exp.case()
3586	                    .when(
3587	                        exp.GTE(this=start.copy(), expression=exp.Literal.number(0)),
3588	                        exp.Add(this=start.copy(), expression=exp.Literal.number(1)),
3589	                    )
3590	                    .else_(start)
3591	                )
3592	            if end is not None:
3593	                end = (
3594	                    exp.case()
3595	                    .when(
3596	                        exp.LT(this=end.copy(), expression=exp.Literal.number(0)),
3597	                        exp.Sub(this=end.copy(), expression=exp.Literal.number(1)),
3598	                    )
3599	                    .else_(end)
3600	                )
3601	
3602	        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
3603	
3604	    def arrayszip_sql(self, expression: exp.ArraysZip) -> str:
3605	        args = expression.expressions
3606	
3607	        if not args:
3608	            # Return [{}] - using MAP([], []) since DuckDB can't represent empty structs
3609	            return self.sql(exp.array(exp.Map(keys=exp.array(), values=exp.array())))
3610	
3611	        # Build placeholder values for template
3612	        lengths = [exp.Length(this=arg) for arg in args]
3613	        max_len = (
3614	            lengths[0]
3615	            if len(lengths) == 1
3616	            else exp.Greatest(this=lengths[0], expressions=lengths[1:])
3617	        )
3618	
3619	        # Empty struct with same schema: {'$1': NULL, '$2': NULL, ...}
3620	        empty_struct = exp.func(
3621	            "STRUCT",
3622	            *[
3623	                exp.PropertyEQ(this=exp.Literal.string(f"${i + 1}"), expression=exp.Null())
3624	                for i in range(len(args))
3625	            ],
3626	        )
3627	
3628	        # Struct for transform: {'$1': COALESCE(arr1, [])[__i + 1], ...}
3629	        # COALESCE wrapping handles NULL arrays - prevents invalid NULL[i] syntax

[read sqlglot/expressions/array.py lines 80-99]
80	
81	
82	class ArrayReverse(Expression, Func):
83	    pass
84	
85	
86	class ArraySlice(Expression, Func):
87	    arg_types = {"this": True, "start": True, "end": False, "step": False, "zero_based": False}
88	
89	
90	class ArraySort(Expression, Func):
91	    arg_types = {"this": True, "expression": False}
92	
93	
94	class Shuffle(Expression, Func):
95	    pass
96	
97	
98	class SortArray(Expression, Func):
99	    arg_types = {"this": True, "asc": False, "nulls_first": False}

$ cd  && sed -n 440,460p sqlglot/parsers/snowflake.py; grep -rn "zero_based" sqlglot | head -20; sed -n 70,90p sqlglot/parsers/spark2.py; grep -n "ArraySlice\|SLICE" sqlglot/parsers/*.py sqlglot/generators/{spark,databricks,hive}.py
/bin/bash: line 1: cd: too many arguments
sqlglot/dialects/dialect.py:2263:    zero_based_indexing: bool = True,
sqlglot/dialects/dialect.py:2282:                    exp.JSONPathSubscript(this=index if zero_based_indexing else index - 1)
sqlglot/expressions/array.py:87:    arg_types = {"this": True, "start": True, "end": False, "step": False, "zero_based": False}
sqlglot/expressions/array.py:141:    arg_types = {"this": True, "expression": True, "zero_based": False}
sqlglot/generators/duckdb.py:1607:            if e.args.get("zero_based")
sqlglot/generators/duckdb.py:3582:        if expression.args.get("zero_based"):
sqlglot/parsers/clickhouse.py:316:            exp.JSONExtractScalar, zero_based_indexing=False
sqlglot/parsers/snowflake.py:448:            zero_based=True,
sqlglot/parsers/snowflake.py:454:            zero_based=True,
            zone=seq_get(args, 1),
        ),
        "LTRIM": lambda args: build_trim(args, reverse_args=True),
        "INT": build_as_cast("int"),
        "MAP_FROM_ARRAYS": exp.Map.from_arg_list,
        "RLIKE": exp.RegexpLike.from_arg_list,
        "RTRIM": lambda args: build_trim(args, is_left=False, reverse_args=True),
        "SHIFTLEFT": binary_from_function(exp.BitwiseLeftShift),
        "SHIFTRIGHT": binary_from_function(exp.BitwiseRightShift),
        "STRING": build_as_cast("string"),
        "SLICE": exp.ArraySlice.from_arg_list,
        "TIMESTAMP": build_as_cast("timestamp"),
        "TO_TIMESTAMP": lambda args, dialect: (
            build_as_cast("timestamp")(args)
            if len(args) == 1
            else build_formatted_time(exp.StrToTime)(args, dialect)
        ),
        "TO_UNIX_TIMESTAMP": exp.StrToUnix.from_arg_list,
        "TO_UTC_TIMESTAMP": lambda args, dialect: exp.FromTimeZone(
            this=exp.cast(
                seq_get(args, 0) or exp.Var(this=""),
sqlglot/parsers/clickhouse.py:294:        "ARRAYSLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/presto.py:125:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/snowflake.py:450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/spark2.py:80:        "SLICE": exp.ArraySlice.from_arg_list,

$ cd  2>/dev/null || cd ; pwd; grep -n "def rename_func" -A12 sqlglot/dialects/dialect.py; python -c "
import sqlglot
print(sqlglot.transpile(\"SELECT ARRAY_SLICE(x,1,2)\",read='snowflake',write='spark'))"

1264:def rename_func(name: str) -> t.Callable[[Generator, exp.Expr], str]:
1265-    return lambda self, expression: self.func(name, *flatten(expression.args.values()))
1266-
1267-
1268-def bracket_to_element_at_sql(self: Generator, expression: exp.Bracket) -> str:
1269-    index = seq_get(
1270-        apply_index_offset(
1271-            expression.this,
1272-            expression.expressions,
1273-            1 - expression.args.get("offset", 0),
1274-            dialect=self.dialect,
1275-        ),
1276-        0,
Unable to set __version__, run `pip install -e .` or `python setup.py develop` first.
['SELECT SLICE(x, 1, 2)']

[grep 'ArraySlice|ARRAY_SLICE|"SLICE"' in sqlglot]
sqlglot/parsers/snowflake.py:450:        "ARRAY_SLICE": lambda args: exp.ArraySlice(
sqlglot/parsers/presto.py:125:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/spark2.py:80:        "SLICE": exp.ArraySlice.from_arg_list,
sqlglot/parsers/clickhouse.py:294:        "ARRAYSLICE": exp.ArraySlice.from_arg_list,
sqlglot/generators/presto.py:325:        exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/spark2.py:142:            exp.ArraySlice: rename_func("SLICE"),
sqlglot/generators/clickhouse.py:291:        exp.ArraySlice: rename_func("arraySlice"),
sqlglot/generators/duckdb.py:3572:    def arrayslice_sql(self, expression: exp.ArraySlice) -> str:
sqlglot/generators/duckdb.py:3574:        Transpiles Snowflake's ARRAY_SLICE (0-indexed, exclusive end) to DuckDB's
sqlglot/generators/duckdb.py:3575:        ARRAY_SLICE (1-indexed, inclusive end) by wrapping start and end in CASE
sqlglot/generators/duckdb.py:3602:        return self.func("ARRAY_SLICE", expression.this, start, end, expression.args.get("step"))
sqlglot/typing/__init__.py:266:            exp.ArraySlice,
sqlglot/expressions/array.py:86:class ArraySlice(Expression, Func):

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
tests/dialects/test_duckdb.py:1473:        self.validate_identity("ARRAY_SLICE(x, 1, 3, 2)")

[read tests/dialects/test_dialect.py lines 1520-1551]
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

[read sqlglot/parsers/spark2.py lines 70-89]
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
80	        "SLICE": exp.ArraySlice.from_arg_list,
81	        "TIMESTAMP": build_as_cast("timestamp"),
82	        "TO_TIMESTAMP": lambda args, dialect: (
83	            build_as_cast("timestamp")(args)
84	            if len(args) == 1
85	            else build_formatted_time(exp.StrToTime)(args, dialect)
86	        ),
87	        "TO_UNIX_TIMESTAMP": exp.StrToUnix.from_arg_list,
88	        "TO_UTC_TIMESTAMP": lambda args, dialect: exp.FromTimeZone(
89	            this=exp.cast(

$ python -c "
from sqlglot import exp
print(exp.ArraySize(this=exp.column('a')).sql('duckdb'))"
Unable to set __version__, run `pip install -e .` or `python setup.py develop` first.
ARRAY_LENGTH(a)

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
