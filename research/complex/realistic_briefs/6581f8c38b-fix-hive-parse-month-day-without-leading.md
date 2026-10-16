[sqlglot/dialects/dialect.py lines 215-220: _Dialect.__getitem__]
   215	    @classmethod
   216	    def __getitem__(cls, key: str) -> Type[Dialect]:
   217	        if key not in cls._classes:
   218	            cls._try_load(key)
   219	
   220	        return cls._classes[key]

[sqlglot/dialects/dialect.py lines 973-985: Dialect.format_time]
   973	    @classmethod
   974	    def format_time(cls, expression: str | exp.Expr | None) -> exp.Expr | None:
   975	        """Converts a time format in this dialect to its equivalent Python `strftime` format."""
   976	        if isinstance(expression, str):
   977	            return exp.Literal.string(
   978	                # the time formats are quoted
   979	                format_time(expression[1:-1], cls.TIME_MAPPING, cls.TIME_TRIE)
   980	            )
   981	
   982	        if expression and expression.is_string:
   983	            return exp.Literal.string(format_time(expression.this, cls.TIME_MAPPING, cls.TIME_TRIE))
   984	
   985	        return expression

[sqlglot/dialects/duckdb.py lines 42-55: DuckDB.<stmt@42>]
    42	    INVERSE_TIME_MAPPING = {
    43	        "%e": "%-d",  # BigQuery's space-padded day (%e) -> DuckDB's no-padding day (%-d)
    44	        "%:z": "%z",  # In DuckDB %z	can represent +/-HH:MM, +/-HHMM, or +/-HH.
    45	        "%-z": "%z",
    46	        "%f_zero": "%n",
    47	        "%f_one": "%n",
    48	        "%f_two": "%n",
    49	        "%f_three": "%g",
    50	        "%f_four": "%n",
    51	        "%f_five": "%n",
    52	        "%f_seven": "%n",
    53	        "%f_eight": "%n",
    54	        "%f_nine": "%n",
    55	    }

[sqlglot/dialects/hive.py lines 79-79: Hive.<stmt@79>]
    79	    DATE_FORMAT = "'yyyy-MM-dd'"

[sqlglot/dialects/hive.py lines 81-81: Hive.<stmt@81>]
    81	    TIME_FORMAT = "'yyyy-MM-dd HH:mm:ss'"

[sqlglot/dialects/spark.py lines 22-26: Spark.Tokenizer.<stmt@22>]
    22	        RAW_STRINGS = [
    23	            (prefix + q, q)
    24	            for q in t.cast(list[str], Spark2.Tokenizer.QUOTES)
    25	            for prefix in ("r", "R")
    26	        ]

[sqlglot/expressions/core.py lines 1754-1756: Literal.string]
  1754	    @classmethod
  1755	    def string(cls, string: object) -> Literal:
  1756	        return cls(this=str(string), is_string=True)

[sqlglot/generator.py lines 2983-3005: Generator.escape_str]
  2983	    def escape_str(
  2984	        self,
  2985	        text: str,
  2986	        escape_backslash: bool = True,
  2987	        delimiter: str | None = None,
  2988	        escaped_delimiter: str | None = None,
  2989	        is_byte_string: bool = False,
  2990	    ) -> str:
  2991	        if is_byte_string:
  2992	            supports_escape_sequences = self.dialect.BYTE_STRINGS_SUPPORT_ESCAPED_SEQUENCES
  2993	        else:
  2994	            supports_escape_sequences = self.dialect.STRINGS_SUPPORT_ESCAPED_SEQUENCES
  2995	
  2996	        if supports_escape_sequences:
  2997	            text = "".join(
  2998	                self.dialect.ESCAPED_SEQUENCES.get(ch, ch) if escape_backslash or ch != "\\" else ch
  2999	                for ch in text
  3000	            )
  3001	
  3002	        delimiter = delimiter or self.dialect.QUOTE_END
  3003	        escaped_delimiter = escaped_delimiter or self._escaped_quote_end
  3004	
  3005	        return self._replace_line_breaks(text).replace(delimiter, escaped_delimiter)

[sqlglot/generator.py lines 4640-4650: Generator.format_time]
  4640	    def format_time(
  4641	        self,
  4642	        expression: exp.Expr,
  4643	        inverse_time_mapping: dict[str, str] | None = None,
  4644	        inverse_time_trie: dict | None = None,
  4645	    ) -> str | None:
  4646	        return format_time(
  4647	            self.sql(expression, "format"),
  4648	            inverse_time_mapping or self.dialect.INVERSE_TIME_MAPPING,
  4649	            inverse_time_trie or self.dialect.INVERSE_TIME_TRIE,
  4650	        )

[sqlglot/generator.py lines 5351-5355: Generator._replace_line_breaks]
  5351	    def _replace_line_breaks(self, string: str) -> str:
  5352	        """We don't want to extra indent line breaks so we temporarily replace them with sentinels."""
  5353	        if self.pretty:
  5354	            return string.replace("\n", self.SENTINEL_LINE_BREAK)
  5355	        return string

[sqlglot/generators/duckdb.py lines 325-362: _date_delta_to_binary_interval_op]
   325	def _date_delta_to_binary_interval_op(
   326	    cast: bool = True,
   327	) -> t.Callable[[DuckDBGenerator, DATETIME_DELTA], str]:
   328	    """
   329	    DuckDB override to handle:
   330	    1. NANOSECOND operations (DuckDB doesn't support INTERVAL ... NANOSECOND)
   331	    2. Float/decimal interval values (DuckDB INTERVAL requires integers)
   332	    """
   333	    base_impl = date_delta_to_binary_interval_op(cast=cast)
   334	
   335	    def _duckdb_date_delta_sql(self: DuckDBGenerator, expression: DATETIME_DELTA) -> str:
   336	        unit = expression.unit
   337	        interval_value = expression.expression
   338	
   339	        # Handle NANOSECOND unit (DuckDB doesn't support INTERVAL ... NANOSECOND)
   340	        if _is_nanosecond_unit(unit):
   341	            if isinstance(interval_value, exp.Interval):
   342	                interval_value = interval_value.this
   343	
   344	            timestamp_ns = exp.cast(expression.this, exp.DType.TIMESTAMP_NS)
   345	
   346	            return self.sql(
   347	                exp.func(
   348	                    "MAKE_TIMESTAMP_NS",
   349	                    exp.Add(this=exp.func("EPOCH_NS", timestamp_ns), expression=interval_value),
   350	                )
   351	            )
   352	
   353	        # Handle float/decimal interval values as duckDB INTERVAL requires integer expressions
   354	        if not interval_value or isinstance(interval_value, exp.Interval):
   355	            return base_impl(self, expression)
   356	
   357	        if interval_value.is_type(*exp.DataType.REAL_TYPES):
   358	            expression.set("expression", exp.cast(exp.func("ROUND", interval_value), "INT"))
   359	
   360	        return base_impl(self, expression)
   361	
   362	    return _duckdb_date_delta_sql

[sqlglot/generators/hive.py lines 43-43: <stmt@43>]
    43	HIVE_TIME_FORMAT = "'yyyy-MM-dd HH:mm:ss'"

[sqlglot/generators/hive.py lines 44-44: <stmt@44>]
    44	HIVE_DATE_FORMAT = "'yyyy-MM-dd'"

[sqlglot/generators/mysql.py lines 74-84: date_add_sql]
    74	def date_add_sql(
    75	    kind: str,
    76	) -> t.Callable[[generator.Generator, exp.Expr], str]:
    77	    def func(self: generator.Generator, expression: exp.Expr) -> str:
    78	        return self.func(
    79	            f"DATE_{kind}",
    80	            expression.this,
    81	            exp.Interval(this=expression.expression, unit=unit_to_var(expression)),
    82	        )
    83	
    84	    return func

[sqlglot/generators/mysql.py lines 105-119: _remove_ts_or_ds_to_date]
   105	def _remove_ts_or_ds_to_date(
   106	    to_sql: t.Callable[[MySQLGenerator, exp.Expr], str] | None = None,
   107	    args: tuple[str, ...] = ("this",),
   108	) -> t.Callable[[MySQLGenerator, exp.Func], str]:
   109	    def func(self: MySQLGenerator, expression: exp.Func) -> str:
   110	        for arg_key in args:
   111	            arg = expression.args.get(arg_key)
   112	            if isinstance(arg, (exp.TsOrDsToDate, exp.TsOrDsToTimestamp)) and not arg.args.get(
   113	                "format"
   114	            ):
   115	                expression.set(arg_key, arg.this)
   116	
   117	        return to_sql(self, expression) if to_sql else self.function_fallback_sql(expression)
   118	
   119	    return func

[sqlglot/generators/spark.py lines 92-148: SparkGenerator.<stmt@92>]
    92	    TRANSFORMS = {
    93	        k: v
    94	        for k, v in {
    95	            **Spark2Generator.TRANSFORMS,
    96	            exp.ArrayConstructCompact: lambda self, e: self.func(
    97	                "ARRAY_COMPACT", self.func("ARRAY", *e.expressions)
    98	            ),
    99	            exp.ArrayInsert: lambda self, e: self.func(
   100	                "ARRAY_INSERT", e.this, e.args.get("position"), e.expression
   101	            ),
   102	            exp.ArrayAppend: array_append_sql("ARRAY_APPEND"),
   103	            exp.ArrayPrepend: array_append_sql("ARRAY_PREPEND"),
   104	            exp.BitwiseAndAgg: rename_func("BIT_AND"),
   105	            exp.BitwiseOrAgg: rename_func("BIT_OR"),
   106	            exp.BitwiseXorAgg: rename_func("BIT_XOR"),
   107	            exp.BitwiseCount: rename_func("BIT_COUNT"),
   108	            exp.Create: preprocess(
   109	                [
   110	                    remove_unique_constraints,
   111	                    lambda e: ctas_with_tmp_tables_to_create_tmp_view(
   112	                        e, temporary_storage_provider
   113	                    ),
   114	                    move_partitioned_by_to_schema_columns,
   115	                ]
   116	            ),
   117	            exp.CurrentVersion: rename_func("VERSION"),
   118	            exp.DateFromUnixDate: rename_func("DATE_FROM_UNIX_DATE"),
   119	            exp.DatetimeAdd: date_delta_to_binary_interval_op(cast=False),
   120	            exp.DatetimeSub: date_delta_to_binary_interval_op(cast=False),
   121	            exp.GroupConcat: _groupconcat_sql,
   122	            exp.EndsWith: rename_func("ENDSWITH"),
   123	            exp.JSONKeys: rename_func("JSON_OBJECT_KEYS"),
   124	            exp.PartitionedByProperty: lambda self, e: (
   125	                f"PARTITIONED BY {self.wrap(self.expressions(sqls=[_normalize_partition(e) for e in e.this.expressions], skip_first=True))}"
   126	            ),
   127	            exp.SafeAdd: rename_func("TRY_ADD"),
   128	            exp.SafeDivide: rename_func("TRY_DIVIDE"),
   129	            exp.SafeMultiply: rename_func("TRY_MULTIPLY"),
   130	            exp.SafeSubtract: rename_func("TRY_SUBTRACT"),
   131	            exp.StartsWith: rename_func("STARTSWITH"),
    ... (17 more lines)

[sqlglot/generators/spark2.py lines 51-55: _str_to_date]
    51	def _str_to_date(self: Spark2Generator, expression: exp.StrToDate) -> str:
    52	    time_format = self.format_time(expression)
    53	    if time_format == HIVE_DATE_FORMAT:
    54	        return self.func("TO_DATE", expression.this)
    55	    return self.func("TO_DATE", expression.this, time_format)

[sqlglot/parsers/duckdb.py lines 62-66: _show_parser]
    62	def _show_parser(*args: t.Any, **kwargs: t.Any) -> t.Callable[[DuckDBParser], exp.Show]:
    63	    def _parse(self: DuckDBParser) -> exp.Show:
    64	        return self._parse_show_duckdb(*args, **kwargs)
    65	
    66	    return _parse

[sqlglot/parsers/duckdb.py lines 325-332: DuckDBParser._parse_bracket]
   325	    def _parse_bracket(self, this: exp.Expr | None = None) -> exp.Expr | None:
   326	        bracket = super()._parse_bracket(this)
   327	
   328	        if self.dialect.version < (1, 2) and isinstance(bracket, exp.Bracket):
   329	            # https://duckdb.org/2025/02/05/announcing-duckdb-120.html#breaking-changes
   330	            bracket.set("returns_list_for_maps", True)
   331	
   332	        return bracket

[sqlglot/parsers/mysql.py lines 23-33: _has_time_specifier]
    23	def _has_time_specifier(date_format: str) -> bool:
    24	    i = 0
    25	    length = len(date_format)
    26	
    27	    while i < length:
    28	        if date_format[i] == "%":
    29	            i += 1
    30	            if i < length and date_format[i] in TIME_SPECIFIERS:
    31	                return True
    32	        i += 1
    33	    return False

[sqlglot/parsers/mysql.py lines 36-44: _str_to_date]
    36	def _str_to_date(args: list) -> exp.StrToDate | exp.StrToTime:
    37	    mysql_date_format = seq_get(args, 1)
    38	    date_format = Dialect["mysql"].format_time(mysql_date_format)
    39	    this = seq_get(args, 0)
    40	
    41	    if mysql_date_format and _has_time_specifier(mysql_date_format.name):
    42	        return exp.StrToTime(this=this, format=date_format)
    43	
    44	    return exp.StrToDate(this=this, format=date_format)

[sqlglot/parsers/mysql.py lines 47-51: _show_parser]
    47	def _show_parser(*args: t.Any, **kwargs: t.Any) -> t.Callable[[MySQLParser], exp.Show]:
    48	    def _parse(self: MySQLParser) -> exp.Show:
    49	        return self._parse_show_mysql(*args, **kwargs)
    50	
    51	    return _parse

[sqlglot/parsers/mysql.py lines 546-559: MySQLParser._parse_type]
   546	    def _parse_type(
   547	        self, parse_interval: bool = True, fallback_to_identifier: bool = False
   548	    ) -> exp.Expr | None:
   549	        # mysql binary is special and can work anywhere, even in order by operations
   550	        # it operates like a no paren func
   551	        if self._match(TokenType.BINARY, advance=False):
   552	            data_type = self._parse_types(check_func=True, allow_identifiers=False)
   553	
   554	            if isinstance(data_type, exp.DataType):
   555	                return self.expression(exp.Cast(this=self._parse_column(), to=data_type))
   556	
   557	        return super()._parse_type(
   558	            parse_interval=parse_interval, fallback_to_identifier=fallback_to_identifier
   559	        )

[sqlglot/parsers/spark.py lines 67-67: SparkParser.<stmt@67>]
    67	    SET_TRIE = new_trie(key.split(" ") for key in SET_PARSERS)

[sqlglot/time.py lines 10-62: format_time]
    10	def format_time(
    11	    string: str, mapping: dict[str, str], trie: dict[t.Any, t.Any] | None = None
    12	) -> str | None:
    13	    """
    14	    Converts a time string given a mapping.
    15	
    16	    Examples:
    17	        >>> format_time("%Y", {"%Y": "YYYY"})
    18	        'YYYY'
    19	
    20	        Args:
    21	            mapping: dictionary of time format to target time format.
    22	            trie: optional trie, can be passed in for performance.
    23	
    24	        Returns:
    25	            The converted time string.
    26	    """
    27	    if not string:
    28	        return None
    29	
    30	    start = 0
    31	    end = 1
    32	    size = len(string)
    33	    trie = trie or new_trie(mapping)
    34	    current = trie
    35	    chunks: list[str] = []
    36	    sym = None
    37	
    38	    while end <= size:
    39	        chars = string[start:end]
    40	        result, current = in_trie(current, chars[-1])
    41	
    42	        if result == TrieResult.FAILED:
    43	            if sym:
    44	                end -= 1
    45	                chars = sym
    46	                sym = None
    47	            else:
    48	                chars = chars[0]
    49	                end = start + 1
    ... (13 more lines)

[sqlglot/trie.py lines 44-82: in_trie]
    44	def in_trie(trie: dict, key: key) -> tuple[TrieResult, dict]:
    45	    """
    46	    Checks whether a key is in a trie.
    47	
    48	    Examples:
    49	        >>> in_trie(new_trie(["cat"]), "bob")
    50	        (<TrieResult.FAILED: 1>, {'c': {'a': {'t': {0: True}}}})
    51	
    52	        >>> in_trie(new_trie(["cat"]), "ca")
    53	        (<TrieResult.PREFIX: 2>, {'t': {0: True}})
    54	
    55	        >>> in_trie(new_trie(["cat"]), "cat")
    56	        (<TrieResult.EXISTS: 3>, {0: True})
    57	
    58	    Args:
    59	        trie: The trie to be searched.
    60	        key: The target key.
    61	
    62	    Returns:
    63	        A pair `(value, subtrie)`, where `subtrie` is the sub-trie we get at the point
    64	        where the search stops, and `value` is a TrieResult value that can be one of:
    65	
    66	        - TrieResult.FAILED: the search was unsuccessful
    67	        - TrieResult.PREFIX: `value` is a prefix of a keyword in `trie`
    68	        - TrieResult.EXISTS: `key` exists in `trie`
    69	    """
    70	    if not key:
    71	        return (TrieResult.FAILED, trie)
    72	
    73	    current = trie
    74	    for char in key:
    75	        if char not in current:
    76	            return (TrieResult.FAILED, current)
    77	        current = current[char]
    78	
    79	    if 0 in current:
    80	        return (TrieResult.EXISTS, current)
    81	
    82	    return (TrieResult.PREFIX, current)

[grep -nw STRPTIME sqlglot/]
sqlglot/generators/duckdb.py:1705:            f"CAST(STRPTIME(CAST({self.sql(e, 'this')} AS TEXT), {self.dialect.DATEINT_FORMAT}) AS DATE)"
sqlglot/generators/duckdb.py:1770:            "EPOCH", self.func("STRPTIME", e.this, self.format_time(e))
sqlglot/generators/duckdb.py:2759:        base_sql = self.func("STRPTIME", value, formatted_time)
sqlglot/generators/duckdb.py:2771:        function_name = "STRPTIME" if not expression.args.get("safe") else "TRY_STRPTIME"
sqlglot/generators/duckdb.py:2793:        return self.func("STRPTIME", value, formatted_time)
sqlglot/generators/duckdb.py:2799:                self.func("STRPTIME", expression.this, formatted_time),
sqlglot/generators/duckdb.py:2812:            func_name = "TRY_STRPTIME" if safe else "STRPTIME"
sqlglot/parsers/duckdb.py:180:        "STRPTIME": build_formatted_time(exp.StrToTime),

[grep -nw STR_TO_DATE sqlglot/]
sqlglot/generator.py:4100:        return self.func("STR_TO_DATE", expression.this, expression.args.get("format"))
sqlglot/generators/mysql.py:51:    return self.func("STR_TO_DATE", concat, f"'{date_format}'")
sqlglot/generators/mysql.py:57:    return self.func("STR_TO_DATE", expression.this, self.format_time(expression))
sqlglot/generators/singlestore.py:55:            "STR_TO_DATE",
sqlglot/generators/singlestore.py:115:            f"STR_TO_DATE({self.sql(e, 'this')}, {self.dialect.DATEINT_FORMAT})"
sqlglot/parsers/clickhouse.py:47:        return exp.Anonymous(this="STR_TO_DATE", expressions=args)
sqlglot/parsers/clickhouse.py:304:        "STR_TO_DATE": _build_str_to_date,
sqlglot/parsers/mysql.py:136:        "STR_TO_DATE": _str_to_date,
sqlglot/parsers/singlestore.py:29:        "STR_TO_DATE": build_formatted_time(exp.StrToDate, "mysql"),

[grep -nw Placeholder sqlglot/]
sqlglot/dialects/dialect.py:2007:    if isinstance(unit, exp.Placeholder) or type(unit) not in (exp.Var, exp.Literal):
sqlglot/dialects/dialect.py:2016:    if isinstance(unit, (exp.Var, exp.Placeholder, exp.WeekStart, exp.Column)):
sqlglot/expressions/builders.py:21:    Placeholder,
sqlglot/expressions/builders.py:868:        if isinstance(node, Placeholder):
sqlglot/expressions/core.py:1841:class Placeholder(Expression, Condition):
sqlglot/generator.py:3422:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/generators/clickhouse.py:574:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/generators/postgres.py:541:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/generators/spark.py:175:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/lineage.py:474:                    col_expr = col_source or exp.Placeholder()
sqlglot/lineage.py:488:            col_expr = col_source or exp.Placeholder()
sqlglot/parser.py:1197:        TokenType.PLACEHOLDER: lambda self: self.expression(exp.Placeholder()),
sqlglot/parser.py:1200:            self.expression(exp.Placeholder(this=self._prev.text))
sqlglot/parsers/clickhouse.py:579:        return self.expression(exp.Placeholder(this=this, kind=kind))
sqlglot/parsers/duckdb.py:208:            self.expression(exp.Placeholder(this=self._prev.text))
sqlglot/parsers/postgres.py:96:        TokenType.PLACEHOLDER: lambda self: self.expression(exp.Placeholder(jdbc=True)),
sqlglot/parsers/postgres.py:301:        return self.expression(exp.Placeholder(this=this))
sqlglot/parsers/spark.py:117:        return self.expression(exp.Placeholder(this=this, widget=True))

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
