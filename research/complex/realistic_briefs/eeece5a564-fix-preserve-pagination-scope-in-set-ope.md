[sqlglot/expressions/core.py lines 903-905: Expression.expression]
   903	    @property
   904	    def expression(self) -> t.Any:
   905	        return self.args.get("expression")

[sqlglot/expressions/core.py lines 1297-1299: Expression.pop]
  1297	    def pop(self: E) -> E:
  1298	        self.replace(None)
  1299	        return self

[sqlglot/expressions/core.py lines 2578-2579: maybe_copy]
  2578	@t.overload
  2579	def maybe_copy(instance: None, copy: bool = True) -> None: ...

[sqlglot/expressions/core.py lines 2582-2583: maybe_copy]
  2582	@t.overload
  2583	def maybe_copy(instance: E, copy: bool = True) -> E: ...

[sqlglot/expressions/core.py lines 2586-2587: maybe_copy]
  2586	def maybe_copy(instance, copy=True):
  2587	    return instance.copy() if copy and instance else instance

[sqlglot/expressions/query.py lines 1096-1098: SetOperation.kind]
  1096	    @property
  1097	    def kind(self) -> str:
  1098	        return self.text("kind").upper()

[sqlglot/expressions/query.py lines 1100-1102: SetOperation.side]
  1100	    @property
  1101	    def side(self) -> str:
  1102	        return self.text("side").upper()

[sqlglot/generator.py lines 136-298: Generator.<stmt@136>]
   136	    TRANSFORMS: t.ClassVar[dict[type[exp.Expr], t.Callable[..., str]]] = {
   137	        **JSON_PATH_PART_TRANSFORMS,
   138	        exp.Adjacent: lambda self, e: self.binary(e, "-|-"),
   139	        exp.AllowedValuesProperty: lambda self, e: (
   140	            f"ALLOWED_VALUES {self.expressions(e, flat=True)}"
   141	        ),
   142	        exp.AnalyzeColumns: lambda self, e: self.sql(e, "this"),
   143	        exp.AnalyzeWith: lambda self, e: self.expressions(e, prefix="WITH ", sep=" "),
   144	        exp.ArrayContainedBy: lambda self, e: self.binary(e, "<@"),
   145	        exp.ArrayContainsAll: lambda self, e: self.binary(e, "@>"),
   146	        exp.ArrayOverlaps: lambda self, e: self.binary(e, "&&"),
   147	        exp.AssumeColumnConstraint: lambda self, e: f"ASSUME ({self.sql(e, 'this')})",
   148	        exp.AutoRefreshProperty: lambda self, e: f"AUTO REFRESH {self.sql(e, 'this')}",
   149	        exp.BackupProperty: lambda self, e: f"BACKUP {self.sql(e, 'this')}",
   150	        exp.BinaryColumnConstraint: lambda *_: "BINARY",
   151	        exp.CaseSpecificColumnConstraint: lambda _, e: (
   152	            f"{'NOT ' if e.args.get('not_') else ''}CASESPECIFIC"
   153	        ),
   154	        exp.CalledOnNullInputProperty: lambda *_: "CALLED ON NULL INPUT",
   155	        exp.Ceil: lambda self, e: self.ceil_floor(e),
   156	        exp.CharacterSetColumnConstraint: lambda self, e: f"CHARACTER SET {self.sql(e, 'this')}",
   157	        exp.CharacterSetProperty: lambda self, e: (
   158	            f"{'DEFAULT ' if e.args.get('default') else ''}CHARACTER SET={self.sql(e, 'this')}"
   159	        ),
   160	        exp.ClusteredColumnConstraint: lambda self, e: (
   161	            f"CLUSTERED ({self.expressions(e, 'this', indent=False)})"
   162	        ),
   163	        exp.CollateColumnConstraint: lambda self, e: f"COLLATE {self.sql(e, 'this')}",
   164	        exp.CommentColumnConstraint: lambda self, e: f"COMMENT {self.sql(e, 'this')}",
   165	        exp.ConnectByRoot: lambda self, e: f"CONNECT_BY_ROOT {self.sql(e, 'this')}",
   166	        exp.ConvertToCharset: lambda self, e: self.func(
   167	            "CONVERT", e.this, e.args["dest"], e.args.get("source")
   168	        ),
   169	        exp.CopyGrantsProperty: lambda *_: "COPY GRANTS",
   170	        exp.CredentialsProperty: lambda self, e: (
   171	            f"CREDENTIALS=({self.expressions(e, 'expressions', sep=' ')})"
   172	        ),
   173	        exp.CurrentCatalog: lambda *_: "CURRENT_CATALOG",
   174	        exp.SessionUser: lambda *_: "SESSION_USER",
   175	        exp.DateFormatColumnConstraint: lambda self, e: f"FORMAT {self.sql(e, 'this')}",
    ... (123 more lines)

[sqlglot/generator.py lines 1868-1899: Generator.set_operation]
  1868	    def set_operation(self, expression: exp.SetOperation) -> str:
  1869	        op_type = type(expression)
  1870	        op_name = op_type.key.upper()
  1871	
  1872	        distinct = expression.args.get("distinct")
  1873	        if (
  1874	            distinct is False
  1875	            and op_type in (exp.Except, exp.Intersect)
  1876	            and not self.EXCEPT_INTERSECT_SUPPORT_ALL_CLAUSE
  1877	        ):
  1878	            self.unsupported(f"{op_name} ALL is not supported")
  1879	
  1880	        default_distinct = self.dialect.SET_OP_DISTINCT_BY_DEFAULT[op_type]
  1881	
  1882	        if distinct is None:
  1883	            distinct = default_distinct
  1884	            if distinct is None:
  1885	                self.unsupported(f"{op_name} requires DISTINCT or ALL to be specified")
  1886	
  1887	        if distinct is default_distinct:
  1888	            distinct_or_all = ""
  1889	        else:
  1890	            distinct_or_all = " DISTINCT" if distinct else " ALL"
  1891	
  1892	        side_kind = " ".join(filter(None, [expression.side, expression.kind]))
  1893	        side_kind = f"{side_kind} " if side_kind else ""
  1894	
  1895	        by_name = " BY NAME" if expression.args.get("by_name") else ""
  1896	        on = self.expressions(expression, key="on", flat=True)
  1897	        on = f" ON ({on})" if on else ""
  1898	
  1899	        return f"{side_kind}{op_name}{distinct_or_all}{by_name}{on}"

[sqlglot/generator.py lines 1901-1936: Generator.set_operations]
  1901	    def set_operations(self, expression: exp.SetOperation) -> str:
  1902	        if not self.SET_OP_MODIFIERS:
  1903	            limit = expression.args.get("limit")
  1904	            order = expression.args.get("order")
  1905	
  1906	            if limit or order:
  1907	                select = self._move_ctes_to_top_level(
  1908	                    exp.subquery(expression, "_l_0", copy=False).select("*", copy=False)
  1909	                )
  1910	
  1911	                if limit:
  1912	                    select = select.limit(limit.pop(), copy=False)
  1913	                if order:
  1914	                    select = select.order_by(order.pop(), copy=False)
  1915	                return self.sql(select)
  1916	
  1917	        sqls: list[str] = []
  1918	        stack: list[str | exp.Expr] = [expression]
  1919	
  1920	        while stack:
  1921	            node = stack.pop()
  1922	
  1923	            if isinstance(node, exp.SetOperation):
  1924	                stack.append(node.expression)
  1925	                stack.append(
  1926	                    self.maybe_comment(
  1927	                        self.set_operation(node), comments=node.comments, separated=True
  1928	                    )
  1929	                )
  1930	                stack.append(node.this)
  1931	            else:
  1932	                sqls.append(self.sql(node))
  1933	
  1934	        this = self.sep().join(sqls)
  1935	        this = self.query_modifiers(expression, this)
  1936	        return self.prepend_ctes(expression, this)

[sqlglot/generator.py lines 1938-1945: Generator.fetch_sql]
  1938	    def fetch_sql(self, expression: exp.Fetch) -> str:
  1939	        direction = expression.args.get("direction")
  1940	        direction = f" {direction}" if direction else ""
  1941	        count = self.sql(expression, "count")
  1942	        count = f" {count}" if count else ""
  1943	        limit_options = self.sql(expression, "limit_options")
  1944	        limit_options = f"{limit_options}" if limit_options else " ROWS ONLY"
  1945	        return f"{self.seg('FETCH')}{direction}{count}{limit_options}"

[sqlglot/generator.py lines 1947-1953: Generator.limitoptions_sql]
  1947	    def limitoptions_sql(self, expression: exp.LimitOptions) -> str:
  1948	        percent = " PERCENT" if expression.args.get("percent") else ""
  1949	        rows = " ROWS" if expression.args.get("rows") else ""
  1950	        with_ties = " WITH TIES" if expression.args.get("with_ties") else ""
  1951	        if not with_ties and rows:
  1952	            with_ties = " ONLY"
  1953	        return f"{percent}{rows}{with_ties}"

[sqlglot/generator.py lines 2958-2973: Generator.limit_sql]
  2958	    def limit_sql(self, expression: exp.Limit, top: bool = False) -> str:
  2959	        this = self.sql(expression, "this")
  2960	
  2961	        args = [
  2962	            self._simplify_unless_literal(e) if self.LIMIT_ONLY_LITERALS else e
  2963	            for e in (expression.args.get(k) for k in ("offset", "expression"))
  2964	            if e
  2965	        ]
  2966	
  2967	        args_sql = ", ".join(self.sql(e) for e in args)
  2968	        args_sql = f"({args_sql})" if top and any(not e.is_number for e in args) else args_sql
  2969	        expressions = self.expressions(expression, flat=True)
  2970	        limit_options = self.sql(expression, "limit_options")
  2971	        expressions = f" BY {expressions}" if expressions else ""
  2972	
  2973	        return f"{this}{self.seg('TOP' if top else 'LIMIT')} {args_sql}{limit_options}{expressions}"

[sqlglot/generator.py lines 2975-2981: Generator.offset_sql]
  2975	    def offset_sql(self, expression: exp.Offset) -> str:
  2976	        this = self.sql(expression, "this")
  2977	        value = expression.expression
  2978	        value = self._simplify_unless_literal(value) if self.LIMIT_ONLY_LITERALS else value
  2979	        expressions = self.expressions(expression, flat=True)
  2980	        expressions = f" BY {expressions}" if expressions else ""
  2981	        return f"{this}{self.seg('OFFSET')} {self.sql(value)}{expressions}"

[sqlglot/generator.py lines 3351-3357: Generator.offset_limit_modifiers]
  3351	    def offset_limit_modifiers(
  3352	        self, expression: exp.Expr, fetch: bool, limit: exp.Fetch | exp.Limit | None
  3353	    ) -> list[str]:
  3354	        return [
  3355	            self.sql(expression, "offset") if fetch else self.sql(limit),
  3356	            self.sql(limit) if fetch else self.sql(expression, "offset"),
  3357	        ]

[sqlglot/generator.py lines 3458-3467: Generator.star_sql]
  3458	    def star_sql(self, expression: exp.Star) -> str:
  3459	        except_ = self.expressions(expression, key="except_", flat=True)
  3460	        except_ = f"{self.seg(self.STAR_EXCEPT)} ({except_})" if except_ else ""
  3461	        replace = self.expressions(expression, key="replace", flat=True)
  3462	        replace = f"{self.seg('REPLACE')} ({replace})" if replace else ""
  3463	        rename = self.expressions(expression, key="rename", flat=True)
  3464	        rename = f"{self.seg('RENAME')} ({rename})" if rename else ""
  3465	        ilike = self.sql(expression, "ilike")
  3466	        ilike = f"{self.seg('ILIKE')} {ilike}" if ilike else ""
  3467	        return f"*{ilike}{except_}{replace}{rename}"

[sqlglot/generators/clickhouse.py lines 448-457: ClickHouseGenerator.offset_sql]
   448	    def offset_sql(self, expression: exp.Offset) -> str:
   449	        offset = super().offset_sql(expression)
   450	
   451	        # OFFSET ... FETCH syntax requires a "ROW" or "ROWS" keyword
   452	        # https://clickhouse.com/docs/sql-reference/statements/select/offset
   453	        parent = expression.parent
   454	        if isinstance(parent, exp.Select) and isinstance(parent.args.get("limit"), exp.Fetch):
   455	            offset = f"{offset} ROWS"
   456	
   457	        return offset

[sqlglot/generators/clickhouse.py lines 560-572: ClickHouseGenerator.after_limit_modifiers]
   560	    def after_limit_modifiers(self, expression: exp.Expr) -> list[str]:
   561	        return super().after_limit_modifiers(expression) + [
   562	            (
   563	                self.seg("SETTINGS ") + self.expressions(expression, key="settings", flat=True)
   564	                if expression.args.get("settings")
   565	                else ""
   566	            ),
   567	            (
   568	                self.seg("FORMAT ") + self.sql(expression, "format")
   569	                if expression.args.get("format")
   570	                else ""
   571	            ),
   572	        ]

[sqlglot/generators/sqlite.py lines 87-96: _offset_to_limit]
    87	def _offset_to_limit(expression: exp.Expr) -> exp.Expr:
    88	    if not isinstance(expression, exp.Select):
    89	        return expression
    90	
    91	    offset = expression.args.get("offset")
    92	
    93	    if offset and not expression.args.get("limit"):
    94	        expression.limit(-1, copy=False)
    95	
    96	    return expression

[sqlglot/generators/tsql.py lines 276-298: TSQLGenerator.select_sql]
   276	    def select_sql(self, expression: exp.Select) -> str:
   277	        limit = expression.args.get("limit")
   278	        offset = expression.args.get("offset")
   279	
   280	        if isinstance(limit, exp.Fetch) and not offset:
   281	            # Dialects like Oracle can FETCH directly from a row set but
   282	            # T-SQL requires an ORDER BY + OFFSET clause in order to FETCH
   283	            offset = exp.Offset(expression=exp.Literal.number(0))
   284	            expression.set("offset", offset)
   285	
   286	        if offset:
   287	            if not expression.args.get("order"):
   288	                # ORDER BY is required in order to use OFFSET in a query, so we use
   289	                # a noop order by, since we don't really care about the order.
   290	                # See: https://www.microsoftpressstore.com/articles/article.aspx?p=2314819
   291	                expression.order_by(exp.select(exp.null()).subquery(), copy=False)
   292	
   293	            if isinstance(limit, exp.Limit):
   294	                # TOP and OFFSET can't be combined, we need use FETCH instead of TOP
   295	                # we replace here because otherwise TOP would be generated in select_sql
   296	                limit.replace(exp.Fetch(direction="FIRST", count=limit.expression))
   297	
   298	        return super().select_sql(expression)

[sqlglot/generators/tsql.py lines 507-508: TSQLGenerator.offset_sql]
   507	    def offset_sql(self, expression: exp.Offset) -> str:
   508	        return f"{super().offset_sql(expression)} ROWS"

[sqlglot/parser.py lines 5757-5766: Parser._parse_limit_options]
  5757	    def _parse_limit_options(self) -> exp.LimitOptions | None:
  5758	        percent = self._match_set((TokenType.PERCENT, TokenType.MOD))
  5759	        rows = self._match_set((TokenType.ROW, TokenType.ROWS))
  5760	        self._match_text_seq("ONLY")
  5761	        with_ties = self._match_text_seq("WITH", "TIES")
  5762	
  5763	        if not (percent or rows or with_ties):
  5764	            return None
  5765	
  5766	        return self.expression(exp.LimitOptions(percent=percent, rows=rows, with_ties=with_ties))

[sqlglot/parser.py lines 5830-5839: Parser._parse_offset]
  5830	    def _parse_offset(self, this: exp.Expr | None = None) -> exp.Expr | None:
  5831	        if not self._match(TokenType.OFFSET):
  5832	            return this
  5833	
  5834	        count = self._parse_term()
  5835	        self._match_set((TokenType.ROW, TokenType.ROWS))
  5836	
  5837	        return self.expression(
  5838	            exp.Offset(this=this, expression=count, expressions=self._parse_limit_by())
  5839	        )

[sqlglot/parser.py lines 5875-5876: Parser._parse_limit_by]
  5875	    def _parse_limit_by(self) -> list[exp.Expr] | None:
  5876	        return self._parse_csv(self._parse_bitwise) if self._match_text_seq("BY") else None

[sqlglot/parsers/duckdb.py lines 62-66: _show_parser]
    62	def _show_parser(*args: t.Any, **kwargs: t.Any) -> t.Callable[[DuckDBParser], exp.Show]:
    63	    def _parse(self: DuckDBParser) -> exp.Show:
    64	        return self._parse_show_duckdb(*args, **kwargs)
    65	
    66	    return _parse

[sqlglot/parsers/duckdb.py lines 252-252: DuckDBParser.<stmt@252>]
   252	    SET_TRIE = new_trie(key.split(" ") for key in SET_PARSERS)

[grep -nw Rows sqlglot/]
sqlglot/executor/context.py:60:                    raise Exception("Rows are different.")

[grep -nw Fetch sqlglot/]
sqlglot/expressions/query.py:602:class Fetch(Expression):
sqlglot/generator.py:1938:    def fetch_sql(self, expression: exp.Fetch) -> str:
sqlglot/generator.py:3303:        if self.LIMIT_FETCH == "LIMIT" and isinstance(limit, exp.Fetch):
sqlglot/generator.py:3311:            limit = exp.Fetch(direction="FIRST", count=exp.maybe_copy(limit.expression))
sqlglot/generator.py:3325:            *self.offset_limit_modifiers(expression, isinstance(limit, exp.Fetch), limit),
sqlglot/generator.py:3352:        self, expression: exp.Expr, fetch: bool, limit: exp.Fetch | exp.Limit | None
sqlglot/generators/clickhouse.py:454:        if isinstance(parent, exp.Select) and isinstance(parent.args.get("limit"), exp.Fetch):
sqlglot/generators/presto.py:632:        self, expression: exp.Expr, fetch: bool, limit: exp.Fetch | exp.Limit | None
sqlglot/generators/tsql.py:280:        if isinstance(limit, exp.Fetch) and not offset:
sqlglot/generators/tsql.py:296:                limit.replace(exp.Fetch(direction="FIRST", count=limit.expression))
sqlglot/optimizer/unnest_subqueries.py:153:    if not where or where.find(exp.Or) or select.find(exp.Limit, exp.Offset, exp.Fetch):
sqlglot/parser.py:5823:                exp.Fetch(

[grep -nw First sqlglot/]
sqlglot/dialects/dialect.py:368:    """First day of the week in DATE_TRUNC(week). Defaults to 0 (Monday). -1 would be Sunday."""
sqlglot/expressions/aggregate.py:126:class First(Expression, AggFunc):
sqlglot/generators/duckdb.py:3996:        if isinstance(this, exp.First):
sqlglot/generators/duckdb.py:4474:            # 1. First AT TIME ZONE: ensures truncation happens in the target timezone
sqlglot/generators/hive.py:408:    IGNORE_NULLS_FUNCS: t.ClassVar = (exp.First, exp.Last, exp.FirstValue, exp.LastValue)
sqlglot/generators/presto.py:354:        exp.First: _first_last_sql,
sqlglot/optimizer/qualify_columns.py:868:    # First part is the table name and last part is the star so they can be dropped
sqlglot/parsers/hive.py:96:        "FIRST": build_with_ignore_nulls(exp.First),
sqlglot/planner.py:267:                        exp.alias_(exp.First(this=key), f"_o_{i}", quoted=True)
sqlglot/typing/hive.py:64:            exp.First,
sqlglot/typing/snowflake.py:118:    # First annotate the argument to get its type
sqlglot/typing/snowflake.py:158:    # First annotate the argument to get its type

[grep -nw INTERSECT sqlglot/]
sqlglot/expressions/query.py:391:        Builds an INTERSECT expression.
sqlglot/expressions/query.py:396:            'SELECT * FROM foo INTERSECT SELECT * FROM bla'
sqlglot/expressions/query.py:2223:    Initializes a syntax tree for the `INTERSECT` operation.
sqlglot/expressions/query.py:2227:        'SELECT * FROM foo INTERSECT SELECT * FROM bla'
sqlglot/expressions/query.py:2230:        expressions: the SQL code strings, corresponding to the `INTERSECT`'s operands.
sqlglot/generator.py:319:    # Whether the EXCEPT and INTERSECT operations can return duplicates
sqlglot/generators/duckdb.py:2167:    #                      e.g. [2,2,2] INTERSECT [2,2] -> [2,2]
sqlglot/optimizer/annotate_types.py:642:        This handles UNION, INTERSECT, EXCEPT, etc., coercing types across
sqlglot/optimizer/pushdown_projections.py:151:        # SELECT DISTINCT, UNION DISTINCT, INTERSECT, and EXCEPT consume the entire row, so we
sqlglot/parser.py:1008:        TokenType.INTERSECT,
sqlglot/parsers/prql.py:43:        "INTERSECT": lambda self, query: query.intersect(
sqlglot/tokenizer_core.py:324:    INTERSECT = auto()
sqlglot/tokens.py:303:        "INTERSECT": TokenType.INTERSECT,

[grep -nw FETCH sqlglot/]
sqlglot/generator.py:344:    # Whether limit and fetch are supported (possible values: "ALL", "LIMIT", "FETCH")
sqlglot/generator.py:1945:        return f"{self.seg('FETCH')}{direction}{count}{limit_options}"
sqlglot/generator.py:3305:            # "FETCH FIRST ROWS ONLY" without a count means one row per the SQL
sqlglot/generator.py:3310:        elif self.LIMIT_FETCH == "FETCH" and isinstance(limit, exp.Limit):
sqlglot/generators/clickhouse.py:451:        # OFFSET ... FETCH syntax requires a "ROW" or "ROWS" keyword
sqlglot/generators/oracle.py:33:    LIMIT_FETCH = "FETCH"
sqlglot/generators/tsql.py:143:    LIMIT_FETCH = "FETCH"
sqlglot/generators/tsql.py:281:            # Dialects like Oracle can FETCH directly from a row set but
sqlglot/generators/tsql.py:282:            # T-SQL requires an ORDER BY + OFFSET clause in order to FETCH
sqlglot/generators/tsql.py:294:                # TOP and OFFSET can't be combined, we need use FETCH instead of TOP
sqlglot/parser.py:1607:        TokenType.FETCH: lambda self: ("limit", self._parse_limit()),
sqlglot/parser.py:5813:        if self._match(TokenType.FETCH):
sqlglot/tokenizer_core.py:294:    FETCH = auto()
sqlglot/tokens.py:280:        "FETCH": TokenType.FETCH,
sqlglot/tokens.py:518:        TokenType.FETCH,

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
