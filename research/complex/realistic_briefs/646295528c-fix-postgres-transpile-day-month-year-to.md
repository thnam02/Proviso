[sqlglot/dialects/dialect.py lines 1996-2008: date_delta_sql]
  1996	def date_delta_sql(name: str, cast: bool = False) -> t.Callable[[Generator, DATE_ADD_OR_DIFF], str]:
  1997	    def _delta_sql(self: Generator, expression: DATE_ADD_OR_DIFF) -> str:
  1998	        if cast and isinstance(expression, exp.TsOrDsAdd):
  1999	            expression = ts_or_ds_add_cast(expression)
  2000	
  2001	        return self.func(
  2002	            name,
  2003	            unit_to_var(expression),
  2004	            expression.expression,
  2005	            expression.this,
  2006	        )
  2007	
  2008	    return _delta_sql

[sqlglot/dialects/postgres.py lines 30-69: Postgres.<stmt@30>]
    30	    TIME_MAPPING = {
    31	        "d": "%u",  # 1-based day of week
    32	        "D": "%u",  # 1-based day of week
    33	        "dd": "%d",  # day of month
    34	        "DD": "%d",  # day of month
    35	        "ddd": "%j",  # zero padded day of year
    36	        "DDD": "%j",  # zero padded day of year
    37	        "FMDD": "%-d",  # - is no leading zero for Python; same for FM in postgres
    38	        "FMDDD": "%-j",  # day of year
    39	        "FMHH12": "%-I",  # 9
    40	        "FMHH24": "%-H",  # 9
    41	        "FMMI": "%-M",  # Minute
    42	        "FMMM": "%-m",  # 1
    43	        "FMSS": "%-S",  # Second
    44	        "HH12": "%I",  # 09
    45	        "HH24": "%H",  # 09
    46	        "mi": "%M",  # zero padded minute
    47	        "MI": "%M",  # zero padded minute
    48	        "mm": "%m",  # 01
    49	        "MM": "%m",  # 01
    50	        "OF": "%z",  # utc offset
    51	        "ss": "%S",  # zero padded second
    52	        "SS": "%S",  # zero padded second
    53	        "TMDay": "%A",  # TM is locale dependent
    54	        "TMDy": "%a",
    55	        "TMMon": "%b",  # Sep
    56	        "TMMonth": "%B",  # September
    57	        "day": "%Aenlower",  # tuesday
    58	        "dy": "%aenlower",  # tue
    59	        "TZ": "%Z",  # uppercase timezone name
    60	        "US": "%f",  # zero padded microsecond
    61	        "ww": "%U",  # 1-based week of year
    62	        "WW": "%U",  # 1-based week of year
    63	        "yy": "%y",  # 15
    64	        "YY": "%y",  # 15
    65	        "yyy": "%Ythree",  # 015
    66	        "YYY": "%Ythree",  # 015
    67	        "yyyy": "%Y",  # 2015
    68	        "YYYY": "%Y",  # 2015
    69	    }

[sqlglot/expressions/core.py lines 1682-1686: Func.sql_name]
  1682	    @classmethod
  1683	    def sql_name(cls) -> str:
  1684	        sql_names = cls.sql_names()
  1685	        assert sql_names, f"Expected non-empty 'sql_names' for Func: {cls.__name__}."
  1686	        return sql_names[0]

[sqlglot/generator.py lines 3307-3310: Generator.after_limit_modifiers]
  3307	    def after_limit_modifiers(self, expression: exp.Expr) -> list[str]:
  3308	        locks = self.expressions(expression, key="locks", sep=" ")
  3309	        locks = f" {locks}" if locks else ""
  3310	        return [locks, self.sql(expression, "sample")]

[sqlglot/generator.py lines 4617-4634: Generator.function_fallback_sql]
  4617	    def function_fallback_sql(self, expression: exp.Func) -> str:
  4618	        args = []
  4619	
  4620	        for key in expression.arg_types:
  4621	            arg_value = expression.args.get(key)
  4622	
  4623	            if isinstance(arg_value, list):
  4624	                for value in arg_value:
  4625	                    args.append(value)
  4626	            elif arg_value is not None:
  4627	                args.append(arg_value)
  4628	
  4629	        if self.dialect.PRESERVE_ORIGINAL_NAMES:
  4630	            name = expression.meta_get("name") or expression.sql_name()
  4631	        else:
  4632	            name = expression.sql_name()
  4633	
  4634	        return self.func(name, *args)

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

[sqlglot/generators/postgres.py lines 80-110: _date_diff_sql]
    80	def _date_diff_sql(self: PostgresGenerator, expression: exp.DateDiff | exp.TsOrDsDiff) -> str:
    81	    unit = expression.text("unit").upper() or "DAY"
    82	
    83	    # Dialects like MySQL count crossed day boundaries, which maps to DATE subtraction
    84	    if unit == "DAY" and expression.args.get("date_part_boundary"):
    85	        this = exp.cast(expression.this, exp.DType.DATE)
    86	        expr = exp.cast(expression.expression, exp.DType.DATE)
    87	        return self.sql(exp.paren(this - expr))
    88	
    89	    factor = DATE_DIFF_FACTOR.get(unit)
    90	
    91	    end = f"CAST({self.sql(expression, 'this')} AS TIMESTAMP)"
    92	    start = f"CAST({self.sql(expression, 'expression')} AS TIMESTAMP)"
    93	
    94	    if factor is not None:
    95	        return f"CAST(EXTRACT(epoch FROM {end} - {start}){factor} AS BIGINT)"
    96	
    97	    age = f"AGE({end}, {start})"
    98	
    99	    if unit == "WEEK":
   100	        unit = f"EXTRACT(days FROM ({end} - {start})) / 7"
   101	    elif unit == "MONTH":
   102	        unit = f"EXTRACT(year FROM {age}) * 12 + EXTRACT(month FROM {age})"
   103	    elif unit == "QUARTER":
   104	        unit = f"EXTRACT(year FROM {age}) * 4 + EXTRACT(month FROM {age}) / 3"
   105	    elif unit == "YEAR":
   106	        unit = f"EXTRACT(year FROM {age})"
   107	    else:
   108	        unit = age
   109	
   110	    return f"CAST({unit} AS BIGINT)"

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

[sqlglot/generators/postgres.py lines 291-398: PostgresGenerator.<stmt@291>]
   291	    TRANSFORMS = {
   292	        **{
   293	            k: v
   294	            for k, v in generator.Generator.TRANSFORMS.items()
   295	            if k != exp.CommentColumnConstraint
   296	        },
   297	        exp.AnyValue: _versioned_anyvalue_sql,
   298	        exp.ArrayConcat: array_concat_sql("ARRAY_CAT"),
   299	        exp.ArrayFilter: filter_array_using_unnest,
   300	        exp.ArrayAppend: array_append_sql("ARRAY_APPEND"),
   301	        exp.ArrayPrepend: array_append_sql("ARRAY_PREPEND", swap_params=True),
   302	        exp.BitwiseAndAgg: rename_func("BIT_AND"),
   303	        exp.BitwiseOrAgg: rename_func("BIT_OR"),
   304	        exp.BitwiseXor: lambda self, e: self.binary(e, "#"),
   305	        exp.BitwiseXorAgg: rename_func("BIT_XOR"),
   306	        exp.ColumnDef: transforms.preprocess([_auto_increment_to_serial, _serial_to_generated]),
   307	        exp.CurrentDate: no_paren_current_date_sql,
   308	        exp.CurrentTimestamp: lambda *_: "CURRENT_TIMESTAMP",
   309	        exp.CurrentUser: lambda *_: "CURRENT_USER",
   310	        exp.CurrentVersion: rename_func("VERSION"),
   311	        exp.DateAdd: _date_add_sql("+"),
   312	        exp.DateDiff: _date_diff_sql,
   313	        exp.DateStrToDate: datestrtodate_sql,
   314	        exp.DateSub: _date_add_sql("-"),
   315	        exp.Explode: rename_func("UNNEST"),
   316	        exp.ExplodingGenerateSeries: rename_func("GENERATE_SERIES"),
   317	        exp.GenerateSeries: generate_series_sql("GENERATE_SERIES"),
   318	        exp.Getbit: getbit_sql,
   319	        exp.GroupConcat: lambda self, e: groupconcat_sql(
   320	            self, e, func_name="STRING_AGG", within_group=False
   321	        ),
   322	        exp.IntDiv: rename_func("DIV"),
   323	        exp.JSONArrayAgg: lambda self, e: self.func(
   324	            "JSON_AGG",
   325	            self.sql(e, "this"),
   326	            suffix=f"{self.sql(e, 'order')})",
   327	        ),
   328	        exp.JSONExtract: _json_extract_sql("JSON_EXTRACT_PATH", "->"),
   329	        exp.JSONExtractScalar: _json_extract_sql("JSON_EXTRACT_PATH_TEXT", "->>"),
   330	        exp.JSONBExtract: lambda self, e: self.binary(e, "#>"),
    ... (68 more lines)

[sqlglot/generators/tsql.py lines 190-251: TSQLGenerator.<stmt@190>]
   190	    TRANSFORMS = {
   191	        **{k: v for k, v in generator.Generator.TRANSFORMS.items() if k != exp.ReturnsProperty},
   192	        exp.AnyValue: any_value_to_max_sql,
   193	        exp.Atan2: rename_func("ATN2"),
   194	        exp.ArrayToString: rename_func("STRING_AGG"),
   195	        exp.AutoIncrementColumnConstraint: lambda *_: "IDENTITY",
   196	        exp.Ceil: rename_func("CEILING"),
   197	        exp.Chr: rename_func("CHAR"),
   198	        exp.DateAdd: date_delta_sql("DATEADD"),
   199	        exp.CTE: transforms.preprocess([qualify_derived_table_outputs]),
   200	        exp.CurrentDate: rename_func("GETDATE"),
   201	        exp.CurrentTimestamp: rename_func("GETDATE"),
   202	        exp.CurrentTimestampLTZ: rename_func("SYSDATETIMEOFFSET"),
   203	        exp.DateStrToDate: datestrtodate_sql,
   204	        exp.GeneratedAsIdentityColumnConstraint: generatedasidentitycolumnconstraint_sql,
   205	        exp.GroupConcat: _string_agg_sql,
   206	        exp.If: rename_func("IIF"),
   207	        exp.JSONExtract: _json_extract_sql,
   208	        exp.JSONExtractScalar: _json_extract_sql,
   209	        exp.LastDay: lambda self, e: self.func("EOMONTH", e.this),
   210	        exp.Ln: rename_func("LOG"),
   211	        exp.Max: max_or_greatest,
   212	        exp.MD5: lambda self, e: self.func("HASHBYTES", exp.Literal.string("MD5"), e.this),
   213	        exp.Min: min_or_least,
   214	        exp.NumberToStr: _format_sql,
   215	        exp.Repeat: rename_func("REPLICATE"),
   216	        exp.CurrentSchema: rename_func("SCHEMA_NAME"),
   217	        exp.Select: transforms.preprocess(
   218	            [
   219	                transforms.eliminate_distinct_on,
   220	                transforms.eliminate_semi_and_anti_joins,
   221	                transforms.eliminate_qualify,
   222	                transforms.unnest_generate_date_array_using_recursive_cte,
   223	            ]
   224	        ),
   225	        exp.Stddev: rename_func("STDEV"),
   226	        exp.StrPosition: lambda self, e: strposition_sql(
   227	            self, e, func_name="CHARINDEX", supports_position=True
   228	        ),
   229	        exp.Subquery: transforms.preprocess([qualify_derived_table_outputs]),
    ... (22 more lines)

[sqlglot/parsers/postgres.py lines 89-92: PostgresParser.<stmt@89>]
    89	    PROPERTY_PARSERS = {
    90	        **{k: v for k, v in parser.Parser.PROPERTY_PARSERS.items() if k != "INPUT"},
    91	        "SET": lambda self: self.expression(exp.SetConfigProperty(this=self._parse_set())),
    92	    }

[sqlglot/parsers/tsql.py lines 31-47: <stmt@31>]
    31	DATE_DELTA_INTERVAL = {
    32	    "year": "year",
    33	    "yyyy": "year",
    34	    "yy": "year",
    35	    "quarter": "quarter",
    36	    "qq": "quarter",
    37	    "q": "quarter",
    38	    "month": "month",
    39	    "mm": "month",
    40	    "m": "month",
    41	    "week": "week",
    42	    "ww": "week",
    43	    "wk": "week",
    44	    "day": "day",
    45	    "dd": "day",
    46	    "d": "day",
    47	}

[sqlglot/parsers/tsql.py lines 127-152: _build_formatted_time]
   127	def _build_formatted_time(
   128	    exp_class: type[E], full_format_mapping: bool | None = None
   129	) -> t.Callable[[list], E]:
   130	    def _builder(args: list) -> E:
   131	        fmt = seq_get(args, 0)
   132	        if isinstance(fmt, exp.Expr):
   133	            from sqlglot.dialects.tsql import TSQL
   134	
   135	            fmt = exp.Literal.string(
   136	                format_time(
   137	                    fmt.name.lower(),
   138	                    (
   139	                        {**TSQL.TIME_MAPPING, **FULL_FORMAT_TIME_MAPPING}
   140	                        if full_format_mapping
   141	                        else TSQL.TIME_MAPPING
   142	                    ),
   143	                )
   144	            )
   145	
   146	        this = seq_get(args, 1)
   147	        if isinstance(this, exp.Expr):
   148	            this = exp.cast(this, exp.DType.DATETIME2)
   149	
   150	        return exp_class(this=this, format=fmt)
   151	
   152	    return _builder

[sqlglot/parsers/tsql.py lines 208-236: _build_date_delta]
   208	def _build_date_delta(
   209	    exp_class: type[E], unit_mapping: dict[str, str] | None = None, big_int: bool = False
   210	) -> t.Callable[[list], E]:
   211	    def _builder(args: list) -> E:
   212	        unit = seq_get(args, 0)
   213	        if unit and unit_mapping:
   214	            unit = exp.var(unit_mapping.get(unit.name.lower(), unit.name))
   215	
   216	        start_date = seq_get(args, 1)
   217	        if start_date and start_date.is_number:
   218	            # Numeric types are valid DATETIME values
   219	            if start_date.is_int:
   220	                adds = DEFAULT_START_DATE + datetime.timedelta(days=start_date.to_py())
   221	                start_date = exp.Literal.string(adds.strftime("%F"))
   222	            else:
   223	                # We currently don't handle float values, i.e. they're not converted to equivalent DATETIMEs.
   224	                # This is not a problem when generating T-SQL code, it is when transpiling to other dialects.
   225	                return exp_class(
   226	                    this=seq_get(args, 2), expression=start_date, unit=unit, big_int=big_int
   227	                )
   228	
   229	        return exp_class(
   230	            this=exp.TimeStrToTime(this=seq_get(args, 2)),
   231	            expression=exp.TimeStrToTime(this=start_date),
   232	            unit=unit,
   233	            big_int=big_int,
   234	        )
   235	
   236	    return _builder

[sqlglot/parsers/tsql.py lines 263-280: _build_with_arg_as_text]
   263	def _build_with_arg_as_text(
   264	    klass: type[exp.Expr],
   265	) -> t.Callable[[list[exp.Expr]], exp.Expr]:
   266	    def _parse(args: list[exp.Expr]) -> exp.Expr:
   267	        this = seq_get(args, 0)
   268	
   269	        if this and not this.is_string:
   270	            this = exp.cast(this, exp.DType.TEXT)
   271	
   272	        expression = seq_get(args, 1)
   273	        kwargs = {"this": this}
   274	
   275	        if expression:
   276	            kwargs["expression"] = expression
   277	
   278	        return klass(**kwargs)
   279	
   280	    return _parse

[sqlglot/parsers/tsql.py lines 680-690: TSQLParser._parse_into]
   680	    def _parse_into(self) -> exp.Into | None:
   681	        into = super()._parse_into()
   682	
   683	        table = isinstance(into, exp.Into) and into.find(exp.Table)
   684	        if isinstance(table, exp.Table):
   685	            table_identifier = table.this
   686	            if table_identifier.args.get("temporary"):
   687	                # Promote the temporary property from the Identifier to the Into expression
   688	                t.cast(exp.Into, into).set("temporary", True)
   689	
   690	        return into

[grep -nw Year sqlglot/]
sqlglot/expressions/temporal.py:273:class Year(Expression, Func):
sqlglot/generators/hive.py:114:    exp.Year,
sqlglot/generators/mysql.py:231:        exp.Year: _remove_ts_or_ds_to_date(),
sqlglot/parsers/hive.py:118:        "YEAR": lambda args: exp.Year(this=exp.TsOrDsToDate.from_arg_list(args)),
sqlglot/parsers/mysql.py:154:        "YEAR": lambda args: exp.Year(this=exp.TsOrDsToDate(this=seq_get(args, 0))),
sqlglot/typing/__init__.py:214:            exp.Year,
sqlglot/typing/duckdb.py:26:            exp.Year,

[grep -nw Month sqlglot/]
sqlglot/dialects/oracle.py:40:        "MM": "%m",  # Month (01-12; January = 01)
sqlglot/dialects/singlestore.py:22:        "MM": "%m",  # Month (01-12; January = 01)
sqlglot/expressions/temporal.py:245:class Month(Expression, Func):
sqlglot/generators/duckdb.py:950:    #  SELECT DATE_DIFF('MONTH', CAST('2024-11-30' AS DATE), CAST('2024-12-01' AS DATE)) --> 1 (Month crossed)
sqlglot/generators/hive.py:113:    exp.Month,
sqlglot/generators/mysql.py:184:        exp.Month: _remove_ts_or_ds_to_date(),
sqlglot/parsers/hive.py:99:        "MONTH": lambda args: exp.Month(this=exp.TsOrDsToDate.from_arg_list(args)),
sqlglot/parsers/mysql.py:132:        "MONTH": lambda args: exp.Month(this=exp.TsOrDsToDate(this=seq_get(args, 0))),
sqlglot/typing/__init__.py:211:            exp.Month,
sqlglot/typing/duckdb.py:22:            exp.Month,
sqlglot/typing/hive.py:52:            exp.Month,
sqlglot/typing/mysql.py:80:            exp.Month,

[grep -nw Date sqlglot/]
sqlglot/dialects/dialect.py:1929:    # Date truncation
sqlglot/expressions/temporal.py:73:# Date arithmetic
sqlglot/expressions/temporal.py:170:        # https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/ROUND-and-TRUNC-Date-Functions.html
sqlglot/expressions/temporal.py:202:# Date/time extraction
sqlglot/expressions/temporal.py:285:# Date/time construction
sqlglot/expressions/temporal.py:288:class Date(Expression, Func):
sqlglot/expressions/temporal.py:408:# Date/time conversion
sqlglot/generator.py:5186:            self.unsupported("Date parts are not supported in LAST_DAY.")
sqlglot/generators/duckdb.py:283:def _date_sql(self: DuckDBGenerator, expression: exp.Date) -> str:
sqlglot/generators/duckdb.py:1653:        exp.Date: _date_sql,
sqlglot/generators/exasol.py:404:        exp.Date: rename_func("TO_DATE"),
sqlglot/generators/singlestore.py:72:        exp.Date: unsupported_args("zone", "expressions")(rename_func("DATE")),
sqlglot/optimizer/canonicalize.py:58:        exp.Date,
sqlglot/optimizer/canonicalize.py:96:        isinstance(node, (exp.Date, exp.TsOrDsToDate))
sqlglot/optimizer/canonicalize.py:139:        isinstance(expression, (exp.Date, exp.TsOrDsToDate))
sqlglot/parser.py:7786:        types, for example `{d'yyyy-mm-dd'}` will be parsed as a `Date` column, exactly the
sqlglot/parsers/bigquery.py:26:def _build_date(args: list) -> exp.Date | exp.DateFromParts:
sqlglot/parsers/bigquery.py:27:    expr_type = exp.DateFromParts if len(args) == 3 else exp.Date
sqlglot/parsers/dremio.py:66:        return exp.Date(this=exp.Literal.string(date_str))
sqlglot/parsers/exasol.py:162:        "d": exp.Date,
sqlglot/parsers/singlestore.py:109:        "DATE": exp.Date.from_arg_list,
sqlglot/parsers/tsql.py:448:        "d": exp.Date,
sqlglot/typing/__init__.py:76:            exp.Date,

[grep -nw EXTRACT sqlglot/]
sqlglot/dialects/snowflake.py:113:        # Without this override, EXTRACT(EPOCH_SECOND FROM ts) would be normalized
sqlglot/dialects/snowflake.py:114:        # to EXTRACT(EPOCH FROM ts) and lose the integer semantics.
sqlglot/executor/env.py:249:    "EXTRACT": null_if_any(lambda this, e: getattr(e, this)),
sqlglot/generator.py:386:    # Whether to generate an unquoted value for EXTRACT's date part argument
sqlglot/generator.py:574:    # Whether to normalize the date parts in EXTRACT(<date_part> FROM <expr>) into a common representation
sqlglot/generator.py:3633:        return f"EXTRACT({this_sql} FROM {expression_sql})"
sqlglot/generators/duckdb.py:171:        year_expr = exp.func("EXTRACT", "YEAR", date_expr)
sqlglot/generators/duckdb.py:179:        year_expr = exp.func("EXTRACT", "YEAR", date_expr)
sqlglot/generators/duckdb.py:180:        quarter_expr = exp.func("EXTRACT", "QUARTER", date_expr)
sqlglot/generators/duckdb.py:194:        dow = exp.func("EXTRACT", "DAYOFWEEK", date_expr)
sqlglot/generators/duckdb.py:1987:    # Mappings for EXTRACT/DATE_PART transpilation
sqlglot/generators/duckdb.py:2981:        Transpile EXTRACT/DATE_PART for DuckDB, handling specifiers not natively supported.
sqlglot/generators/duckdb.py:2993:                "EXTRACT from TIMESTAMPTZ / TIMESTAMPLTZ may produce different results due to timezone handling differences"
sqlglot/generators/postgres.py:95:        return f"CAST(EXTRACT(epoch FROM {end} - {start}){factor} AS BIGINT)"
sqlglot/generators/postgres.py:100:        unit = f"EXTRACT(days FROM ({end} - {start})) / 7"
sqlglot/generators/postgres.py:102:        unit = f"EXTRACT(year FROM {age}) * 12 + EXTRACT(month FROM {age})"
sqlglot/generators/postgres.py:104:        unit = f"EXTRACT(year FROM {age}) * 4 + EXTRACT(month FROM {age}) / 3"
sqlglot/generators/postgres.py:106:        unit = f"EXTRACT(year FROM {age})"
sqlglot/generators/python.py:92:        exp.Extract: lambda self, e: f"EXTRACT('{e.name.lower()}', {self.sql(e, 'expression')})",
sqlglot/generators/snowflake.py:589:        exp.TimeToUnix: lambda self, e: f"EXTRACT(epoch_second FROM {self.sql(e, 'this')})",
sqlglot/optimizer/annotate_types.py:36:# EXTRACT/DATE_PART specifiers that return BIGINT instead of INT
sqlglot/parser.py:1529:        "EXTRACT": lambda self: self._parse_extract(),
sqlglot/parser.py:7947:            self.raise_error("Expected FROM or comma after EXTRACT", self._prev)

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
