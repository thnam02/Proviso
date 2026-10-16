[sqlglot/dialects/dialect.py lines 1963-2001: build_trunc]
  1963	def build_trunc(
  1964	    args: BuilderArgs,
  1965	    dialect: DialectType,
  1966	    date_trunc_unabbreviate: bool = True,
  1967	    default_date_trunc_unit: str | None = None,
  1968	    date_trunc_requires_part: bool = True,
  1969	    fractions_supported: bool = False,
  1970	) -> exp.DateTrunc | exp.Trunc | exp.Anonymous:
  1971	    """
  1972	    Builder for dialects with overloaded TRUNC (Oracle, Snowflake, etc).
  1973	    Uses type annotation to distinguish date vs numeric truncation.
  1974	    Returns Anonymous if type cannot be determined.
  1975	    """
  1976	    from sqlglot.optimizer.annotate_types import annotate_types
  1977	
  1978	    this = seq_get(args, 0)
  1979	    second = seq_get(args, 1)
  1980	
  1981	    if this and not this.type:
  1982	        this = annotate_types(this, dialect=dialect)
  1983	    if second and not second.type:
  1984	        second = annotate_types(second, dialect=dialect)
  1985	
  1986	    # Date truncation
  1987	    if (
  1988	        this and this.is_type(*exp.DataType.TEMPORAL_TYPES) and (second or default_date_trunc_unit)
  1989	    ) or (second and second.is_type(*exp.DataType.TEXT_TYPES)):
  1990	        unit = second or exp.Literal.string(default_date_trunc_unit)
  1991	        return exp.DateTrunc(this=this, unit=unit, unabbreviate=date_trunc_unabbreviate)
  1992	
  1993	    # Numeric truncation
  1994	    if (
  1995	        (this and this.is_type(*exp.DataType.NUMERIC_TYPES))
  1996	        or (second and second.is_type(*exp.DataType.NUMERIC_TYPES))
  1997	        or (not date_trunc_requires_part and not second)
  1998	    ):
  1999	        return exp.Trunc(this=this, decimals=second, fractions_supported=fractions_supported)
  2000	
  2001	    return exp.Anonymous(this="TRUNC", expressions=args)

[sqlglot/expressions/builders.py lines 457-515: cast]
   457	def cast(
   458	    expression: ExpOrStr,
   459	    to: DATA_TYPE,
   460	    copy: bool = True,
   461	    dialect: DialectType = None,
   462	    **opts: Unpack[ParserNoDialectArgs],
   463	) -> Cast:
   464	    """Cast an expression to a data type.
   465	
   466	    Example:
   467	        >>> cast('x + 1', 'int').sql()
   468	        'CAST(x + 1 AS INT)'
   469	
   470	    Args:
   471	        expression: The expression to cast.
   472	        to: The datatype to cast to.
   473	        copy: Whether to copy the supplied expressions.
   474	        dialect: The target dialect. This is used to prevent a re-cast in the following scenario:
   475	            - The expression to be cast is already a exp.Cast expression
   476	            - The existing cast is to a type that is logically equivalent to new type
   477	
   478	            For example, if :expression='CAST(x as DATETIME)' and :to=Type.TIMESTAMP,
   479	            but in the target dialect DATETIME is mapped to TIMESTAMP, then we will NOT return `CAST(x (as DATETIME) as TIMESTAMP)`
   480	            and instead just return the original expression `CAST(x as DATETIME)`.
   481	
   482	            This is to prevent it being output as a double cast `CAST(x (as TIMESTAMP) as TIMESTAMP)` once the DATETIME -> TIMESTAMP
   483	            mapping is applied in the target dialect generator.
   484	
   485	    Returns:
   486	        The new Cast instance.
   487	    """
   488	    expr = maybe_parse(expression, copy=copy, dialect=dialect, **opts)
   489	    data_type = DataType.build(to, copy=copy, dialect=dialect, **opts)
   490	
   491	    # dont re-cast if the expression is already a cast to the correct type
   492	    if isinstance(expr, Cast):
   493	        from sqlglot.dialects.dialect import Dialect
   494	
   495	        target_dialect = Dialect.get_or_raise(dialect)
   496	        type_mapping = target_dialect.generator_class.TYPE_MAPPING
    ... (19 more lines)

[sqlglot/expressions/core.py lines 1533-1534: Expression.__floordiv__]
  1533	    def __floordiv__(self, other: t.Any) -> IntDiv:
  1534	        return self._binop(IntDiv, other)

[sqlglot/expressions/core.py lines 2381-2465: convert]
  2381	def convert(value: t.Any, copy: bool = False) -> Expr:
  2382	    """Convert a python value into an expression object.
  2383	
  2384	    Raises an error if a conversion is not possible.
  2385	
  2386	    Args:
  2387	        value: A python object.
  2388	        copy: Whether to copy `value` (only applies to Exprs and collections).
  2389	
  2390	    Returns:
  2391	        The equivalent expression object.
  2392	    """
  2393	    if isinstance(value, Expr):
  2394	        return maybe_copy(value, copy)
  2395	    if isinstance(value, str):
  2396	        return Literal.string(value)
  2397	    if isinstance(value, bool):
  2398	        return Boolean(this=value)
  2399	    if value is None or (isinstance(value, float) and math.isnan(value)):
  2400	        return Null()
  2401	    if isinstance(value, numbers.Number):
  2402	        return Literal.number(value)
  2403	    if isinstance(value, bytes):
  2404	        from sqlglot.expressions.query import HexString as _HexString
  2405	
  2406	        return _HexString(this=value.hex())
  2407	    if isinstance(value, datetime.datetime):
  2408	        datetime_literal = Literal.string(value.isoformat(sep=" "))
  2409	
  2410	        tz = None
  2411	        if value.tzinfo:
  2412	            # this works for zoneinfo.ZoneInfo, pytz.timezone and datetime.datetime.utc to return IANA timezone names like "America/Los_Angeles"
  2413	            # instead of abbreviations like "PDT". This is for consistency with other timezone handling functions in SQLGlot
  2414	            tz = Literal.string(str(value.tzinfo))
  2415	
  2416	        from sqlglot.expressions.temporal import TimeStrToTime as _TimeStrToTime
  2417	
  2418	        return _TimeStrToTime(this=datetime_literal, zone=tz)
  2419	    if isinstance(value, datetime.date):
  2420	        date_literal = Literal.string(value.strftime("%Y-%m-%d"))
    ... (45 more lines)

[sqlglot/expressions/functions.py lines 45-47: Cast.name]
    45	    @property
    46	    def name(self) -> str:
    47	        return self.this.name

[sqlglot/generator.py lines 4211-4220: Generator.cast_sql]
  4211	    def cast_sql(self, expression: exp.Cast, safe_prefix: str | None = None) -> str:
  4212	        format_sql = self.sql(expression, "format")
  4213	        format_sql = f" FORMAT {format_sql}" if format_sql else ""
  4214	        to_sql = self.sql(expression, "to")
  4215	        to_sql = f" {to_sql}" if to_sql else ""
  4216	        action = self.sql(expression, "action")
  4217	        action = f" {action}" if action else ""
  4218	        default = self.sql(expression, "default")
  4219	        default = f" DEFAULT {default} ON CONVERSION ERROR" if default else ""
  4220	        return f"{safe_prefix or ''}CAST({self.sql(expression, 'this')} AS{to_sql}{default}{format_sql}{action})"

[sqlglot/generator.py lines 4517-4523: Generator.intdiv_sql]
  4517	    def intdiv_sql(self, expression: exp.IntDiv) -> str:
  4518	        return self.sql(
  4519	            exp.Cast(
  4520	                this=exp.Div(this=expression.this, expression=expression.expression),
  4521	                to=exp.DataType(this=exp.DType.INT),
  4522	            )
  4523	        )

[sqlglot/generator.py lines 4530-4549: Generator.div_sql]
  4530	    def div_sql(self, expression: exp.Div) -> str:
  4531	        l, r = expression.left, expression.right
  4532	
  4533	        if not self.dialect.SAFE_DIVISION and expression.args.get("safe"):
  4534	            r.replace(exp.Nullif(this=r.copy(), expression=exp.Literal.number(0)))
  4535	
  4536	        if self.dialect.TYPED_DIVISION and not expression.args.get("typed"):
  4537	            if not l.is_type(*exp.DataType.REAL_TYPES) and not r.is_type(*exp.DataType.REAL_TYPES):
  4538	                l.replace(exp.cast(l.copy(), to=exp.DType.DOUBLE))
  4539	
  4540	        elif not self.dialect.TYPED_DIVISION and expression.args.get("typed"):
  4541	            if l.is_type(*exp.DataType.INTEGER_TYPES) and r.is_type(*exp.DataType.INTEGER_TYPES):
  4542	                return self.sql(
  4543	                    exp.cast(
  4544	                        l / r,
  4545	                        to=exp.DType.BIGINT,
  4546	                    )
  4547	                )
  4548	
  4549	        return self.binary(expression, "/")

[sqlglot/optimizer/annotate_types.py lines 46-84: annotate_types]
    46	def annotate_types(
    47	    expression: E,
    48	    schema: dict[str, object] | Schema | None = None,
    49	    expression_metadata: ExprMetadataType | None = None,
    50	    coerces_to: dict[exp.DType, set[exp.DType]] | None = None,
    51	    dialect: DialectType = None,
    52	    overwrite_types: bool = True,
    53	) -> E:
    54	    """
    55	    Infers the types of an expression, annotating its AST accordingly.
    56	
    57	    Example:
    58	        >>> import sqlglot
    59	        >>> schema = {"y": {"cola": "SMALLINT"}}
    60	        >>> sql = "SELECT x.cola + 2.5 AS cola FROM (SELECT y.cola AS cola FROM y AS y) AS x"
    61	        >>> annotated_expr = annotate_types(sqlglot.parse_one(sql), schema=schema)
    62	        >>> annotated_expr.expressions[0].type.this  # Get the type of "x.cola + 2.5 AS cola"
    63	        <DType.DOUBLE: 'DOUBLE'>
    64	
    65	    Args:
    66	        expression: Expr to annotate.
    67	        schema: Database schema.
    68	        expression_metadata: Maps expression type to corresponding annotation function.
    69	        coerces_to: Maps expression type to set of types that it can be coerced into.
    70	        dialect: The dialect to consult when constructing a Schema object, if needed.
    71	        overwrite_types: Re-annotate the existing AST types.
    72	
    73	    Returns:
    74	        The expression annotated with types.
    75	    """
    76	
    77	    schema = ensure_schema(schema, dialect=dialect)
    78	
    79	    return TypeAnnotator(
    80	        schema=schema,
    81	        expression_metadata=expression_metadata,
    82	        coerces_to=coerces_to,
    83	        overwrite_types=overwrite_types,
    84	    ).annotate(expression)

[sqlglot/optimizer/annotate_types.py lines 196-231: TypeAnnotator.__init__]
   196	    def __init__(
   197	        self,
   198	        schema: Schema,
   199	        expression_metadata: ExprMetadataType | None = None,
   200	        coerces_to: dict[exp.DType, set[exp.DType]] | None = None,
   201	        binary_coercions: BinaryCoercions | None = None,
   202	        overwrite_types: bool = True,
   203	    ) -> None:
   204	        self.schema = schema
   205	        dialect = schema.dialect or Dialect()
   206	        self.dialect = dialect
   207	        self.expression_metadata = expression_metadata or dialect.EXPRESSION_METADATA
   208	        self.coerces_to = coerces_to or dialect.COERCES_TO or self.COERCES_TO
   209	        self.binary_coercions = binary_coercions or self.BINARY_COERCIONS
   210	
   211	        # Caches the ids of annotated sub-Exprs, to ensure we only visit them once
   212	        self._visited: set[int] = set()
   213	
   214	        # Caches NULL-annotated expressions to set them to UNKNOWN after type inference is completed
   215	        self._null_expressions: dict[int, exp.Expr] = {}
   216	
   217	        # Databricks and Spark ≥v3 actually support NULL (i.e., VOID) as a type
   218	        self._supports_null_type = dialect.SUPPORTS_NULL_TYPE
   219	
   220	        # Maps an exp.SetOperation's id (e.g. UNION) to its projection types. This is computed if the
   221	        # exp.SetOperation is the expression of a scope source, as selecting from it multiple times
   222	        # would reprocess the entire subtree to coerce the types of its operands' projections
   223	        self._setop_column_types: dict[int, dict[str, exp.DataType | exp.DType]] = {}
   224	
   225	        # When set to False, this enables partial annotation by skipping already-annotated nodes
   226	        self._overwrite_types = overwrite_types
   227	
   228	        # Maps (Scope, source_name) to its column projections and types
   229	        self._scope_source_selects: dict[
   230	            tuple[Scope, str], dict[str, exp.DataType | exp.DType]
   231	        ] = {}

[sqlglot/optimizer/annotate_types.py lines 255-276: TypeAnnotator._set_type]
   255	    def _set_type(
   256	        self, expression: exp.Expr, target_type: exp.DataType | exp.DType | None
   257	    ) -> exp.Expr:
   258	        prev_type = expression.type
   259	        expression_id = id(expression)
   260	
   261	        # TODO (mypyc): expression.type = ... should work but mypyc compiles the property
   262	        # setter to enforce the getter's return type (Optional[DataType]), rejecting DType.
   263	        # Bypass by converting and assigning to _type directly.
   264	        dtype = target_type or exp.DType.UNKNOWN
   265	        expression._type = dtype if isinstance(dtype, exp.DataType) else dtype.into_expr()
   266	        self._visited.add(expression_id)
   267	
   268	        if (
   269	            not self._supports_null_type
   270	            and t.cast(exp.DataType, expression.type).this == exp.DType.NULL
   271	        ):
   272	            self._null_expressions[expression_id] = expression
   273	        elif prev_type and t.cast(exp.DataType, prev_type).this == exp.DType.NULL:
   274	            self._null_expressions.pop(expression_id, None)
   275	
   276	        return expression

[sqlglot/optimizer/annotate_types.py lines 815-825: TypeAnnotator._annotate_literal]
   815	    def _annotate_literal(self, expression: exp.Literal) -> exp.Literal:
   816	        if expression.is_string:
   817	            self._set_type(expression, exp.DType.VARCHAR)
   818	        elif expression.is_int:
   819	            self._set_type(expression, exp.DType.INT)
   820	        else:
   821	            self._set_type(expression, exp.DType.DOUBLE)
   822	
   823	        expression.meta["nonnull"] = True
   824	
   825	        return expression

[sqlglot/schema.py lines 177-178: AbstractMappingSchema.udf_depth]
   177	    def udf_depth(self) -> int:
   178	        return dict_depth(self.udf_mapping)

[sqlglot/transforms.py lines 656-665: epoch_cast_to_ts]
   656	def epoch_cast_to_ts(expression: exp.Expr) -> exp.Expr:
   657	    """Replace 'epoch' in casts by the equivalent date literal."""
   658	    if (
   659	        isinstance(expression, (exp.Cast, exp.TryCast))
   660	        and expression.name.lower() == "epoch"
   661	        and expression.to.this in exp.DataType.TEMPORAL_TYPES
   662	    ):
   663	        expression.this.replace(exp.Literal.string("1970-01-01 00:00:00"))
   664	
   665	    return expression

[sqlglot/typing/__init__.py lines 18-379: <stmt@18>]
    18	EXPRESSION_METADATA: ExprMetadataType = {
    19	    **{
    20	        expr_type: {"annotator": lambda self, e: self._annotate_binary(e)}
    21	        for expr_type in subclasses(exp.__name__, exp.Binary)
    22	    },
    23	    **{
    24	        expr_type: {"annotator": lambda self, e: self._annotate_unary(e)}
    25	        for expr_type in subclasses(
    26	            exp.__name__, (exp.Unary, exp.Alias, exp.IgnoreNulls, exp.RespectNulls)
    27	        )
    28	    },
    29	    **{
    30	        expr_type: {"returns": exp.DType.BIGINT}
    31	        for expr_type in {
    32	            exp.ApproxDistinct,
    33	            exp.ArraySize,
    34	            exp.CountIf,
    35	            exp.DenseRank,
    36	            exp.Int64,
    37	            exp.Ntile,
    38	            exp.Rank,
    39	            exp.RowNumber,
    40	            exp.UnixSeconds,
    41	            exp.UnixMicros,
    42	            exp.UnixMillis,
    43	        }
    44	    },
    45	    **{
    46	        expr_type: {"returns": exp.DType.BINARY}
    47	        for expr_type in {
    48	            exp.FromBase32,
    49	            exp.FromBase64,
    50	        }
    51	    },
    52	    **{
    53	        expr_type: {"returns": exp.DType.BOOLEAN}
    54	        for expr_type in {
    55	            exp.All,
    56	            exp.Any,
    57	            exp.Between,
    ... (322 more lines)

[grep -nw Double sqlglot/]
sqlglot/generators/duckdb.py:4506:            # Double AT TIME ZONE needed for BigQuery compatibility:

[grep -nw Integer sqlglot/]
sqlglot/generator.py:1634:            # Integer representation will be returned if:
sqlglot/generators/duckdb.py:2913:        - Integer result if both min and max are integers
sqlglot/generators/duckdb.py:4413:            # Integer case: standard INTERVAL N MONTH syntax

[grep -nw Truncate sqlglot/]
sqlglot/generators/duckdb.py:963:        # Truncate both dates to week boundaries to respect input dialect semantics
sqlglot/optimizer/simplify.py:499:    # Truncate sub-day units — only valid for datetime inputs
sqlglot/optimizer/simplify.py:512:    # Truncate date-level units, shared for both date and datetime

[grep -nw Trunc sqlglot/]
sqlglot/dialects/dialect.py:1970:) -> exp.DateTrunc | exp.Trunc | exp.Anonymous:
sqlglot/dialects/dialect.py:1999:        return exp.Trunc(this=this, decimals=second, fractions_supported=fractions_supported)
sqlglot/expressions/math.py:200:class Trunc(Expression, Func):
sqlglot/generators/clickhouse.py:341:        exp.Trunc: rename_func("trunc"),
sqlglot/generators/duckdb.py:2871:    def trunc_sql(self, expression: exp.Trunc) -> str:
sqlglot/generators/hive.py:494:    def trunc_sql(self, expression: exp.Trunc) -> str:
sqlglot/generators/mysql.py:216:        exp.Trunc: rename_func("TRUNCATE"),
sqlglot/generators/presto.py:431:        exp.Trunc: rename_func("TRUNCATE"),
sqlglot/generators/sqlite.py:298:    def trunc_sql(self, expression: exp.Trunc) -> str:
sqlglot/generators/tsql.py:259:        exp.Trunc: lambda self, e: self.func(
sqlglot/typing/mysql.py:48:def _annotate_truncate(self: TypeAnnotator, expression: exp.Trunc) -> exp.Expr:
sqlglot/typing/mysql.py:203:    exp.Trunc: {"annotator": _annotate_truncate},

[grep -nw TRUNC sqlglot/]
sqlglot/dialects/dialect.py:1972:    Builder for dialects with overloaded TRUNC (Oracle, Snowflake, etc).
sqlglot/dialects/dialect.py:2001:    return exp.Anonymous(this="TRUNC", expressions=args)
sqlglot/expressions/math.py:202:    _sql_names = ["TRUNC", "TRUNCATE"]
sqlglot/expressions/temporal.py:170:        # https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/ROUND-and-TRUNC-Date-Functions.html
sqlglot/generators/duckdb.py:2880:        return self.func("TRUNC", expression.this, decimals)
sqlglot/generators/hive.py:358:            "TRUNC", e.this, weekstart_unit_to_str(self, e)
sqlglot/generators/hive.py:490:    # Hive/Spark lack native numeric TRUNC. CAST to BIGINT truncates toward zero (not rounds).
sqlglot/generators/oracle.py:74:        exp.DateTrunc: lambda self, e: self.func("TRUNC", e.this, e.unit),
sqlglot/generators/spark2.py:159:                "TRUNC", e.this, weekstart_unit_to_str(self, e)
sqlglot/generators/sqlite.py:293:    # Note: SQLite's TRUNC always returns REAL (e.g., trunc(10.99) -> 10.0), not INTEGER.
sqlglot/generators/sqlite.py:296:    # so every use of TRUNC is affected. Modeling precisely would require exp.FloatTrunc.
sqlglot/generators/sqlite.py:299:        return self.func("TRUNC", expression.this)
sqlglot/parsers/exasol.py:86:        "TRUNC": build_trunc,
sqlglot/parsers/hive.py:126:        "TRUNC": exp.TimestampTrunc.from_arg_list,
sqlglot/parsers/oracle.py:37:        "TRUNC": lambda args, dialect: build_trunc(
sqlglot/parsers/snowflake.py:636:        "TRUNC": lambda args, dialect: build_trunc(
sqlglot/parsers/spark2.py:101:        "TRUNC": lambda args: exp.DateTrunc(unit=seq_get(args, 1), this=seq_get(args, 0)),

[grep -nw TRUNCATE sqlglot/]
sqlglot/expressions/math.py:202:    _sql_names = ["TRUNC", "TRUNCATE"]
sqlglot/generator.py:240:        exp.PartitionByTruncate: lambda self, e: self.func("TRUNCATE", e.this, e.expression),
sqlglot/generator.py:5423:        return f"TRUNCATE {target}{exists}{tables}{on_cluster}{identity}{option}{partition}"
sqlglot/generator.py:5998:        return f"TRUNCATE{filler} {with_count}"
sqlglot/generators/hive.py:389:        exp.PartitionByTruncate: lambda self, e: self.func("TRUNCATE", e.expression, e.this),
sqlglot/generators/mysql.py:216:        exp.Trunc: rename_func("TRUNCATE"),
sqlglot/generators/presto.py:426:        # Note: Presto's TRUNCATE always returns DOUBLE, even with decimals=0, whereas
sqlglot/generators/presto.py:431:        exp.Trunc: rename_func("TRUNCATE"),
sqlglot/generators/singlestore.py:1594:                self.unsupported(f"TRUNCATE TABLE does not support {arg_name}")
sqlglot/generators/singlestore.py:1597:            statements.append(f"TRUNCATE {self.sql(table)}")
sqlglot/parser.py:718:        TokenType.TRUNCATE,
sqlglot/parser.py:818:        TokenType.TRUNCATE,
sqlglot/parser.py:935:        TokenType.TRUNCATE,
sqlglot/parser.py:1181:        TokenType.TRUNCATE: lambda self: self._parse_truncate_table(),
sqlglot/parser.py:1478:        "TRUNCATE": lambda self: self._parse_partitioned_by_bucket_or_truncate(),
sqlglot/parser.py:1484:            # PARTITION BY (BUCKET(..) | TRUNCATE(..))
sqlglot/parser.py:1540:        "TRUNCATE",
sqlglot/parser.py:2831:                self.raise_error("Expected trigger event (INSERT, UPDATE, DELETE, TRUNCATE)")
sqlglot/parser.py:8348:                self._match_text_seq("TRUNCATE")
sqlglot/parser.py:9972:        # Not to be confused with TRUNCATE(number, decimals) function call
sqlglot/parser.py:9977:        # Clickhouse supports TRUNCATE DATABASE as well
sqlglot/parsers/exasol.py:87:        "TRUNCATE": build_trunc,
sqlglot/parsers/snowflake.py:639:        "TRUNCATE": lambda args, dialect: build_trunc(
sqlglot/tokenizer_core.py:434:    TRUNCATE = auto()
sqlglot/tokens.py:406:        "TRUNCATE": TokenType.TRUNCATE,

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
