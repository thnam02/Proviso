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
