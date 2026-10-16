[sqlglot/expressions/core.py lines 1039-1055: Expression.add_comments]
  1039	    def add_comments(self, comments: list[str] | None = None, prepend: bool = False) -> None:
  1040	        if self.comments is None:
  1041	            self.comments = []
  1042	
  1043	        if comments:
  1044	            for comment in comments:
  1045	                _, *meta = comment.split(SQLGLOT_META)
  1046	                if meta:
  1047	                    for kv in "".join(meta).split(","):
  1048	                        k, *v = kv.split("=")
  1049	                        self.meta[k.strip()] = to_bool(v[0].strip() if v else True)
  1050	
  1051	                if not prepend:
  1052	                    self.comments.append(comment)
  1053	
  1054	            if prepend:
  1055	                self.comments = comments + self.comments

[sqlglot/expressions/query.py lines 1010-1023: Table.parts]
  1010	    @property
  1011	    def parts(self) -> list[Expr]:
  1012	        """Return the parts of a table in order catalog, db, table."""
  1013	        parts: list[Expr] = []
  1014	
  1015	        for arg in ("catalog", "db", "this"):
  1016	            part = self.args.get(arg)
  1017	
  1018	            if isinstance(part, Dot):
  1019	                parts.extend(part.flatten())
  1020	            elif isinstance(part, Expr):
  1021	                parts.append(part)
  1022	
  1023	        return parts

[sqlglot/generator.py lines 4253-4254: Generator.command_sql]
  4253	    def command_sql(self, expression: exp.Command) -> str:
  4254	        return f"{self.sql(expression, 'this')} {expression.text('expression').strip()}"

[sqlglot/generator.py lines 4417-4461: Generator.alter_sql]
  4417	    def alter_sql(self, expression: exp.Alter) -> str:
  4418	        actions = expression.args["actions"]
  4419	
  4420	        if not self.dialect.ALTER_TABLE_ADD_REQUIRED_FOR_EACH_COLUMN and isinstance(
  4421	            actions[0], exp.ColumnDef
  4422	        ):
  4423	            actions_sql = self.expressions(expression, key="actions", flat=True)
  4424	            actions_sql = f"ADD {actions_sql}"
  4425	        else:
  4426	            actions_list = []
  4427	            for action in actions:
  4428	                if isinstance(action, (exp.ColumnDef, exp.Schema)):
  4429	                    action_sql = self.add_column_sql(action)
  4430	                else:
  4431	                    action_sql = self.sql(action)
  4432	                    if isinstance(action, exp.Query):
  4433	                        action_sql = f"AS {action_sql}"
  4434	
  4435	                actions_list.append(action_sql)
  4436	
  4437	            actions_sql = self.format_args(*actions_list).lstrip("\n")
  4438	
  4439	        iceberg = (
  4440	            "ICEBERG "
  4441	            if expression.args.get("iceberg") and self.SUPPORTS_DROP_ALTER_ICEBERG_PROPERTY
  4442	            else ""
  4443	        )
  4444	        exists = " IF EXISTS" if expression.args.get("exists") else ""
  4445	        on_cluster = self.sql(expression, "cluster")
  4446	        on_cluster = f" {on_cluster}" if on_cluster else ""
  4447	        only = " ONLY" if expression.args.get("only") else ""
  4448	        options = self.expressions(expression, key="options")
  4449	        options = f", {options}" if options else ""
  4450	        kind = self.sql(expression, "kind")
  4451	        not_valid = " NOT VALID" if expression.args.get("not_valid") else ""
  4452	        check = " WITH CHECK" if expression.args.get("check") else ""
  4453	        cascade = (
  4454	            " CASCADE"
  4455	            if expression.args.get("cascade") and self.dialect.ALTER_TABLE_SUPPORTS_CASCADE
  4456	            else ""
    ... (5 more lines)

[sqlglot/generator.py lines 4468-4477: Generator.add_column_sql]
  4468	    def add_column_sql(self, expression: exp.Expr) -> str:
  4469	        sql = self.sql(expression)
  4470	        if isinstance(expression, exp.Schema):
  4471	            column_text = " COLUMNS"
  4472	        elif isinstance(expression, exp.ColumnDef) and self.ALTER_TABLE_INCLUDE_COLUMN_KEYWORD:
  4473	            column_text = " COLUMN"
  4474	        else:
  4475	            column_text = ""
  4476	
  4477	        return f"ADD{column_text} {sql}"

[sqlglot/generators/mysql.py lines 681-695: MySQLGenerator.datatype_sql]
   681	    def datatype_sql(self, expression: exp.DataType) -> str:
   682	        if (
   683	            self.VARCHAR_REQUIRES_SIZE
   684	            and expression.is_type(exp.DType.VARCHAR)
   685	            and not expression.expressions
   686	        ):
   687	            # `VARCHAR` must always have a size - if it doesn't, we always generate `TEXT`
   688	            return "TEXT"
   689	
   690	        # https://dev.mysql.com/doc/refman/8.0/en/numeric-type-syntax.html
   691	        result = super().datatype_sql(expression)
   692	        if expression.this in self.UNSIGNED_TYPE_MAPPING:
   693	            result = f"{result} UNSIGNED"
   694	
   695	        return result

[sqlglot/parser.py lines 1156-1187: Parser.<stmt@1156>]
  1156	    STATEMENT_PARSERS: t.ClassVar = {
  1157	        TokenType.ALTER: lambda self: self._parse_alter(),
  1158	        TokenType.ANALYZE: lambda self: self._parse_analyze(),
  1159	        TokenType.BEGIN: lambda self: self._parse_transaction(),
  1160	        TokenType.CACHE: lambda self: self._parse_cache(),
  1161	        TokenType.COMMENT: lambda self: self._parse_comment(),
  1162	        TokenType.COMMIT: lambda self: self._parse_commit_or_rollback(),
  1163	        TokenType.COPY: lambda self: self._parse_copy(),
  1164	        TokenType.CREATE: lambda self: self._parse_create(),
  1165	        TokenType.DECLARE: lambda self: self._parse_declare(),
  1166	        TokenType.DELETE: lambda self: self._parse_delete(),
  1167	        TokenType.DESC: lambda self: self._parse_describe(),
  1168	        TokenType.DESCRIBE: lambda self: self._parse_describe(),
  1169	        TokenType.DROP: lambda self: self._parse_drop(),
  1170	        TokenType.GRANT: lambda self: self._parse_grant(),
  1171	        TokenType.REVOKE: lambda self: self._parse_revoke(),
  1172	        TokenType.INSERT: lambda self: self._parse_insert(),
  1173	        TokenType.KILL: lambda self: self._parse_kill(),
  1174	        TokenType.LOAD: lambda self: self._parse_load(),
  1175	        TokenType.MERGE: lambda self: self._parse_merge(),
  1176	        TokenType.PIVOT: lambda self: self._parse_simplified_pivot(),
  1177	        TokenType.PRAGMA: lambda self: self.expression(exp.Pragma(this=self._parse_expression())),
  1178	        TokenType.REFRESH: lambda self: self._parse_refresh(),
  1179	        TokenType.ROLLBACK: lambda self: self._parse_commit_or_rollback(),
  1180	        TokenType.SET: lambda self: self._parse_set(),
  1181	        TokenType.TRUNCATE: lambda self: self._parse_truncate_table(),
  1182	        TokenType.UNCACHE: lambda self: self._parse_uncache(),
  1183	        TokenType.UNPIVOT: lambda self: self._parse_simplified_pivot(is_unpivot=True),
  1184	        TokenType.UPDATE: lambda self: self._parse_update(),
  1185	        TokenType.USE: lambda self: self._parse_use(),
  1186	        TokenType.SEMICOLON: lambda self: exp.Semicolon(),
  1187	    }

[sqlglot/parser.py lines 1510-1522: Parser.<stmt@1510>]
  1510	    ALTER_PARSERS: t.ClassVar = {
  1511	        "ADD": lambda self: self._parse_alter_table_add(),
  1512	        "AS": lambda self: self._parse_select(),
  1513	        "ALTER": lambda self: self._parse_alter_table_alter(),
  1514	        "CLUSTER BY": lambda self: self._parse_cluster_property(),
  1515	        "DELETE": lambda self: self.expression(exp.Delete(where=self._parse_where())),
  1516	        "DROP": lambda self: self._parse_alter_table_drop(),
  1517	        "RENAME": lambda self: self._parse_alter_table_rename(),
  1518	        "SET": lambda self: self._parse_alter_table_set(),
  1519	        "SWAP": lambda self: self.expression(
  1520	            exp.SwapTable(this=self._match(TokenType.WITH) and self._parse_table(schema=True))
  1521	        ),
  1522	    }

[sqlglot/parser.py lines 2288-2298: Parser._warn_unsupported]
  2288	    def _warn_unsupported(self) -> None:
  2289	        if self._tokens_size <= 1:
  2290	            return
  2291	
  2292	        # We use _find_sql because self.sql may comprise multiple chunks, and we're only
  2293	        # interested in emitting a warning for the one being currently processed.
  2294	        sql = self._find_sql(self._tokens[0], self._tokens[-1])[: self.error_message_context]
  2295	
  2296	        logger.warning(
  2297	            f"'{sql}' contains unsupported syntax. Falling back to parsing as a 'Command'."
  2298	        )

[sqlglot/parser.py lines 4933-4939: Parser._parse_table_part]
  4933	    def _parse_table_part(self, schema: bool = False) -> exp.Expr | None:
  4934	        return (
  4935	            (not schema and self._parse_function(optional_parens=False))
  4936	            or self._parse_id_var(any_token=False)
  4937	            or self._parse_string_as_identifier()
  4938	            or self._parse_placeholder()
  4939	        )

[sqlglot/parser.py lines 5322-5341: Parser._parse_derived_table_values]
  5322	    def _parse_derived_table_values(self, allow_value_synonym: bool = False) -> exp.Values | None:
  5323	        is_derived = self._match_pair(TokenType.L_PAREN, TokenType.VALUES)
  5324	        if not is_derived and not (
  5325	            # ClickHouse's `FORMAT Values` is equivalent to `VALUES`
  5326	            self._match_text_seq("VALUES")
  5327	            or self._match_text_seq("FORMAT", "VALUES")
  5328	            # MySQL accepts VALUE as a synonym for VALUES in INSERT statements.
  5329	            or (allow_value_synonym and self._match_text_seq("VALUE"))
  5330	        ):
  5331	            return None
  5332	
  5333	        expressions = self._parse_csv(self._parse_value)
  5334	        alias = self._parse_table_alias()
  5335	
  5336	        if is_derived:
  5337	            self._match_r_paren()
  5338	
  5339	        return self.expression(
  5340	            exp.Values(expressions=expressions, alias=alias or self._parse_table_alias())
  5341	        )

[sqlglot/parser.py lines 9162-9166: Parser._parse_add_column]
  9162	    def _parse_add_column(self) -> exp.ColumnDef | None:
  9163	        if not self._prev.text.upper() == "ADD":
  9164	            return None
  9165	
  9166	        return self._parse_column_def_with_exists()

[sqlglot/parser.py lines 9210-9249: Parser._parse_alter_table_add]
  9210	    def _parse_alter_table_add(self) -> list[exp.Expr]:
  9211	        def _parse_add_alteration() -> exp.Expr | None:
  9212	            self._match_text_seq("ADD")
  9213	            if self._match_set(self.ADD_CONSTRAINT_TOKENS, advance=False) or self._match_texts(
  9214	                self.ADD_CONSTRAINT_KEYWORDS, advance=False
  9215	            ):
  9216	                return self.expression(
  9217	                    exp.AddConstraint(expressions=self._parse_csv(self._parse_constraint))
  9218	                )
  9219	
  9220	            column_def = self._parse_add_column()
  9221	            if isinstance(column_def, exp.ColumnDef):
  9222	                return column_def
  9223	
  9224	            exists = self._parse_exists(not_=True)
  9225	            if self._match_pair(TokenType.PARTITION, TokenType.L_PAREN, advance=False):
  9226	                return self.expression(
  9227	                    exp.AddPartition(
  9228	                        exists=exists,
  9229	                        this=self._parse_field(any_token=True),
  9230	                        location=self._match_text_seq("LOCATION", advance=False)
  9231	                        and self._parse_property(),
  9232	                    )
  9233	                )
  9234	
  9235	            return None
  9236	
  9237	        if not self._match_set(self.ADD_CONSTRAINT_TOKENS, advance=False) and (
  9238	            not self.dialect.ALTER_TABLE_ADD_REQUIRED_FOR_EACH_COLUMN
  9239	            or self._match_text_seq("COLUMNS")
  9240	        ):
  9241	            schema = self._parse_schema()
  9242	
  9243	            return (
  9244	                ensure_list(schema)
  9245	                if schema
  9246	                else self._parse_csv(self._parse_column_def_with_exists)
  9247	            )
  9248	
  9249	        return self._parse_csv(_parse_add_alteration)

[sqlglot/parser.py lines 9406-9472: Parser._parse_alter]
  9406	    def _parse_alter(self) -> exp.Alter | exp.Command:
  9407	        start = self._prev
  9408	
  9409	        iceberg = self._match_text_seq("ICEBERG")
  9410	
  9411	        alter_token = self._match_set(self.ALTERABLES) and self._prev
  9412	        if not alter_token:
  9413	            return self._parse_as_command(start)
  9414	        if iceberg and alter_token.token_type != TokenType.TABLE:
  9415	            return self._parse_as_command(start)
  9416	
  9417	        exists = self._parse_exists()
  9418	        only = self._match_text_seq("ONLY")
  9419	
  9420	        if alter_token.token_type == TokenType.SESSION:
  9421	            this = None
  9422	            check = None
  9423	            cluster = None
  9424	        else:
  9425	            this = self._parse_table(schema=True, parse_partition=self.ALTER_TABLE_PARTITIONS)
  9426	            check = self._match_text_seq("WITH", "CHECK")
  9427	            cluster = self._parse_on_property() if self._match(TokenType.ON) else None
  9428	
  9429	            if self._next:
  9430	                self._advance()
  9431	
  9432	        parser = self.ALTER_PARSERS.get(self._prev.text.upper()) if self._prev else None
  9433	        actions = ensure_list(parser(self)) if parser else None
  9434	        if actions:
  9435	            # More actions of a different kind may follow, e.g. ADD COLUMN a INT, DROP COLUMN b.
  9436	            # The comma before them may have already been consumed by the previous action's parser
  9437	            while (
  9438	                self.ALTER_TABLE_MIXED_ACTIONS
  9439	                and (self._match(TokenType.COMMA) or self._prev.token_type == TokenType.COMMA)
  9440	                and not self._match_texts(self.PROPERTY_PARSERS, advance=False)
  9441	                and self._match_texts(self.ALTER_PARSERS)
  9442	            ):
  9443	                parser = self.ALTER_PARSERS[self._prev.text.upper()]
  9444	                parsed = ensure_list(self._try_parse(lambda: parser(self)))
  9445	                if not parsed or any(isinstance(action, exp.Command) for action in parsed):
    ... (27 more lines)

[sqlglot/parser.py lines 9809-9815: Parser._parse_as_command]
  9809	    def _parse_as_command(self, start: Token) -> exp.Command:
  9810	        while self._curr:
  9811	            self._advance()
  9812	        text = self._find_sql(start, self._prev)
  9813	        size = len(start.text)
  9814	        self._warn_unsupported()
  9815	        return exp.Command(this=text[:size], expression=text[size:])

[sqlglot/parsers/mysql.py lines 251-257: MySQLParser.<stmt@251>]
   251	    ALTER_PARSERS = {
   252	        **parser.Parser.ALTER_PARSERS,
   253	        "CHANGE": lambda self: self._parse_alter_table_modify(rename=True),
   254	        "MODIFY": lambda self: self._parse_alter_table_modify(),
   255	        "AUTO_INCREMENT": lambda self: self._parse_property_assignment(exp.AutoIncrementProperty),
   256	        "COMMENT": lambda self: self._parse_property_assignment(exp.SchemaCommentProperty),
   257	    }

[sqlglot/parsers/mysql.py lines 309-315: MySQLParser._parse_column_constraint]
   309	    def _parse_column_constraint(self) -> exp.Expr | None:
   310	        # SIGNED is the default for numeric types, so MySQL ignores it
   311	        self._match_text_seq("SIGNED")
   312	        if self._match(TokenType.KEY):
   313	            return self.expression(exp.ColumnConstraint(kind=self._parse_primary_key()))
   314	
   315	        return super()._parse_column_constraint()

[grep -nw KEY_BLOCK_SIZE sqlglot/]
sqlglot/generator.py:5078:            return f"KEY_BLOCK_SIZE = {key_block_size}"
sqlglot/parsers/mysql.py:440:            if self._match_text_seq("KEY_BLOCK_SIZE"):

[grep -nw ROW_FORMAT sqlglot/]
sqlglot/expressions/properties.py:621:        "ROW_FORMAT": RowFormatProperty,
sqlglot/parser.py:1387:        "ROW_FORMAT": lambda self: self._parse_property_assignment(exp.RowFormatProperty),

[grep -nw Comment sqlglot/]
sqlglot/expressions/ddl.py:307:class Comment(Expression):
sqlglot/generator.py:4256:    def comment_sql(self, expression: exp.Comment) -> str:
sqlglot/parser.py:2331:            exp.Comment(

[grep -nw ENGINE sqlglot/]
sqlglot/expressions/properties.py:613:        "ENGINE": EngineProperty,
sqlglot/generators/mysql.py:754:        if expression.name == "ENGINE":
sqlglot/parser.py:1338:        "ENGINE": lambda self: self._parse_property_assignment(exp.EngineProperty),
sqlglot/parsers/clickhouse.py:422:        "ENGINE": lambda self: self._parse_engine_property(),
sqlglot/parsers/mysql.py:185:        "ENGINE": _show_parser("ENGINE", target=True),

[grep -nw FORCE sqlglot/]
sqlglot/dialects/duckdb.py:98:            "FORCE": TokenType.FORCE,
sqlglot/dialects/mysql.py:102:            "FORCE": TokenType.FORCE,
sqlglot/generator.py:299:        exp.ForceProperty: lambda *_: "FORCE",
sqlglot/generator.py:1892:        force = " FORCE" if expression.args.get("force") else ""
sqlglot/generators/duckdb.py:2698:        force = "FORCE " if expression.args.get("force") else ""
sqlglot/parser.py:1760:    TABLE_INDEX_HINT_TOKENS: t.ClassVar = {TokenType.FORCE, TokenType.IGNORE, TokenType.USE}
sqlglot/parser.py:2493:                force=self._match_text_seq("FORCE"),
sqlglot/parsers/duckdb.py:240:        TokenType.FORCE: lambda self: self._parse_force(),
sqlglot/parsers/duckdb.py:393:        # FORCE can only be followed by INSTALL or CHECKPOINT
sqlglot/parsers/oracle.py:75:        "FORCE": lambda self: self.expression(exp.ForceProperty()),
sqlglot/parsers/tsql.py:79:    "FORCE": ("EXTERNALPUSHDOWN", "ORDER", "SCALEOUTEXECUTION"),
sqlglot/tokenizer_core.py:303:    FORCE = auto()

[grep -nw Drop sqlglot/]
sqlglot/expressions/ddl.py:346:class Drop(Expression):
sqlglot/generator.py:834:        exp.Drop,
sqlglot/generator.py:1870:    def drop_sql(self, expression: exp.Drop) -> str:
sqlglot/generators/athena.py:61:    elif isinstance(expression, (exp.Alter, exp.Drop, exp.Describe, exp.Show)):
sqlglot/generators/athena.py:62:        if isinstance(expression, exp.Drop) and expression.kind == "VIEW":
sqlglot/generators/spark.py:206:                and isinstance(drop := true_block.expressions[0], exp.Drop)
sqlglot/generators/tsql.py:664:    def drop_sql(self, expression: exp.Drop) -> str:
sqlglot/parser.py:2423:    def _parse_drop(self, exists: bool = False, kind: str | None = None) -> exp.Drop | exp.Command:
sqlglot/parser.py:2478:            exp.Drop(
sqlglot/parser.py:9168:    def _parse_drop_column(self) -> exp.Drop | exp.Command | None:
sqlglot/parser.py:9195:            isinstance(drop, exp.Drop)
sqlglot/parsers/spark2.py:120:    def _parse_drop_column(self) -> exp.Drop | exp.Command | None:
sqlglot/parsers/spark2.py:122:            self.expression(exp.Drop(tables=[self._parse_schema()], kind="COLUMNS"))
sqlglot/tokenizer_core.py:1043:            self._add(TokenType.BIT_STRING, value[2:])  # Drop the 0b
sqlglot/tokenizer_core.py:1053:            self._add(TokenType.HEX_STRING, value[2:])  # Drop the 0x

[grep -nw Alter sqlglot/]
sqlglot/expressions/builders.py:47:from sqlglot.expressions.ddl import Alter, AlterRename, RenameColumn
sqlglot/expressions/builders.py:606:) -> Alter:
sqlglot/expressions/builders.py:615:        Alter table expression
sqlglot/expressions/builders.py:619:    return Alter(
sqlglot/expressions/builders.py:634:) -> Alter:
sqlglot/expressions/builders.py:645:        Alter table expression
sqlglot/expressions/builders.py:650:    return Alter(
sqlglot/expressions/ddl.py:399:class Alter(Expression):
sqlglot/generator.py:4417:    def alter_sql(self, expression: exp.Alter) -> str:
sqlglot/generators/athena.py:61:    elif isinstance(expression, (exp.Alter, exp.Drop, exp.Describe, exp.Show)):
sqlglot/generators/athena.py:103:    def alter_sql(self, expression: exp.Alter) -> str:
sqlglot/generators/athena.py:104:        if isinstance(expression, exp.Alter) and expression.kind == "TABLE":
sqlglot/generators/tsql.py:658:    def alter_sql(self, expression: exp.Alter) -> str:
sqlglot/parser.py:1919:    # Whether Alter statements are allowed to contain Partition specifications
sqlglot/parser.py:9406:    def _parse_alter(self) -> exp.Alter | exp.Command:
sqlglot/parser.py:9457:                    exp.Alter(

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert
- tests.dialects.test_bigquery
- tests.test_executor
- tests.test_optimizer
- Cause: the pytz module is not installed in this environment. These exist before any change and are not caused by your work.
