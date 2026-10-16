[sqlglot/dialects/dialect.py lines 233-238: _Dialect.__getitem__]
   233	    @classmethod
   234	    def __getitem__(cls, key: str) -> Type[Dialect]:
   235	        if key not in cls._classes:
   236	            cls._try_load(key)
   237	
   238	        return cls._classes[key]

[sqlglot/dialects/dialect.py lines 1001-1013: Dialect.format_time]
  1001	    @classmethod
  1002	    def format_time(cls, expression: str | exp.Expr | None) -> exp.Expr | None:
  1003	        """Converts a time format in this dialect to its equivalent Python `strftime` format."""
  1004	        if isinstance(expression, str):
  1005	            return exp.Literal.string(
  1006	                # the time formats are quoted
  1007	                format_time(expression[1:-1], cls.TIME_MAPPING, cls.TIME_TRIE)
  1008	            )
  1009	
  1010	        if expression and expression.is_string:
  1011	            return exp.Literal.string(format_time(expression.this, cls.TIME_MAPPING, cls.TIME_TRIE))
  1012	
  1013	        return expression

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

[sqlglot/dialects/hive.py lines 46-78: Hive.<stmt@46>]
    46	    TIME_MAPPING = {
    47	        "y": "%Y",
    48	        "Y": "%Y",
    49	        "YYYY": "%Y",
    50	        "yyyy": "%Y",
    51	        "YY": "%y",
    52	        "yy": "%y",
    53	        "MMMM": "%B",
    54	        "MMM": "%b",
    55	        # Hive 4.0+ parses MM/dd strictly (java.time.DateTimeFormatter, see HIVE-25458/HIVE-25576)
    56	        "MM": "%mstrict",
    57	        "M": "%-m",
    58	        "dd": "%dstrict",
    59	        "d": "%-d",
    60	        "HH": "%H",
    61	        "H": "%-H",
    62	        "hh": "%I",
    63	        "h": "%-I",
    64	        "mm": "%M",
    65	        "m": "%-M",
    66	        "ss": "%S",
    67	        "s": "%-S",
    68	        "SSSSSS": "%f",
    69	        "a": "%p",
    70	        "DD": "%j",
    71	        "D": "%-j",
    72	        "E": "%a",
    73	        "EE": "%a",
    74	        "EEE": "%a",
    75	        "EEEE": "%A",
    76	        "z": "%Z",
    77	        "Z": "%z",
    78	    }

[sqlglot/dialects/hive.py lines 80-80: Hive.<stmt@80>]
    80	    DATE_FORMAT = "'yyyy-MM-dd'"

[sqlglot/dialects/hive.py lines 82-82: Hive.<stmt@82>]
    82	    TIME_FORMAT = "'yyyy-MM-dd HH:mm:ss'"

[sqlglot/expressions/core.py lines 1754-1756: Literal.string]
  1754	    @classmethod
  1755	    def string(cls, string: object) -> Literal:
  1756	        return cls(this=str(string), is_string=True)

[sqlglot/generator.py lines 2979-3001: Generator.escape_str]
  2979	    def escape_str(
  2980	        self,
  2981	        text: str,
  2982	        escape_backslash: bool = True,
  2983	        delimiter: str | None = None,
  2984	        escaped_delimiter: str | None = None,
  2985	        is_byte_string: bool = False,
  2986	    ) -> str:
  2987	        if is_byte_string:
  2988	            supports_escape_sequences = self.dialect.BYTE_STRINGS_SUPPORT_ESCAPED_SEQUENCES
  2989	        else:
  2990	            supports_escape_sequences = self.dialect.STRINGS_SUPPORT_ESCAPED_SEQUENCES
  2991	
  2992	        if supports_escape_sequences:
  2993	            text = "".join(
  2994	                self.dialect.ESCAPED_SEQUENCES.get(ch, ch) if escape_backslash or ch != "\\" else ch
  2995	                for ch in text
  2996	            )
  2997	
  2998	        delimiter = delimiter or self.dialect.QUOTE_END
  2999	        escaped_delimiter = escaped_delimiter or self._escaped_quote_end
  3000	
  3001	        return self._replace_line_breaks(text).replace(delimiter, escaped_delimiter)

[sqlglot/generator.py lines 5351-5355: Generator._replace_line_breaks]
  5351	    def _replace_line_breaks(self, string: str) -> str:
  5352	        """We don't want to extra indent line breaks so we temporarily replace them with sentinels."""
  5353	        if self.pretty:
  5354	            return string.replace("\n", self.SENTINEL_LINE_BREAK)
  5355	        return string

[sqlglot/generators/duckdb.py lines 315-352: _date_delta_to_binary_interval_op]
   315	def _date_delta_to_binary_interval_op(
   316	    cast: bool = True,
   317	) -> t.Callable[[DuckDBGenerator, DATETIME_DELTA], str]:
   318	    """
   319	    DuckDB override to handle:
   320	    1. NANOSECOND operations (DuckDB doesn't support INTERVAL ... NANOSECOND)
   321	    2. Float/decimal interval values (DuckDB INTERVAL requires integers)
   322	    """
   323	    base_impl = date_delta_to_binary_interval_op(cast=cast)
   324	
   325	    def _duckdb_date_delta_sql(self: DuckDBGenerator, expression: DATETIME_DELTA) -> str:
   326	        unit = expression.unit
   327	        interval_value = expression.expression
   328	
   329	        # Handle NANOSECOND unit (DuckDB doesn't support INTERVAL ... NANOSECOND)
   330	        if _is_nanosecond_unit(unit):
   331	            if isinstance(interval_value, exp.Interval):
   332	                interval_value = interval_value.this
   333	
   334	            timestamp_ns = exp.cast(expression.this, exp.DType.TIMESTAMP_NS)
   335	
   336	            return self.sql(
   337	                exp.func(
   338	                    "MAKE_TIMESTAMP_NS",
   339	                    exp.Add(this=exp.func("EPOCH_NS", timestamp_ns), expression=interval_value),
   340	                )
   341	            )
   342	
   343	        # Handle float/decimal interval values as duckDB INTERVAL requires integer expressions
   344	        if not interval_value or isinstance(interval_value, exp.Interval):
   345	            return base_impl(self, expression)
   346	
   347	        if interval_value.is_type(*exp.DataType.REAL_TYPES):
   348	            expression.set("expression", exp.cast(exp.func("ROUND", interval_value), "INT"))
   349	
   350	        return base_impl(self, expression)
   351	
   352	    return _duckdb_date_delta_sql

[sqlglot/generators/hive.py lines 44-44: <stmt@44>]
    44	HIVE_TIME_FORMAT = "'yyyy-MM-dd HH:mm:ss'"

[sqlglot/generators/hive.py lines 49-49: <stmt@49>]
    49	HIVE_NON_PADDED_TIME_FORMATS = ("'yyyy-M-d HH:mm:ss'", "'yyyy-M-d'")

[sqlglot/generators/hive.py lines 59-81: _lenient_parse_format]
    59	def _lenient_parse_format(fmt: str) -> str:
    60	    """
    61	    Changes the lax %m/%d in a canonical format to the non-padded %-m/%-d, which java.time
    62	    parses with or without a leading zero. This is only safe for delimited specifiers, because
    63	    adjacent fields parse greedily, so e.g. 'yyyyMd' (from '%Y%m%d') can't even parse '20200101'.
    64	
    65	    The format is decomposed into specifiers (`formats`) and the interleaved literal text (`parts`).
    66	    Specifier i sits between parts[i] and parts[i + 1]. A %m/%d is changed only when its neighbors
    67	    don't touch a digit run, i.e., neither side is another specifier or a literal digit. At the end,
    68	    the pieces are zipped back together to produce the rewritten canonical format.
    69	    """
    70	    parts = CANONICAL_TIME_FORMAT.split(fmt)
    71	    formats = CANONICAL_TIME_FORMAT.findall(fmt)
    72	
    73	    for i, fmt_ in enumerate(formats):
    74	        if fmt_ in LAX_TO_NON_PADDED_FORMATS:
    75	            left, right = parts[i], parts[i + 1]
    76	            left_adjacent = (not left and i > 0) or (left and left[-1].isdigit())
    77	            right_adjacent = (not right and i < len(formats) - 1) or (right and right[0].isdigit())
    78	            if not left_adjacent and not right_adjacent:
    79	                formats[i] = LAX_TO_NON_PADDED_FORMATS[fmt_]
    80	
    81	    return "".join(part + fmt_ for part, fmt_ in zip(parts, formats + [""]))

[sqlglot/generators/hive.py lines 397-418: HiveGenerator.format_time]
   397	    def format_time(
   398	        self,
   399	        expression: exp.Expr,
   400	        inverse_time_mapping: dict[str, str] | None = None,
   401	        inverse_time_trie: dict | None = None,
   402	    ) -> str | None:
   403	        # Inferred property because this method is reused by other dialects under Hive
   404	        is_dialect_strict = self.dialect.TIME_MAPPING.get("MM") == "%mstrict"
   405	
   406	        if (
   407	            is_dialect_strict
   408	            and inverse_time_mapping is None
   409	            and isinstance(expression, PARSE_TIME_EXPRESSIONS)
   410	        ):
   411	            # Render a lenient %m/%d non-padded (M/d) so single-digit sources stay parseable
   412	            return format_time(
   413	                _lenient_parse_format(self.sql(expression, "format")),
   414	                self.dialect.INVERSE_TIME_MAPPING,
   415	                self.dialect.INVERSE_TIME_TRIE,
   416	            )
   417	
   418	        return super().format_time(expression, inverse_time_mapping, inverse_time_trie)

[sqlglot/parsers/duckdb.py lines 108-190: DuckDBParser.<stmt@108>]
   108	    FUNCTIONS = {
   109	        **{k: v for k, v in parser.Parser.FUNCTIONS.items() if k not in ("DATE_SUB", "GLOB")},
   110	        "ANY_VALUE": lambda args: exp.IgnoreNulls(this=exp.AnyValue.from_arg_list(args)),
   111	        "ARRAY_PREPEND": _build_array_prepend,
   112	        "ARRAY_REVERSE_SORT": _build_sort_array_desc,
   113	        "ARRAY_INTERSECT": lambda args: exp.ArrayIntersect(expressions=args),
   114	        "ARRAY_SORT": exp.SortArray.from_arg_list,
   115	        "BIT_AND": exp.BitwiseAndAgg.from_arg_list,
   116	        "BIT_OR": exp.BitwiseOrAgg.from_arg_list,
   117	        "BIT_XOR": exp.BitwiseXorAgg.from_arg_list,
   118	        "CURRENT_LOCALTIMESTAMP": exp.Localtimestamp.from_arg_list,
   119	        "DATEDIFF": _build_date_diff,
   120	        "DATE_DIFF": _build_date_diff,
   121	        "DATE_TRUNC": date_trunc_to_time,
   122	        "DATETRUNC": date_trunc_to_time,
   123	        "DECODE": lambda args: exp.Decode(
   124	            this=seq_get(args, 0), charset=exp.Literal.string("utf-8")
   125	        ),
   126	        "EDITDIST3": exp.Levenshtein.from_arg_list,
   127	        "ENCODE": lambda args: exp.Encode(
   128	            this=seq_get(args, 0), charset=exp.Literal.string("utf-8")
   129	        ),
   130	        "EPOCH": exp.TimeToUnix.from_arg_list,
   131	        "EPOCH_MS": lambda args: exp.UnixToTime(this=seq_get(args, 0), scale=exp.UnixToTime.MILLIS),
   132	        "GENERATE_SERIES": _build_generate_series(),
   133	        "GET_CURRENT_TIME": exp.CurrentTime.from_arg_list,
   134	        "GET_BIT": lambda args: exp.Getbit(
   135	            this=seq_get(args, 0), expression=seq_get(args, 1), zero_is_msb=True
   136	        ),
   137	        "JARO_WINKLER_SIMILARITY": exp.JarowinklerSimilarity.from_arg_list,
   138	        "JSON": exp.ParseJSON.from_arg_list,
   139	        "JSON_ARRAY": lambda args: exp.JSONArray(expressions=args),
   140	        "JSON_EXTRACT_PATH": parser.build_extract_json_with_path(exp.JSONExtract),
   141	        "JSON_EXTRACT_STRING": parser.build_extract_json_with_path(exp.JSONExtractScalar),
   142	        "LIST": exp.ArrayAgg.from_arg_list,
   143	        "LIST_DISTINCT": exp.ArrayDistinct.from_arg_list,
   144	        "LIST_APPEND": exp.ArrayAppend.from_arg_list,
   145	        "LIST_CONCAT": parser.build_array_concat,
   146	        "LIST_CONTAINS": exp.ArrayContains.from_arg_list,
   147	        "LIST_COSINE_DISTANCE": exp.CosineDistance.from_arg_list,
    ... (43 more lines)

[sqlglot/parsers/duckdb.py lines 329-336: DuckDBParser._parse_bracket]
   329	    def _parse_bracket(self, this: exp.Expr | None = None) -> exp.Expr | None:
   330	        bracket = super()._parse_bracket(this)
   331	
   332	        if self.dialect.version < (1, 2) and isinstance(bracket, exp.Bracket):
   333	            # https://duckdb.org/2025/02/05/announcing-duckdb-120.html#breaking-changes
   334	            bracket.set("returns_list_for_maps", True)
   335	
   336	        return bracket

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

[grep -nw STR_TO_TIME sqlglot/]
sqlglot/generator.py:4096:        return self.func("STR_TO_TIME", expression.this, expression.args.get("format"))

[grep -nw STRPTIME sqlglot/]
sqlglot/generators/duckdb.py:1669:            f"CAST(STRPTIME(CAST({self.sql(e, 'this')} AS TEXT), {self.dialect.DATEINT_FORMAT}) AS DATE)"
sqlglot/generators/duckdb.py:1734:            "EPOCH", self.func("STRPTIME", e.this, self.format_time(e))
sqlglot/generators/duckdb.py:2723:        base_sql = self.func("STRPTIME", value, formatted_time)
sqlglot/generators/duckdb.py:2735:        function_name = "STRPTIME" if not expression.args.get("safe") else "TRY_STRPTIME"
sqlglot/generators/duckdb.py:2757:        return self.func("STRPTIME", value, formatted_time)
sqlglot/generators/duckdb.py:2763:                self.func("STRPTIME", expression.this, formatted_time),
sqlglot/generators/duckdb.py:2776:            func_name = "TRY_STRPTIME" if safe else "STRPTIME"
sqlglot/parsers/duckdb.py:180:        "STRPTIME": build_formatted_time(exp.StrToTime),

[grep -nw STR_TO_DATE sqlglot/]
sqlglot/generator.py:4100:        return self.func("STR_TO_DATE", expression.this, expression.args.get("format"))
sqlglot/generators/mysql.py:51:    return self.func("STR_TO_DATE", concat, f"'{date_format}'")
sqlglot/generators/mysql.py:57:    return self.func("STR_TO_DATE", expression.this, self.format_time(expression))
sqlglot/generators/singlestore.py:55:            "STR_TO_DATE",
sqlglot/generators/singlestore.py:115:            f"STR_TO_DATE({self.sql(e, 'this')}, {self.dialect.DATEINT_FORMAT})"
sqlglot/parsers/clickhouse.py:47:        return exp.Anonymous(this="STR_TO_DATE", expressions=args)
sqlglot/parsers/clickhouse.py:305:        "STR_TO_DATE": _build_str_to_date,
sqlglot/parsers/mysql.py:139:        "STR_TO_DATE": _str_to_date,
sqlglot/parsers/singlestore.py:29:        "STR_TO_DATE": build_formatted_time(exp.StrToDate, "mysql"),

[grep -nw Placeholder sqlglot/]
sqlglot/dialects/dialect.py:2035:    if isinstance(unit, exp.Placeholder) or type(unit) not in (exp.Var, exp.Literal):
sqlglot/dialects/dialect.py:2044:    if isinstance(unit, (exp.Var, exp.Placeholder, exp.WeekStart, exp.Column)):
sqlglot/expressions/builders.py:21:    Placeholder,
sqlglot/expressions/builders.py:868:        if isinstance(node, Placeholder):
sqlglot/expressions/core.py:1841:class Placeholder(Expression, Condition):
sqlglot/generator.py:3418:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/generators/clickhouse.py:574:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/generators/postgres.py:547:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/generators/spark.py:174:    def placeholder_sql(self, expression: exp.Placeholder) -> str:
sqlglot/lineage.py:474:                    col_expr = col_source or exp.Placeholder()
sqlglot/lineage.py:488:            col_expr = col_source or exp.Placeholder()
sqlglot/parser.py:1198:        TokenType.PLACEHOLDER: lambda self: self.expression(exp.Placeholder()),
sqlglot/parser.py:1201:            self.expression(exp.Placeholder(this=self._prev.text))
sqlglot/parsers/clickhouse.py:580:        return self.expression(exp.Placeholder(this=this, kind=kind))
sqlglot/parsers/duckdb.py:212:            self.expression(exp.Placeholder(this=self._prev.text))
sqlglot/parsers/postgres.py:96:        TokenType.PLACEHOLDER: lambda self: self.expression(exp.Placeholder(jdbc=True)),
sqlglot/parsers/postgres.py:301:        return self.expression(exp.Placeholder(this=this))
sqlglot/parsers/spark.py:117:        return self.expression(exp.Placeholder(this=this, widget=True))

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
