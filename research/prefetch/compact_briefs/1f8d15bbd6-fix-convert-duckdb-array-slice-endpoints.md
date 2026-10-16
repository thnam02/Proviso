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

$ cd ; python -c "
import duckdb
for a in ['2,3','0,2','3,2','-2,-1','-10,2','-10,-8','-3,-1','1,-10','2,-2','0,0','2,10','-1,0','5,6','-2,5']:
    print(a, duckdb.sql(f'select array_slice([1,2,3,4],{a})').fetchall())
"; grep -n "LIST_\|ARRAY_SLICE" sqlglot/parsers/duckdb.py | head -20
Traceback (most recent call last):
  File "<string>", line 2, in <module>
    import duckdb
ModuleNotFoundError: No module named 'duckdb'
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

[read sqlglot/expressions/array.py lines 80-104]
80	    arg_types = {"this": True, "position": True}
81	
82	
83	class ArrayReverse(Expression, Func):
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
96	        "is_length": False,
97	    }
98	
99	
100	class ArraySort(Expression, Func):
101	    arg_types = {"this": True, "expression": False}
102	
103	
104	class Shuffle(Expression, Func):

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
