[sqlglot/expressions/query.py lines 989-1002: Table.parts]
   989	    @property
   990	    def parts(self) -> list[Expr]:
   991	        """Return the parts of a table in order catalog, db, table."""
   992	        parts: list[Expr] = []
   993	
   994	        for arg in ("catalog", "db", "this"):
   995	            part = self.args.get(arg)
   996	
   997	            if isinstance(part, Dot):
   998	                parts.extend(part.flatten())
   999	            elif isinstance(part, Expr):
  1000	                parts.append(part)
  1001	
  1002	        return parts

[sqlglot/generator.py lines 4161-4162: Generator.command_sql]
  4161	    def command_sql(self, expression: exp.Command) -> str:
  4162	        return f"{self.sql(expression, 'this')} {expression.text('expression').strip()}"

[sqlglot/parser.py lines 1110-1141: Parser.<stmt@1110>]
  1110	    STATEMENT_PARSERS: t.ClassVar = {
  1111	        TokenType.ALTER: lambda self: self._parse_alter(),
  1112	        TokenType.ANALYZE: lambda self: self._parse_analyze(),
  1113	        TokenType.BEGIN: lambda self: self._parse_transaction(),
  1114	        TokenType.CACHE: lambda self: self._parse_cache(),
  1115	        TokenType.COMMENT: lambda self: self._parse_comment(),
  1116	        TokenType.COMMIT: lambda self: self._parse_commit_or_rollback(),
  1117	        TokenType.COPY: lambda self: self._parse_copy(),
  1118	        TokenType.CREATE: lambda self: self._parse_create(),
  1119	        TokenType.DECLARE: lambda self: self._parse_declare(),
  1120	        TokenType.DELETE: lambda self: self._parse_delete(),
  1121	        TokenType.DESC: lambda self: self._parse_describe(),
  1122	        TokenType.DESCRIBE: lambda self: self._parse_describe(),
  1123	        TokenType.DROP: lambda self: self._parse_drop(),
  1124	        TokenType.GRANT: lambda self: self._parse_grant(),
  1125	        TokenType.REVOKE: lambda self: self._parse_revoke(),
  1126	        TokenType.INSERT: lambda self: self._parse_insert(),
  1127	        TokenType.KILL: lambda self: self._parse_kill(),
  1128	        TokenType.LOAD: lambda self: self._parse_load(),
  1129	        TokenType.MERGE: lambda self: self._parse_merge(),
  1130	        TokenType.PIVOT: lambda self: self._parse_simplified_pivot(),
  1131	        TokenType.PRAGMA: lambda self: self.expression(exp.Pragma(this=self._parse_expression())),
  1132	        TokenType.REFRESH: lambda self: self._parse_refresh(),
  1133	        TokenType.ROLLBACK: lambda self: self._parse_commit_or_rollback(),
  1134	        TokenType.SET: lambda self: self._parse_set(),
  1135	        TokenType.TRUNCATE: lambda self: self._parse_truncate_table(),
  1136	        TokenType.UNCACHE: lambda self: self._parse_uncache(),
  1137	        TokenType.UNPIVOT: lambda self: self._parse_simplified_pivot(is_unpivot=True),
  1138	        TokenType.UPDATE: lambda self: self._parse_update(),
  1139	        TokenType.USE: lambda self: self._parse_use(),
  1140	        TokenType.SEMICOLON: lambda self: exp.Semicolon(),
  1141	    }

[sqlglot/parser.py lines 2214-2224: Parser._warn_unsupported]
  2214	    def _warn_unsupported(self) -> None:
  2215	        if self._tokens_size <= 1:
  2216	            return
  2217	
  2218	        # We use _find_sql because self.sql may comprise multiple chunks, and we're only
  2219	        # interested in emitting a warning for the one being currently processed.
  2220	        sql = self._find_sql(self._tokens[0], self._tokens[-1])[: self.error_message_context]
  2221	
  2222	        logger.warning(
  2223	            f"'{sql}' contains unsupported syntax. Falling back to parsing as a 'Command'."
  2224	        )

[sqlglot/parser.py lines 2396-2401: Parser._parse_exists]
  2396	    def _parse_exists(self, not_: bool = False) -> bool | None:
  2397	        return (
  2398	            self._match_text_seq("IF")
  2399	            and (not not_ or self._match(TokenType.NOT))
  2400	            and self._match(TokenType.EXISTS)
  2401	        )

[sqlglot/parser.py lines 2842-2869: Parser._parse_property]
  2842	    def _parse_property(self) -> exp.Expr | list[exp.Expr] | None:
  2843	        if self._match_texts(self.PROPERTY_PARSERS):
  2844	            return self.PROPERTY_PARSERS[self._prev.text.upper()](self)
  2845	
  2846	        if self._match_text_seq("CHARACTER", "SET"):
  2847	            return self._parse_character_set()
  2848	
  2849	        if self._match(TokenType.DEFAULT):
  2850	            if self._match_texts(self.PROPERTY_PARSERS):
  2851	                return self.PROPERTY_PARSERS[self._prev.text.upper()](self, default=True)
  2852	
  2853	            if self._match_text_seq("CHARACTER", "SET"):
  2854	                return self._parse_character_set(default=True)
  2855	
  2856	        if self._match_text_seq("COMPOUND", "SORTKEY"):
  2857	            return self._parse_sortkey(compound=True)
  2858	
  2859	        if self._match_text_seq("PARAMETER", "STYLE", "PANDAS"):
  2860	            return self.expression(exp.ParameterStyleProperty(this="PANDAS"))
  2861	
  2862	        index = self._index
  2863	
  2864	        seq_props = self._parse_sequence_properties()
  2865	        if seq_props:
  2866	            return seq_props
  2867	
  2868	        self._retreat(index)
  2869	        return self._parse_key_value_property()

[sqlglot/parser.py lines 2871-2895: Parser._parse_key_value_property]
  2871	    def _parse_key_value_property(
  2872	        self, parse_value: t.Callable[[], exp.Expr | None] | None = None
  2873	    ) -> exp.Property | None:
  2874	        index = self._index
  2875	        key = self._parse_column()
  2876	
  2877	        if not self._match(TokenType.EQ):
  2878	            self._retreat(index)
  2879	            return None
  2880	
  2881	        # Transform the key to exp.Dot if it's dotted identifiers wrapped in exp.Column or to exp.Var otherwise
  2882	        if isinstance(key, exp.Column):
  2883	            key = key.to_dot() if len(key.parts) > 1 else exp.var(key.name)
  2884	
  2885	        value = (
  2886	            parse_value()
  2887	            if parse_value
  2888	            else self._parse_bitwise() or self._parse_var(any_token=True)
  2889	        )
  2890	
  2891	        # Transform the value to exp.Var if it was parsed as exp.Column(exp.Identifier())
  2892	        if isinstance(value, exp.Column):
  2893	            value = exp.var(value.name)
  2894	
  2895	        return self.expression(exp.Property(this=key, value=value))

[sqlglot/parser.py lines 4570-4576: Parser._parse_stream]
  4570	    def _parse_stream(self) -> exp.Stream | None:
  4571	        index = self._index
  4572	        if self._match(TokenType.STREAM):
  4573	            if this := self._try_parse(self._parse_table):
  4574	                return self.expression(exp.Stream(this=this))
  4575	            self._retreat(index)
  4576	        return None

[sqlglot/parser.py lines 4794-4800: Parser._parse_table_part]
  4794	    def _parse_table_part(self, schema: bool = False) -> exp.Expr | None:
  4795	        return (
  4796	            (not schema and self._parse_function(optional_parens=False))
  4797	            or self._parse_id_var(any_token=False)
  4798	            or self._parse_string_as_identifier()
  4799	            or self._parse_placeholder()
  4800	        )

[sqlglot/parser.py lines 5104-5125: Parser._parse_historical_data]
  5104	    def _parse_historical_data(self) -> exp.HistoricalData | None:
  5105	        # https://docs.snowflake.com/en/sql-reference/constructs/at-before
  5106	        index = self._index
  5107	        historical_data = None
  5108	        if self._match_texts(self.HISTORICAL_DATA_PREFIX):
  5109	            this = self._prev.text.upper()
  5110	            kind = (
  5111	                self._match(TokenType.L_PAREN)
  5112	                and self._match_texts(self.HISTORICAL_DATA_KIND)
  5113	                and self._prev.text.upper()
  5114	            )
  5115	            expression = self._match(TokenType.FARROW) and self._parse_bitwise()
  5116	
  5117	            if expression:
  5118	                self._match_r_paren()
  5119	                historical_data = self.expression(
  5120	                    exp.HistoricalData(this=this, kind=kind, expression=expression)
  5121	                )
  5122	            else:
  5123	                self._retreat(index)
  5124	
  5125	        return historical_data

[sqlglot/parser.py lines 5142-5171: Parser._parse_unnest]
  5142	    def _parse_unnest(self, with_alias: bool = True) -> exp.Unnest | None:
  5143	        if not self._match_pair(TokenType.UNNEST, TokenType.L_PAREN, advance=False):
  5144	            return None
  5145	
  5146	        self._advance()
  5147	
  5148	        expressions = self._parse_wrapped_csv(self._parse_equality)
  5149	        offset: bool | exp.Expr = self._match_pair(TokenType.WITH, TokenType.ORDINALITY)
  5150	
  5151	        alias = self._parse_table_alias() if with_alias else None
  5152	
  5153	        if alias:
  5154	            if self.dialect.UNNEST_COLUMN_ONLY:
  5155	                if alias.args.get("columns"):
  5156	                    self.raise_error("Unexpected extra column alias in unnest.")
  5157	
  5158	                alias.set("columns", [alias.this])
  5159	                alias.set("this", None)
  5160	
  5161	            columns = alias.args.get("columns") or []
  5162	            if offset and len(expressions) < len(columns):
  5163	                offset = columns.pop()
  5164	
  5165	        if not offset and self._match_pair(TokenType.WITH, TokenType.OFFSET):
  5166	            self._match(TokenType.ALIAS)
  5167	            offset = self._parse_id_var(
  5168	                any_token=False, tokens=self.UNNEST_OFFSET_ALIAS_TOKENS
  5169	            ) or exp.to_identifier("offset")
  5170	
  5171	        return self.expression(exp.Unnest(expressions=expressions, alias=alias, offset=offset))

[sqlglot/parser.py lines 5173-5189: Parser._parse_derived_table_values]
  5173	    def _parse_derived_table_values(self) -> exp.Values | None:
  5174	        is_derived = self._match_pair(TokenType.L_PAREN, TokenType.VALUES)
  5175	        if not is_derived and not (
  5176	            # ClickHouse's `FORMAT Values` is equivalent to `VALUES`
  5177	            self._match_text_seq("VALUES") or self._match_text_seq("FORMAT", "VALUES")
  5178	        ):
  5179	            return None
  5180	
  5181	        expressions = self._parse_csv(self._parse_value)
  5182	        alias = self._parse_table_alias()
  5183	
  5184	        if is_derived:
  5185	            self._match_r_paren()
  5186	
  5187	        return self.expression(
  5188	            exp.Values(expressions=expressions, alias=alias or self._parse_table_alias())
  5189	        )

[sqlglot/parser.py lines 6940-7006: Parser._parse_column_ops]
  6940	    def _parse_column_ops(self, this: exp.Expr | None) -> exp.Expr | None:
  6941	        while self._curr.token_type in self.BRACKETS:
  6942	            this = self._parse_bracket(this)
  6943	
  6944	        column_operators = self.COLUMN_OPERATORS
  6945	        cast_column_operators = self.CAST_COLUMN_OPERATORS
  6946	        while self._curr:
  6947	            op_token = self._curr.token_type
  6948	
  6949	            if op_token not in column_operators:
  6950	                break
  6951	            op = column_operators[op_token]
  6952	            self._advance()
  6953	
  6954	            if op_token in cast_column_operators:
  6955	                field = self._parse_dcolon()
  6956	                if not field:
  6957	                    self.raise_error("Expected type")
  6958	            elif op and self._curr:
  6959	                field = self._parse_column_reference() or self._parse_bitwise()
  6960	                if isinstance(field, exp.Column) and self._match(TokenType.DOT, advance=False):
  6961	                    field = self._parse_column_ops(field)
  6962	            else:
  6963	                dot = self._is_connected() and self._prev.token_type == TokenType.DOT
  6964	                field = self._parse_field(any_token=True, anonymous_func=True)
  6965	
  6966	                # In t.true, t.null we should produce an Identifier node
  6967	                if dot and isinstance(field, (exp.Null, exp.Boolean)):
  6968	                    field = self.expression(
  6969	                        exp.Identifier(this=self._prev.text),
  6970	                        comments=field.comments,
  6971	                    )
  6972	
  6973	            # Function calls can be qualified, e.g., x.y.FOO()
  6974	            # This converts the final AST to a series of Dots leading to the function call
  6975	            # https://cloud.google.com/bigquery/docs/reference/standard-sql/functions-reference#function_call_rules
  6976	            if isinstance(field, (exp.Func, exp.Window)) and this:
  6977	                this = this.transform(
  6978	                    lambda n: n.to_dot(include_dots=False) if isinstance(n, exp.Column) else n
  6979	                )
    ... (27 more lines)

[sqlglot/parser.py lines 9126-9176: Parser._parse_alter]
  9126	    def _parse_alter(self) -> exp.Alter | exp.Command:
  9127	        start = self._prev
  9128	
  9129	        iceberg = self._match_text_seq("ICEBERG")
  9130	
  9131	        alter_token = self._match_set(self.ALTERABLES) and self._prev
  9132	        if not alter_token:
  9133	            return self._parse_as_command(start)
  9134	        if iceberg and alter_token.token_type != TokenType.TABLE:
  9135	            return self._parse_as_command(start)
  9136	
  9137	        exists = self._parse_exists()
  9138	        only = self._match_text_seq("ONLY")
  9139	
  9140	        if alter_token.token_type == TokenType.SESSION:
  9141	            this = None
  9142	            check = None
  9143	            cluster = None
  9144	        else:
  9145	            this = self._parse_table(schema=True, parse_partition=self.ALTER_TABLE_PARTITIONS)
  9146	            check = self._match_text_seq("WITH", "CHECK")
  9147	            cluster = self._parse_on_property() if self._match(TokenType.ON) else None
  9148	
  9149	            if self._next:
  9150	                self._advance()
  9151	
  9152	        parser = self.ALTER_PARSERS.get(self._prev.text.upper()) if self._prev else None
  9153	        if parser:
  9154	            actions = ensure_list(parser(self))
  9155	            not_valid = self._match_text_seq("NOT", "VALID")
  9156	            options = self._parse_csv(self._parse_property)
  9157	            cascade = self.dialect.ALTER_TABLE_SUPPORTS_CASCADE and self._match_text_seq("CASCADE")
  9158	
  9159	            if not self._curr and actions:
  9160	                return self.expression(
  9161	                    exp.Alter(
  9162	                        this=this,
  9163	                        kind=alter_token.text.upper(),
  9164	                        exists=exists,
  9165	                        actions=actions,
    ... (11 more lines)

[sqlglot/parser.py lines 9511-9517: Parser._parse_as_command]
  9511	    def _parse_as_command(self, start: Token) -> exp.Command:
  9512	        while self._curr:
  9513	            self._advance()
  9514	        text = self._find_sql(start, self._prev)
  9515	        size = len(start.text)
  9516	        self._warn_unsupported()
  9517	        return exp.Command(this=text[:size], expression=text[size:])

[sqlglot/parsers/clickhouse.py lines 460-464: ClickHouseParser.<stmt@460>]
   460	    ALTER_PARSERS = {
   461	        **parser.Parser.ALTER_PARSERS,
   462	        "MODIFY": lambda self: self._parse_alter_table_modify(),
   463	        "REPLACE": lambda self: self._parse_alter_table_replace(),
   464	    }

[sqlglot/parsers/clickhouse.py lines 911-914: ClickHouseParser._parse_alter_table_modify]
   911	    def _parse_alter_table_modify(self) -> exp.Expr | None:
   912	        if properties := self._parse_properties():
   913	            return self.expression(exp.AlterModifySqlSecurity(expressions=properties.expressions))
   914	        return None

[grep -nw REMOVE sqlglot/]
sqlglot/dialects/snowflake.py:159:            "REMOVE": TokenType.COMMAND,
sqlglot/parsers/prql.py:40:        "REMOVE": lambda self, query: query.except_(

[grep -nw MODIFY sqlglot/]
sqlglot/generator.py:482:    # Whether ALTER TABLE ... MODIFY COLUMN column-redefinition syntax is supported
sqlglot/generator.py:4268:            self.unsupported("MODIFY COLUMN is not supported in this dialect")
sqlglot/generator.py:4269:        return f"MODIFY COLUMN {this}"
sqlglot/generator.py:6319:        return f"MODIFY {props}"
sqlglot/generators/mysql.py:753:        return f"MODIFY COLUMN {this} {dtype}{null_constraint}"
sqlglot/parsers/clickhouse.py:462:        "MODIFY": lambda self: self._parse_alter_table_modify(),
sqlglot/parsers/mysql.py:253:        "MODIFY": lambda self: self._parse_alter_table_modify(),
sqlglot/parsers/mysql.py:333:        # MODIFY [COLUMN]            col_name      column_definition [FIRST | AFTER col_name]
sqlglot/parsers/snowflake.py:750:        "MODIFY": lambda self: self._parse_alter_table_alter(),

[grep -nw Exists sqlglot/]
sqlglot/expressions/functions.py:187:class Exists(Expression, Func, SubqueryPredicate):
sqlglot/generator.py:3608:    def exists_sql(self, expression: exp.Exists) -> str:
sqlglot/generators/bigquery.py:170:        exp.Exists(
sqlglot/generators/hive.py:583:    def exists_sql(self, expression: exp.Exists) -> str:
sqlglot/optimizer/unnest_subqueries.py:93:        if isinstance(predicate, exp.Exists):
sqlglot/optimizer/unnest_subqueries.py:233:    if isinstance(parent_predicate, exp.Exists):
sqlglot/optimizer/unnest_subqueries.py:240:            if isinstance(parent_predicate, exp.Exists) or key != value.this:
sqlglot/optimizer/unnest_subqueries.py:249:    if isinstance(parent_predicate, exp.Exists):
sqlglot/optimizer/unnest_subqueries.py:340:            if isinstance(expression.left, (exp.Subquery, exp.Any, exp.Exists, exp.All))
sqlglot/parser.py:609:        TokenType.EXISTS: exp.Exists,
sqlglot/transforms.py:622:                exists: exp.Exists | exp.Not = exp.Exists(this=subquery)
sqlglot/transforms.py:663:            expression_copy = expression_copy.where(exp.Exists(this=anti_join_clause).not_())
sqlglot/transforms.py:996:                binop.replace(exp.Exists(this=this.unnest(), expression=lambda_expr))
sqlglot/typing/__init__.py:66:            exp.Exists,

[grep -nw Alter sqlglot/]
sqlglot/expressions/builders.py:47:from sqlglot.expressions.ddl import Alter, AlterRename, RenameColumn
sqlglot/expressions/builders.py:601:) -> Alter:
sqlglot/expressions/builders.py:610:        Alter table expression
sqlglot/expressions/builders.py:614:    return Alter(
sqlglot/expressions/builders.py:629:) -> Alter:
sqlglot/expressions/builders.py:640:        Alter table expression
sqlglot/expressions/builders.py:645:    return Alter(
sqlglot/expressions/ddl.py:398:class Alter(Expression):
sqlglot/generator.py:4315:    def alter_sql(self, expression: exp.Alter) -> str:
sqlglot/generators/athena.py:61:    elif isinstance(expression, (exp.Alter, exp.Drop, exp.Describe, exp.Show)):
sqlglot/generators/athena.py:103:    def alter_sql(self, expression: exp.Alter) -> str:
sqlglot/generators/athena.py:104:        if isinstance(expression, exp.Alter) and expression.kind == "TABLE":
sqlglot/generators/tsql.py:591:    def alter_sql(self, expression: exp.Alter) -> str:
sqlglot/parser.py:1860:    # Whether Alter statements are allowed to contain Partition specifications
sqlglot/parser.py:9126:    def _parse_alter(self) -> exp.Alter | exp.Command:
sqlglot/parser.py:9161:                    exp.Alter(

[grep -nw AlterColumn sqlglot/]
sqlglot/expressions/ddl.py:241:class AlterColumn(Expression):
sqlglot/generator.py:4211:    def altercolumn_sql(self, expression: exp.AlterColumn) -> str:
sqlglot/generator.py:4249:    def _alter_column_null_constraint_sql(self, expression: exp.AlterColumn) -> str:
sqlglot/generators/hive.py:539:    def altercolumn_sql(self, expression: exp.AlterColumn) -> str:
sqlglot/generators/mysql.py:746:    def altercolumn_sql(self, expression: exp.AlterColumn) -> str:
sqlglot/generators/singlestore.py:1588:    def altercolumn_sql(self, expression: exp.AlterColumn) -> str:
sqlglot/generators/spark2.py:242:    def altercolumn_sql(self, expression: exp.AlterColumn) -> str:
sqlglot/parser.py:9004:            return self.expression(exp.AlterColumn(this=column, drop=True))
sqlglot/parser.py:9006:            return self.expression(exp.AlterColumn(this=column, default=self._parse_disjunction()))
sqlglot/parser.py:9008:            return self.expression(exp.AlterColumn(this=column, comment=self._parse_string()))
sqlglot/parser.py:9010:            return self.expression(exp.AlterColumn(this=column, drop=True, allow_null=True))
sqlglot/parser.py:9012:            return self.expression(exp.AlterColumn(this=column, allow_null=False))
sqlglot/parser.py:9015:            return self.expression(exp.AlterColumn(this=column, visible="VISIBLE"))
sqlglot/parser.py:9017:            return self.expression(exp.AlterColumn(this=column, visible="INVISIBLE"))
sqlglot/parser.py:9022:            exp.AlterColumn(
sqlglot/parsers/hive.py:229:            return self.expression(exp.AlterColumn(this=this, dtype=self._parse_types(schema=True)))
sqlglot/parsers/hive.py:242:            exp.AlterColumn(this=this, rename_to=column_new, dtype=dtype, comment=comment)

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
