[sqlglot/dialects/dialect.py lines 1366-1413: array_append_sql]
  1366	def array_append_sql(
  1367	    name: str, swap_params: bool = False
  1368	) -> t.Callable[[Generator, exp.ArrayAppend | exp.ArrayPrepend], str]:
  1369	    """
  1370	    Transpile ARRAY_APPEND/ARRAY_PREPEND between dialects with different NULL propagation semantics.
  1371	
  1372	    Some dialects (Databricks, Spark, Snowflake) return NULL when the input array is NULL.
  1373	    Others (DuckDB, Postgres) create a new single-element array instead.
  1374	
  1375	    Args:
  1376	        name: Target dialect's function name (e.g., "ARRAY_APPEND", "ARRAY_PREPEND")
  1377	        swap_params: If True, generate (element, array) order instead of (array, element).
  1378	                     DuckDB LIST_PREPEND and Postgres ARRAY_PREPEND use (element, array).
  1379	
  1380	    Returns:
  1381	        A callable that generates SQL with appropriate NULL handling for the target dialect.
  1382	        Dialects that propagate NULLs need to set `ARRAY_FUNCS_PROPAGATES_NULLS` to True.
  1383	    """
  1384	
  1385	    def _array_append_sql(self: Generator, expression: exp.ArrayAppend | exp.ArrayPrepend) -> str:
  1386	        this = expression.this
  1387	        element = expression.expression
  1388	        args = [element, this] if swap_params else [this, element]
  1389	        func_sql = self.func(name, *args)
  1390	
  1391	        source_null_propagation = bool(expression.args.get("null_propagation"))
  1392	        target_null_propagation = self.dialect.ARRAY_FUNCS_PROPAGATES_NULLS
  1393	
  1394	        # No transpilation needed when source and target have matching NULL semantics
  1395	        if source_null_propagation == target_null_propagation:
  1396	            return func_sql
  1397	
  1398	        # Source propagates NULLs, target doesn't: wrap in conditional to return NULL explicitly
  1399	        if source_null_propagation:
  1400	            return self.sql(
  1401	                exp.If(
  1402	                    this=exp.Is(this=this, expression=exp.Null()),
  1403	                    true=exp.Null(),
  1404	                    false=func_sql,
  1405	                )
    ... (8 more lines)

[sqlglot/dialects/dialect.py lines 1435-1514: array_concat_sql]
  1435	def array_concat_sql(
  1436	    name: str,
  1437	) -> t.Callable[[Generator, exp.ArrayConcat], str]:
  1438	    """
  1439	    Transpile ARRAY_CONCAT/ARRAY_CAT between dialects with different NULL propagation semantics.
  1440	
  1441	    Some dialects (Redshift, Snowflake, Spark) return NULL when ANY input array is NULL.
  1442	    Others (DuckDB, PostgreSQL) skip NULL arrays and continue concatenation.
  1443	
  1444	    Args:
  1445	        name: Target dialect's function name (e.g., "ARRAY_CAT", "ARRAY_CONCAT", "LIST_CONCAT")
  1446	
  1447	    Returns:
  1448	        A callable that generates SQL with appropriate NULL handling for the target dialect.
  1449	        Dialects that propagate NULLs need to set `ARRAY_FUNCS_PROPAGATES_NULLS` to True.
  1450	    """
  1451	
  1452	    def _build_func_call(self: Generator, func_name: str, args: BuilderArgs) -> str:
  1453	        """Build ARRAY_CONCAT call from a list of arguments, handling variadic vs binary nesting."""
  1454	        if self.ARRAY_CONCAT_IS_VAR_LEN:
  1455	            return self.func(func_name, *args)
  1456	        elif len(args) == 1:
  1457	            # Single arg gets empty array to preserve semantics
  1458	            return self.func(func_name, args[0], exp.Array(expressions=[]))
  1459	        else:
  1460	            # Snowflake/PostgreSQL/Redshift require binary nesting: ARRAY_CAT(a, ARRAY_CAT(b, c))
  1461	            # Build right-deep tree recursively to avoid creating new ArrayConcat expressions
  1462	            result = self.func(func_name, args[-2], args[-1])
  1463	            for arg in reversed(args[:-2]):
  1464	                result = f"{func_name}({self.sql(arg)}, {result})"
  1465	            return result
  1466	
  1467	    def _array_concat_sql(self: Generator, expression: exp.ArrayConcat) -> str:
  1468	        this = expression.this
  1469	        exprs = expression.expressions
  1470	        all_args = [this] + exprs
  1471	
  1472	        source_null_propagation = bool(expression.args.get("null_propagation"))
  1473	        target_null_propagation = self.dialect.ARRAY_FUNCS_PROPAGATES_NULLS
  1474	
    ... (40 more lines)

[sqlglot/dialects/postgres.py lines 17-17: Postgres.<stmt@17>]
    17	    NULL_ORDERING = "nulls_are_large"

[sqlglot/generator.py lines 3031-3032: Generator.null_sql]
  3031	    def null_sql(self, *_) -> str:
  3032	        return "NULL"

[sqlglot/generator.py lines 3967-3968: Generator.not_sql]
  3967	    def not_sql(self, expression: exp.Not) -> str:
  3968	        return f"NOT {self.sql(expression, 'this')}"

[sqlglot/generator.py lines 4442-4447: Generator.is_sql]
  4442	    def is_sql(self, expression: exp.Is) -> str:
  4443	        if not self.IS_BOOL_ALLOWED and isinstance(expression.expression, exp.Boolean):
  4444	            return self.sql(
  4445	                expression.this if expression.expression.this else exp.not_(expression.this)
  4446	            )
  4447	        return self.binary(expression, "IS")

[sqlglot/generators/postgres.py lines 55-77: _date_add_sql]
    55	def _date_add_sql(kind: str) -> t.Callable[[PostgresGenerator, DATE_ADD_OR_SUB], str]:
    56	    def func(self: PostgresGenerator, expression: DATE_ADD_OR_SUB) -> str:
    57	        if isinstance(expression, exp.TsOrDsAdd):
    58	            expression = ts_or_ds_add_cast(expression)
    59	
    60	        this = self.sql(expression, "this")
    61	        unit = expression.args.get("unit")
    62	
    63	        e = self._simplify_unless_literal(expression.expression)
    64	        if isinstance(e, exp.Interval):
    65	            return f"{this} {kind} {self.sql(e)}"
    66	        elif isinstance(e, exp.Literal):
    67	            e.set("is_string", True)
    68	        elif e.is_number:
    69	            e = exp.Literal.string(e.to_py())
    70	        else:
    71	            one = exp.Literal.number(1)
    72	            interval_times_value = exp.Interval(this=one, unit=unit) * e
    73	            return f"{this} {kind} {self.sql(interval_times_value)}"
    74	
    75	        return f"{this} {kind} {self.sql(exp.Interval(this=e, unit=unit))}"
    76	
    77	    return func

[sqlglot/generators/postgres.py lines 171-179: _json_extract_sql]
   171	def _json_extract_sql(
   172	    name: str, op: str
   173	) -> t.Callable[[PostgresGenerator, JSON_EXTRACT_TYPE], str]:
   174	    def _generate(self: PostgresGenerator, expression: JSON_EXTRACT_TYPE) -> str:
   175	        if expression.args.get("only_json_types"):
   176	            return json_extract_segments(name, quoted_index=False, op=op)(self, expression)
   177	        return json_extract_segments(name)(self, expression)
   178	
   179	    return _generate

[sqlglot/generators/postgres.py lines 458-463: PostgresGenerator.bracket_sql]
   458	    def bracket_sql(self, expression: exp.Bracket) -> str:
   459	        """Forms like ARRAY[1, 2, 3][3] aren't allowed; we need to wrap the ARRAY."""
   460	        if isinstance(expression.this, exp.Array):
   461	            expression.set("this", exp.paren(expression.this, copy=False))
   462	
   463	        return super().bracket_sql(expression)

[sqlglot/parser.py lines 1190-1199: Parser.<stmt@1190>]
  1190	    PRIMARY_PARSERS: t.ClassVar = {
  1191	        **STRING_PARSERS,
  1192	        **NUMERIC_PARSERS,
  1193	        TokenType.INTRODUCER: lambda self, token: self._parse_introducer(token),
  1194	        TokenType.NULL: lambda self, _: self.expression(exp.Null()),
  1195	        TokenType.TRUE: lambda self, _: self.expression(exp.Boolean(this=True)),
  1196	        TokenType.FALSE: lambda self, _: self.expression(exp.Boolean(this=False)),
  1197	        TokenType.SESSION_PARAMETER: lambda self, _: self._parse_session_parameter(),
  1198	        TokenType.STAR: lambda self, _: self._parse_star_ops(),
  1199	    }

[sqlglot/parser.py lines 1211-1233: Parser.<stmt@1211>]
  1211	    RANGE_PARSERS: t.ClassVar = {
  1212	        TokenType.AT_GT: binary_range_parser(exp.ArrayContainsAll),
  1213	        TokenType.BETWEEN: lambda self, this: self._parse_between(this),
  1214	        TokenType.GLOB: binary_range_parser(exp.Glob),
  1215	        TokenType.ILIKE: binary_range_parser(exp.ILike),
  1216	        TokenType.IN: lambda self, this: self._parse_in(this),
  1217	        TokenType.IRLIKE: binary_range_parser(exp.RegexpILike),
  1218	        TokenType.IS: lambda self, this: self._parse_is(this),
  1219	        TokenType.LIKE: binary_range_parser(exp.Like),
  1220	        TokenType.LT_AT: binary_range_parser(exp.ArrayContainedBy),
  1221	        TokenType.OVERLAPS: binary_range_parser(exp.Overlaps),
  1222	        TokenType.RLIKE: binary_range_parser(exp.RegexpLike),
  1223	        TokenType.SIMILAR_TO: binary_range_parser(exp.SimilarTo),
  1224	        TokenType.FOR: lambda self, this: self._parse_comprehension(this),
  1225	        TokenType.QMARK_AMP: binary_range_parser(exp.JSONBContainsAllTopKeys),
  1226	        TokenType.QMARK_PIPE: binary_range_parser(exp.JSONBContainsAnyTopKeys),
  1227	        TokenType.HASH_DASH: binary_range_parser(exp.JSONBDeleteAtPath),
  1228	        TokenType.AT_QMARK: binary_range_parser(exp.JSONBPathExists),
  1229	        TokenType.ADJACENT: binary_range_parser(exp.Adjacent),
  1230	        TokenType.OPERATOR: lambda self, this: self._parse_operator(this),
  1231	        TokenType.AMP_LT: binary_range_parser(exp.ExtendsLeft),
  1232	        TokenType.AMP_GT: binary_range_parser(exp.ExtendsRight),
  1233	    }

[sqlglot/parser.py lines 5937-5968: Parser._parse_range]
  5937	    def _parse_range(self, this: exp.Expr | None = None) -> exp.Expr | None:
  5938	        this = this or self._parse_bitwise()
  5939	
  5940	        while True:
  5941	            negate = self._match(TokenType.NOT)
  5942	            if self._match_set(self.RANGE_PARSERS):
  5943	                expression = self.RANGE_PARSERS[self._prev.token_type](self, this)
  5944	                if not expression:
  5945	                    return this
  5946	
  5947	                this = expression
  5948	            elif self._match(TokenType.ISNULL) or (negate and self._match(TokenType.NULL)):
  5949	                this = self.expression(exp.Is(this=this, expression=exp.Null()))
  5950	            elif self._match(TokenType.NOTNULL):
  5951	                # Postgres supports ISNULL and NOTNULL for conditions.
  5952	                # https://blog.andreiavram.ro/postgresql-null-composite-type/
  5953	                this = self.expression(exp.Is(this=this, expression=exp.Null()))
  5954	                this = self.expression(exp.Not(this=this))
  5955	            else:
  5956	                if negate:
  5957	                    self._retreat(self._index - 1)
  5958	                break
  5959	
  5960	            if negate:
  5961	                this = self._negate_range(this)
  5962	                if self._curr and (
  5963	                    self._curr.token_type == TokenType.NOT
  5964	                    or self._curr.token_type in self.RANGE_PARSERS
  5965	                ):
  5966	                    this = self.expression(exp.Paren(this=this))
  5967	
  5968	        return this

[sqlglot/parser.py lines 5981-6012: Parser._parse_is]
  5981	    def _parse_is(self, this: exp.Expr | None) -> exp.Expr | None:
  5982	        index = self._index - 1
  5983	        negate = self._match(TokenType.NOT)
  5984	
  5985	        if self._match_text_seq("DISTINCT", "FROM"):
  5986	            klass = exp.NullSafeEQ if negate else exp.NullSafeNEQ
  5987	            return self.expression(klass(this=this, expression=self._parse_bitwise()))
  5988	
  5989	        if self._match(TokenType.JSON):
  5990	            kind = self._match_texts(self.IS_JSON_PREDICATE_KIND) and self._prev.text.upper()
  5991	
  5992	            if self._match_text_seq("WITH"):
  5993	                _with = True
  5994	            elif self._match_text_seq("WITHOUT"):
  5995	                _with = False
  5996	            else:
  5997	                _with = None
  5998	
  5999	            unique = self._match(TokenType.UNIQUE)
  6000	            self._match_text_seq("KEYS")
  6001	            expression: exp.Expr | None = self.expression(
  6002	                exp.JSON(this=kind, with_=_with, unique=unique)
  6003	            )
  6004	        else:
  6005	            expression = self._parse_null() or self._parse_bitwise()
  6006	            if not expression:
  6007	                self._retreat(index)
  6008	                return None
  6009	
  6010	        this = self.expression(exp.Is(this=this, expression=expression))
  6011	        this = self.expression(exp.Not(this=this)) if negate else this
  6012	        return self._parse_column_ops(this)

[sqlglot/parser.py lines 6853-6919: Parser._parse_column_ops]
  6853	    def _parse_column_ops(self, this: exp.Expr | None) -> exp.Expr | None:
  6854	        while self._curr.token_type in self.BRACKETS:
  6855	            this = self._parse_bracket(this)
  6856	
  6857	        column_operators = self.COLUMN_OPERATORS
  6858	        cast_column_operators = self.CAST_COLUMN_OPERATORS
  6859	        while self._curr:
  6860	            op_token = self._curr.token_type
  6861	
  6862	            if op_token not in column_operators:
  6863	                break
  6864	            op = column_operators[op_token]
  6865	            self._advance()
  6866	
  6867	            if op_token in cast_column_operators:
  6868	                field = self._parse_dcolon()
  6869	                if not field:
  6870	                    self.raise_error("Expected type")
  6871	            elif op and self._curr:
  6872	                field = self._parse_column_reference() or self._parse_bitwise()
  6873	                if isinstance(field, exp.Column) and self._match(TokenType.DOT, advance=False):
  6874	                    field = self._parse_column_ops(field)
  6875	            else:
  6876	                dot = self._is_connected() and self._prev.token_type == TokenType.DOT
  6877	                field = self._parse_field(any_token=True, anonymous_func=True)
  6878	
  6879	                # In t.true, t.null we should produce an Identifier node
  6880	                if dot and isinstance(field, (exp.Null, exp.Boolean)):
  6881	                    field = self.expression(
  6882	                        exp.Identifier(this=self._prev.text),
  6883	                        comments=field.comments,
  6884	                    )
  6885	
  6886	            # Function calls can be qualified, e.g., x.y.FOO()
  6887	            # This converts the final AST to a series of Dots leading to the function call
  6888	            # https://cloud.google.com/bigquery/docs/reference/standard-sql/functions-reference#function_call_rules
  6889	            if isinstance(field, (exp.Func, exp.Window)) and this:
  6890	                this = this.transform(
  6891	                    lambda n: n.to_dot(include_dots=False) if isinstance(n, exp.Column) else n
  6892	                )
    ... (27 more lines)

[sqlglot/parser.py lines 8666-8669: Parser._parse_null]
  8666	    def _parse_null(self) -> exp.Expr | None:
  8667	        if self._match_set((TokenType.NULL, TokenType.UNKNOWN)):
  8668	            return self.PRIMARY_PARSERS[TokenType.NULL](self, self._prev)
  8669	        return self._parse_placeholder()

[sqlglot/parsers/postgres.py lines 89-92: PostgresParser.<stmt@89>]
    89	    PROPERTY_PARSERS = {
    90	        **{k: v for k, v in parser.Parser.PROPERTY_PARSERS.items() if k != "INPUT"},
    91	        "SET": lambda self: self.expression(exp.SetConfigProperty(this=self._parse_set())),
    92	    }

[grep -nw NOTNULL sqlglot/]
sqlglot/parser.py:5950:            elif self._match(TokenType.NOTNULL):
sqlglot/parser.py:5951:                # Postgres supports ISNULL and NOTNULL for conditions.
sqlglot/tokenizer_core.py:355:    NOTNULL = auto()
sqlglot/tokens.py:324:        "NOTNULL": TokenType.NOTNULL,

[grep -nw Unknown sqlglot/]
sqlglot/helper.py:64:    raise ValueError(f"Unknown {kind} '{word}'.{similar}")
sqlglot/lineage.py:338:            logger.warning(f"Unknown subquery scope: {subquery.sql(dialect=dialect)}")
sqlglot/optimizer/qualify_columns.py:557:        raise OptimizeError(f"Unknown output column: {node.name}")
sqlglot/optimizer/qualify_columns.py:634:                raise OptimizeError(f"Unknown column: {column_name}")
sqlglot/optimizer/qualify_columns.py:867:                raise OptimizeError(f"Unknown table: {table}")
sqlglot/optimizer/resolver.py:103:            raise OptimizeError(f"Unknown set operation: {expression}")
sqlglot/optimizer/resolver.py:139:                raise OptimizeError(f"Unknown table: {name}")
sqlglot/parser.py:9398:                    self.raise_error(f"Unknown option {option}")
sqlglot/schema.py:771:                raise ValueError(f"Unknown {name}: {key}")

[grep -nw ISNULL sqlglot/]
sqlglot/generators/tsql.py:106:    return self.func("ISNULL", json_query, json_value)
sqlglot/generators/tsql.py:614:        func_name = "ISNULL" if expression.args.get("is_null") else "COALESCE"
sqlglot/parser.py:730:        TokenType.ISNULL,
sqlglot/parser.py:865:        TokenType.ISNULL,
sqlglot/parser.py:5948:            elif self._match(TokenType.ISNULL) or (negate and self._match(TokenType.NULL)):
sqlglot/parser.py:5951:                # Postgres supports ISNULL and NOTNULL for conditions.
sqlglot/parsers/mysql.py:129:        "ISNULL": isnull_to_is_null,
sqlglot/parsers/tsql.py:370:        "ISNULL": lambda args: build_coalesce(args=args, is_null=True),
sqlglot/tokenizer_core.py:330:    ISNULL = auto()
sqlglot/tokens.py:307:        "ISNULL": TokenType.ISNULL,

[grep -nw FALSE sqlglot/]
sqlglot/dialects/dialect.py:665:    from a table, then the result is `NULL`, despite `FALSE AND NULL` evaluating to `FALSE`.
sqlglot/generator.py:3035:        return "TRUE" if expression.this else "FALSE"
sqlglot/generators/duckdb.py:253:            # Handle 'off' -> FALSE (case insensitive)
sqlglot/generators/duckdb.py:564:    DuckDB's native && operator is not NULL-safe: [1,NULL,3] && [NULL,4,5] returns FALSE.
sqlglot/generators/duckdb.py:1247:    Snowflake's `BOOLXOR_AGG(col)` returns TRUE if exactly one input in `col` is TRUE, FALSE otherwise;
sqlglot/generators/duckdb.py:2210:    #   3 IN UNNEST([1, 2])     -> FALSE
sqlglot/generators/duckdb.py:2211:    #   1 IN UNNEST(NULL)       -> FALSE (not NULL)
sqlglot/generators/duckdb.py:2212:    #   1 IN UNNEST([])         -> FALSE
sqlglot/generators/duckdb.py:2218:            WHEN :arr IS NULL OR ARRAY_LENGTH(:arr) = 0 THEN FALSE
sqlglot/generators/duckdb.py:2221:            ELSE FALSE
sqlglot/generators/postgres.py:563:        #                            ELSE COALESCE(value = ANY(array), FALSE) END
sqlglot/generators/starrocks.py:64:    # StarRocks doesn't support "IS TRUE/FALSE" syntax.
sqlglot/optimizer/simplify.py:961:        A AND NOT A -> FALSE (only for non-NULL A)
sqlglot/optimizer/simplify.py:1388:        Reduces a prefix check to either TRUE or FALSE if both the string and the
sqlglot/optimizer/simplify.py:1642:        self.stack.append("TRUE" if e.this else "FALSE")
sqlglot/parser.py:719:        TokenType.FALSE,
sqlglot/parser.py:1196:        TokenType.FALSE: lambda self, _: self.expression(exp.Boolean(this=False)),
sqlglot/parser.py:1739:    ON_CONDITION_TOKENS: t.ClassVar = {"ERROR", "NULL", "TRUE", "FALSE", "EMPTY"}
sqlglot/parser.py:8674:        if self._match(TokenType.FALSE):
sqlglot/parser.py:8675:            return self.PRIMARY_PARSERS[TokenType.FALSE](self, self._prev)
sqlglot/tokenizer_core.py:293:    FALSE = auto()
sqlglot/tokens.py:280:        "FALSE": TokenType.FALSE,

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
