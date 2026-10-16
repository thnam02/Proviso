[grep 'EXTERNAL|Command|def _parse_create|def _parse_as_command|USING' in sqlglot/dialects/athena.py]
30:        - CREATE [EXTERNAL] TABLE (without AS SELECT)
104:        if second_text in ("DATABASE", "EXTERNAL", "SCHEMA"):

[grep 'def _parse_create|def _parse_as_command' in sqlglot]
sqlglot/parsers/snowflake.py:1058:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/starrocks.py:108:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/tsql.py:823:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parser.py:2510:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parser.py:3526:    def _parse_create_like(self) -> exp.LikeProperty | None:
sqlglot/parser.py:9871:    def _parse_as_command(self, start: Token) -> exp.Command:
sqlglot/parsers/fabric.py:8:    def _parse_create(self) -> exp.Create | exp.Command:

Note: `-r` was ignored: Grep always searches a directory recursively.

[read sqlglot/parser.py lines 2510-2719]
2510	    def _parse_create(self) -> exp.Create | exp.Command:
2511	        # Note: this can't be None because we've matched a statement parser
2512	        start = self._prev
2513	
2514	        replace = (
2515	            start.token_type == TokenType.REPLACE
2516	            or self._match_pair(TokenType.OR, TokenType.REPLACE)
2517	            or self._match_pair(TokenType.OR, TokenType.ALTER)
2518	        )
2519	        refresh = self._match_pair(TokenType.OR, TokenType.REFRESH)
2520	
2521	        unique = self._match(TokenType.UNIQUE)
2522	
2523	        if self._match_text_seq("CLUSTERED", "COLUMNSTORE"):
2524	            clustered = True
2525	        elif self._match_text_seq("NONCLUSTERED", "COLUMNSTORE") or self._match_text_seq(
2526	            "COLUMNSTORE"
2527	        ):
2528	            clustered = False
2529	        else:
2530	            clustered = None
2531	
2532	        if self._match_pair(TokenType.TABLE, TokenType.FUNCTION, advance=False):
2533	            self._advance()
2534	
2535	        properties = None
2536	        create_token = self._match_set(self.CREATABLES) and self._prev
2537	
2538	        if not create_token:
2539	            # exp.Properties.Location.POST_CREATE
2540	            properties = self._parse_properties()
2541	            create_token = self._match_set(self.CREATABLES) and self._prev
2542	
2543	            if not properties or not create_token:
2544	                return self._parse_as_command(start)
2545	
2546	        create_token_type = t.cast(Token, create_token).token_type
2547	
2548	        concurrently = self._match_text_seq("CONCURRENTLY")
2549	        exists = self._parse_exists(not_=True)
2550	        this = None
2551	        expression: exp.Expr | None = None
2552	        indexes = None
2553	        no_schema_binding = None
2554	        begin = None
2555	        clone = None
2556	
2557	        def extend_props(temp_props: exp.Properties | None) -> None:
2558	            nonlocal properties
2559	            if properties and temp_props:
2560	                properties.expressions.extend(temp_props.expressions)
2561	            elif temp_props:
2562	                properties = temp_props
2563	
2564	        if create_token_type in (TokenType.FUNCTION, TokenType.PROCEDURE):
2565	            this = self._parse_user_defined_function(kind=create_token_type)
2566	
2567	            # exp.Properties.Location.POST_SCHEMA ("schema" here is the UDF's type signature)
2568	            extend_props(self._parse_properties())
2569	
2570	            expression = self._parse_heredoc() if self._match(TokenType.ALIAS) else None
2571	
2572	            if (
2573	                not expression
2574	                and create_token_type == TokenType.FUNCTION
2575	                and isinstance(this, exp.UserDefinedFunction)
2576	                and this.args.get("wrapped")
2577	            ):
2578	                pre_table_index = self._index
2579	                is_table = self._match(TokenType.TABLE)
2580	
2581	                expression = self._parse_expression()
2582	                overload_mode = bool(
2583	                    expression
2584	                    and self._curr.token_type == TokenType.COMMA
2585	                    and self._next.token_type == TokenType.L_PAREN
2586	                )
2587	                if not overload_mode:
2588	                    self._retreat(pre_table_index)
2589	                    is_table = False
2590	                    expression = None
2591	            else:
2592	                is_table = False
2593	                overload_mode = False
2594	
2595	            extend_props(self._parse_function_properties())
2596	
2597	            if not expression:
2598	                if self._match(TokenType.COMMAND):
2599	                    expression = self._parse_as_command(self._prev)
2600	                else:
2601	                    begin = self._match(TokenType.BEGIN)
2602	                    return_ = self._match_text_seq("RETURN")
2603	
2604	                    if self._match(TokenType.STRING, advance=False):
2605	                        # Takes care of BigQuery's JavaScript UDF definitions that end in an OPTIONS property
2606	                        # # https://cloud.google.com/bigquery/docs/reference/standard-sql/data-definition-language#create_function_statement
2607	                        expression = self._parse_string()
2608	                        extend_props(self._parse_properties())
2609	                    else:
2610	                        expression = (
2611	                            self._parse_user_defined_function_expression()
2612	                            if create_token_type == TokenType.FUNCTION
2613	                            else self._parse_block()
2614	                        )
2615	
2616	                    if return_:
2617	                        expression = self.expression(exp.Return(this=expression))
2618	
2619	            if overload_mode and expression:
2620	                expression = self._parse_macro_overloads(
2621	                    t.cast(exp.UserDefinedFunction, this), expression, is_table
2622	                )
2623	        elif create_token_type == TokenType.INDEX:
2624	            # Postgres allows anonymous indexes, eg. CREATE INDEX IF NOT EXISTS ON t(c)
2625	            if not self._match(TokenType.ON):
2626	                index = self._parse_id_var()
2627	                anonymous = False
2628	            else:
2629	                index = None
2630	                anonymous = True
2631	
2632	            this = self._parse_index(index=index, anonymous=anonymous)
2633	        elif (
2634	            create_token_type == TokenType.CONSTRAINT and self._match(TokenType.TRIGGER)
2635	        ) or create_token_type == TokenType.TRIGGER:
2636	            if is_constraint := (create_token_type == TokenType.CONSTRAINT):
2637	                create_token = self._prev
2638	
2639	            trigger_name = self._parse_id_var()
2640	            if not trigger_name:
2641	  
… (3714 more characters)

[read sqlglot/dialects/athena.py]
1	from __future__ import annotations
2	
3	
4	from sqlglot import tokens
5	from sqlglot.dialects.dialect import DialectType
6	from sqlglot.generators.athena import AthenaGenerator
7	from sqlglot.parsers.athena import AthenaParser
8	from sqlglot.tokens import TokenType, Token
9	from sqlglot.dialects.trino import Trino
10	from sqlglot.dialects.hive import Hive
11	
12	
13	class Athena(Trino):
14	    """
15	    Over the years, it looks like AWS has taken various execution engines, bolted on AWS-specific
16	    modifications and then built the Athena service around them.
17	
18	    Thus, Athena is not simply hosted Trino, it's more like a router that routes SQL queries to an
19	    execution engine depending on the query type.
20	
21	    As at 2024-09-10, assuming your Athena workgroup is configured to use "Athena engine version 3",
22	    the following engines exist:
23	
24	    Hive:
25	     - Accepts mostly the same syntax as Hadoop / Hive
26	     - Uses backticks to quote identifiers
27	     - Has a distinctive DDL syntax (around things like setting table properties, storage locations etc)
28	       that is different from Trino
29	     - Used for *most* DDL, with some exceptions that get routed to the Trino engine instead:
30	        - CREATE [EXTERNAL] TABLE (without AS SELECT)
31	        - ALTER
32	        - DROP
33	
34	    Trino:
35	      - Uses double quotes to quote identifiers
36	      - Used for DDL operations that involve SELECT queries, eg:
37	        - CREATE VIEW / DROP VIEW
38	        - CREATE TABLE... AS SELECT
39	      - Used for DML operations
40	        - SELECT, INSERT, UPDATE, DELETE, MERGE
41	
42	    The SQLGlot Athena dialect tries to identify which engine a query would be routed to and then uses the
43	    tokenizer / parser / generator for that engine. This is unfortunately necessary, as there are certain
44	    incompatibilities between the engines' dialects and thus can't be handled by a single, unifying dialect.
45	
46	    References:
47	    - https://docs.aws.amazon.com/athena/latest/ug/ddl-reference.html
48	    - https://docs.aws.amazon.com/athena/latest/ug/dml-queries-functions-operators.html
49	    """
50	
51	    # This Tokenizer consumes a combination of HiveQL and Trino SQL and then processes the tokens
52	    # to disambiguate which dialect needs to be actually used in order to tokenize correctly.
53	    class Tokenizer(tokens.Tokenizer):
54	        IDENTIFIERS = Trino.Tokenizer.IDENTIFIERS + Hive.Tokenizer.IDENTIFIERS
55	        STRING_ESCAPES = Trino.Tokenizer.STRING_ESCAPES + Hive.Tokenizer.STRING_ESCAPES
56	        HEX_STRINGS = Trino.Tokenizer.HEX_STRINGS + Hive.Tokenizer.HEX_STRINGS
57	        UNICODE_STRINGS = Trino.Tokenizer.UNICODE_STRINGS + Hive.Tokenizer.UNICODE_STRINGS
58	
59	        NUMERIC_LITERALS = {
60	            **Trino.Tokenizer.NUMERIC_LITERALS,
61	            **Hive.Tokenizer.NUMERIC_LITERALS,
62	        }
63	
64	        KEYWORDS = {
65	            **Hive.Tokenizer.KEYWORDS,
66	            **Trino.Tokenizer.KEYWORDS,
67	            "UNLOAD": TokenType.COMMAND,
68	        }
69	
70	        def __init__(self, dialect: DialectType = None) -> None:
71	            super().__init__(dialect=dialect)
72	
73	            self._hive_tokenizer = Hive().tokenizer()
74	            self._trino_tokenizer = _TrinoTokenizer(Trino())
75	
76	        def tokenize(self, sql: str) -> list[Token]:
77	            tokens = super().tokenize(sql)
78	
79	            if _tokenize_as_hive(tokens):
80	                return [Token(TokenType.HIVE_TOKEN_STREAM, "")] + self._hive_tokenizer.tokenize(sql)
81	
82	            return self._trino_tokenizer.tokenize(sql)
83	
84	    Parser = AthenaParser
85	
86	    Generator = AthenaGenerator
87	
88	
89	def _tokenize_as_hive(tokens: list[Token]) -> bool:
90	    if len(tokens) < 2:
91	        return False
92	
93	    first, second, *rest = tokens
94	
95	    first_type = first.token_type
96	    first_text = first.text.upper()
97	    second_type = second.token_type
98	    second_text = second.text.upper()
99	
100	    if first_type in (TokenType.DESCRIBE, TokenType.SHOW) or first_text == "MSCK REPAIR":
101	        return True
102	
103	    if first_type in (TokenType.ALTER, TokenType.CREATE, TokenType.DROP):
104	        if second_text in ("DATABASE", "EXTERNAL", "SCHEMA"):
105	            return True
106	        if second_type == TokenType.VIEW:
107	            return False
108	
109	        return all(t.token_type != TokenType.SELECT for t in rest)
110	
111	    return False
112	
113	
114	# Athena extensions to Trino's tokenizer
115	class _TrinoTokenizer(Trino.Tokenizer):
116	    KEYWORDS = {
117	        **Trino.Tokenizer.KEYWORDS,
118	        "UNLOAD": TokenType.COMMAND,
119	    }
120

[read sqlglot/parser.py lines 2719-2808]
2719	                if props:
2720	                    sequence_props = exp.SequenceProperties()
2721	                    options = []
2722	                    for prop in props:
2723	                        if isinstance(prop, exp.SequenceProperties):
2724	                            for arg, value in prop.args.items():
2725	                                if arg == "options":
2726	                                    options.extend(value)
2727	                                else:
2728	                                    sequence_props.set(arg, value)
2729	                            prop.pop()
2730	
2731	                    if options:
2732	                        sequence_props.set("options", options)
2733	
2734	                    props.append("expressions", sequence_props)
2735	                    extend_props(props)
2736	            else:
2737	                expression = self._parse_ddl_select()
2738	
2739	                # Some dialects also support using a table as an alias instead of a SELECT.
2740	                # Here we fallback to this as an alternative.
2741	                if not expression and has_alias:
2742	                    expression = self._try_parse(self._parse_table_parts)
2743	
2744	            if create_token_type == TokenType.TABLE:
2745	                # exp.Properties.Location.POST_EXPRESSION
2746	                extend_props(self._parse_properties())
2747	
2748	                indexes = []
2749	                while True:
2750	                    index = self._parse_index()
2751	
2752	                    # exp.Properties.Location.POST_INDEX
2753	                    extend_props(self._parse_properties())
2754	                    if not index:
2755	                        break
2756	                    else:
2757	                        self._match(TokenType.COMMA)
2758	                        indexes.append(index)
2759	            elif create_token_type == TokenType.VIEW:
2760	                if self._match_text_seq("WITH", "NO", "SCHEMA", "BINDING"):
2761	                    no_schema_binding = True
2762	            elif create_token_type in (TokenType.SINK, TokenType.SOURCE):
2763	                extend_props(self._parse_properties())
2764	
2765	            shallow = self._match_text_seq("SHALLOW")
2766	
2767	            if self._match_texts(self.CLONE_KEYWORDS):
2768	                copy = self._prev.text.lower() == "copy"
2769	                clone = self.expression(
2770	                    exp.Clone(this=self._parse_table(schema=True), shallow=shallow, copy=copy)
2771	                )
2772	
2773	        if self._curr and not self._match_set((TokenType.R_PAREN, TokenType.COMMA), advance=False):
2774	            return self._parse_as_command(start)
2775	
2776	        create_kind_text = create_token.text.upper()
2777	        return self.expression(
2778	            exp.Create(
2779	                this=this,
2780	                kind=self.dialect.CREATABLE_KIND_MAPPING.get(create_kind_text) or create_kind_text,
2781	                replace=replace,
2782	                refresh=refresh,
2783	                unique=unique,
2784	                expression=expression,
2785	                exists=exists,
2786	                properties=properties,
2787	                indexes=indexes,
2788	                no_schema_binding=no_schema_binding,
2789	                begin=begin,
2790	                clone=clone,
2791	                concurrently=concurrently,
2792	                clustered=clustered,
2793	            )
2794	        )
2795	
2796	    def _parse_sequence_properties(self) -> exp.SequenceProperties | None:
2797	        seq = exp.SequenceProperties()
2798	
2799	        options = []
2800	        index = self._index
2801	
2802	        while self._curr:
2803	            self._match(TokenType.COMMA)
2804	            if self._match_text_seq("INCREMENT"):
2805	                self._match_text_seq("BY")
2806	                self._match_text_seq("=")
2807	                seq.set("increment", self._parse_term())
2808	            elif self._match_text_seq("MINVALUE"):

[read sqlglot/parsers/athena.py]
1	from __future__ import annotations
2	
3	import typing as t
4	
5	from sqlglot import exp
6	from sqlglot.errors import ErrorLevel
7	from sqlglot.parsers.trino import TrinoParser
8	from sqlglot.tokens import TokenType, Token
9	
10	if t.TYPE_CHECKING:
11	    from sqlglot.dialects.dialect import DialectType
12	    from sqlglot.dialects.hive import Hive
13	    from sqlglot.dialects.trino import Trino
14	
15	
16	class AthenaTrinoParser(TrinoParser):
17	    STATEMENT_PARSERS = {
18	        **TrinoParser.STATEMENT_PARSERS,
19	        TokenType.USING: lambda self: self._parse_as_command(self._prev),
20	    }
21	
22	
23	class AthenaParser(AthenaTrinoParser):
24	    def __init__(
25	        self,
26	        error_level: ErrorLevel | None = None,
27	        error_message_context: int = 100,
28	        max_errors: int = 3,
29	        max_nodes: int = -1,
30	        dialect: DialectType = None,
31	        hive: Hive | None = None,
32	        trino: Trino | None = None,
33	    ) -> None:
34	        from sqlglot.dialects.hive import Hive
35	        from sqlglot.dialects.trino import Trino
36	
37	        hive = hive or Hive()
38	        trino = trino or Trino()
39	
40	        super().__init__(
41	            error_level=error_level,
42	            error_message_context=error_message_context,
43	            max_errors=max_errors,
44	            max_nodes=max_nodes,
45	            dialect=dialect,
46	        )
47	
48	        self._hive_parser = hive.parser(
49	            error_level=error_level,
50	            error_message_context=error_message_context,
51	            max_errors=max_errors,
52	            max_nodes=max_nodes,
53	        )
54	        self._trino_parser = AthenaTrinoParser(
55	            error_level=error_level,
56	            error_message_context=error_message_context,
57	            max_errors=max_errors,
58	            max_nodes=max_nodes,
59	            dialect=trino,
60	        )
61	
62	    def parse(self, raw_tokens: list[Token], sql: str) -> list[exp.Expr | None]:
63	        if raw_tokens and raw_tokens[0].token_type == TokenType.HIVE_TOKEN_STREAM:
64	            return self._hive_parser.parse(raw_tokens[1:], sql)
65	
66	        return self._trino_parser.parse(raw_tokens, sql)
67	
68	    def parse_into(
69	        self,
70	        expression_types: exp.IntoType,
71	        raw_tokens: list[Token],
72	        sql: str | None = None,
73	    ) -> list[exp.Expr | None]:
74	        if raw_tokens and raw_tokens[0].token_type == TokenType.HIVE_TOKEN_STREAM:
75	            return self._hive_parser.parse_into(expression_types, raw_tokens[1:], sql)
76	
77	        return self._trino_parser.parse_into(expression_types, raw_tokens, sql)
78

[read sqlglot/parser.py lines 9871-9895]
9871	    def _parse_as_command(self, start: Token) -> exp.Command:
9872	        while self._curr:
9873	            self._advance()
9874	        text = self._find_sql(start, self._prev)
9875	        size = len(start.text)
9876	        self._warn_unsupported()
9877	        return exp.Command(this=text[:size], expression=text[size:])
9878	
9879	    def _parse_dict_property(self, this: str) -> exp.DictProperty:
9880	        settings = []
9881	
9882	        self._match_l_paren()
9883	        kind = self._parse_id_var()
9884	
9885	        if self._match(TokenType.L_PAREN):
9886	            while True:
9887	                key = self._parse_id_var()
9888	                value = self._parse_function() or self._parse_primary_or_var()
9889	                if not key and value is None:
9890	                    break
9891	                settings.append(self.expression(exp.DictSubProperty(this=key, value=value)))
9892	            self._match(TokenType.R_PAREN)
9893	
9894	        self._match_r_paren()
9895

[grep 'def _parse_ddl_select' in sqlglot]
sqlglot/parser.py:9130:    def _parse_ddl_select(self) -> exp.Expr | None:
sqlglot/parser.py-9131-        return self._parse_query_modifiers(
sqlglot/parser.py-9132-            self._parse_set_operations(self._parse_select(nested=True, parse_subquery_alias=False))
sqlglot/parser.py-9133-        )
sqlglot/parser.py-9134-
sqlglot/parser.py-9135-    def _parse_transaction(self) -> exp.Transaction | exp.Command:
sqlglot/parser.py-9136-        this = None
sqlglot/parser.py-9137-        if self._match_texts(self.TRANSACTION_KIND):
sqlglot/parser.py-9138-            this = self._prev.text

[grep 'EXTERNAL|Command|def _parse_create|class Parser' in sqlglot/dialects/athena.py]
30:        - CREATE [EXTERNAL] TABLE (without AS SELECT)
104:        if second_text in ("DATABASE", "EXTERNAL", "SCHEMA"):

[grep 'def _parse_create\\b' in sqlglot]
sqlglot/parser.py:2510:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/snowflake.py:1058:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/starrocks.py:108:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/tsql.py:823:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/fabric.py:8:    def _parse_create(self) -> exp.Create | exp.Command:

[read sqlglot/parser.py lines 2510-2739]
2510	    def _parse_create(self) -> exp.Create | exp.Command:
2511	        # Note: this can't be None because we've matched a statement parser
2512	        start = self._prev
2513	
2514	        replace = (
2515	            start.token_type == TokenType.REPLACE
2516	            or self._match_pair(TokenType.OR, TokenType.REPLACE)
2517	            or self._match_pair(TokenType.OR, TokenType.ALTER)
2518	        )
2519	        refresh = self._match_pair(TokenType.OR, TokenType.REFRESH)
2520	
2521	        unique = self._match(TokenType.UNIQUE)
2522	
2523	        if self._match_text_seq("CLUSTERED", "COLUMNSTORE"):
2524	            clustered = True
2525	        elif self._match_text_seq("NONCLUSTERED", "COLUMNSTORE") or self._match_text_seq(
2526	            "COLUMNSTORE"
2527	        ):
2528	            clustered = False
2529	        else:
2530	            clustered = None
2531	
2532	        if self._match_pair(TokenType.TABLE, TokenType.FUNCTION, advance=False):
2533	            self._advance()
2534	
2535	        properties = None
2536	        create_token = self._match_set(self.CREATABLES) and self._prev
2537	
2538	        if not create_token:
2539	            # exp.Properties.Location.POST_CREATE
2540	            properties = self._parse_properties()
2541	            create_token = self._match_set(self.CREATABLES) and self._prev
2542	
2543	            if not properties or not create_token:
2544	                return self._parse_as_command(start)
2545	
2546	        create_token_type = t.cast(Token, create_token).token_type
2547	
2548	        concurrently = self._match_text_seq("CONCURRENTLY")
2549	        exists = self._parse_exists(not_=True)
2550	        this = None
2551	        expression: exp.Expr | None = None
2552	        indexes = None
2553	        no_schema_binding = None
2554	        begin = None
2555	        clone = None
2556	
2557	        def extend_props(temp_props: exp.Properties | None) -> None:
2558	            nonlocal properties
2559	            if properties and temp_props:
2560	                properties.expressions.extend(temp_props.expressions)
2561	            elif temp_props:
2562	                properties = temp_props
2563	
2564	        if create_token_type in (TokenType.FUNCTION, TokenType.PROCEDURE):
2565	            this = self._parse_user_defined_function(kind=create_token_type)
2566	
2567	            # exp.Properties.Location.POST_SCHEMA ("schema" here is the UDF's type signature)
2568	            extend_props(self._parse_properties())
2569	
2570	            expression = self._parse_heredoc() if self._match(TokenType.ALIAS) else None
2571	
2572	            if (
2573	                not expression
2574	                and create_token_type == TokenType.FUNCTION
2575	                and isinstance(this, exp.UserDefinedFunction)
2576	                and this.args.get("wrapped")
2577	            ):
2578	                pre_table_index = self._index
2579	                is_table = self._match(TokenType.TABLE)
2580	
2581	                expression = self._parse_expression()
2582	                overload_mode = bool(
2583	                    expression
2584	                    and self._curr.token_type == TokenType.COMMA
2585	                    and self._next.token_type == TokenType.L_PAREN
2586	                )
2587	                if not overload_mode:
2588	                    self._retreat(pre_table_index)
2589	                    is_table = False
2590	                    expression = None
2591	            else:
2592	                is_table = False
2593	                overload_mode = False
2594	
2595	            extend_props(self._parse_function_properties())
2596	
2597	            if not expression:
2598	                if self._match(TokenType.COMMAND):
2599	                    expression = self._parse_as_command(self._prev)
2600	                else:
2601	                    begin = self._match(TokenType.BEGIN)
2602	                    return_ = self._match_text_seq("RETURN")
2603	
2604	                    if self._match(TokenType.STRING, advance=False):
2605	                        # Takes care of BigQuery's JavaScript UDF definitions that end in an OPTIONS property
2606	                        # # https://cloud.google.com/bigquery/docs/reference/standard-sql/data-definition-language#create_function_statement
2607	                        expression = self._parse_string()
2608	                        extend_props(self._parse_properties())
2609	                    else:
2610	                        expression = (
2611	                            self._parse_user_defined_function_expression()
2612	                            if create_token_type == TokenType.FUNCTION
2613	                            else self._parse_block()
2614	                        )
2615	
2616	                    if return_:
2617	                        expression = self.expression(exp.Return(this=expression))
2618	
2619	            if overload_mode and expression:
2620	                expression = self._parse_macro_overloads(
2621	                    t.cast(exp.UserDefinedFunction, this), expression, is_table
2622	                )
2623	        elif create_token_type == TokenType.INDEX:
2624	            # Postgres allows anonymous indexes, eg. CREATE INDEX IF NOT EXISTS ON t(c)
2625	            if not self._match(TokenType.ON):
2626	                index = self._parse_id_var()
2627	                anonymous = False
2628	            else:
2629	                index = None
2630	                anonymous = True
2631	
2632	            this = self._parse_index(index=index, anonymous=anonymous)
2633	        elif (
2634	            create_token_type == TokenType.CONSTRAINT and self._match(TokenType.TRIGGER)
2635	        ) or create_token_type == TokenType.TRIGGER:
2636	            if is_constraint := (create_token_type == TokenType.CONSTRAINT):
2637	                create_token = self._prev
2638	
2639	            trigger_name = self._parse_id_var()
2640	            if not trigger_name:
2641	  
… (4703 more characters)

$ grep -n "def _parse_ddl_select" -A12 sqlglot/parser.py; grep -n "def _parse_as_command" -A15 sqlglot/parser.py; python -c "
from sqlglot import tokenize
for t in tokenize('CREATE TABLE t AS USING EXTERNAL FUNCTION f(x VARCHAR) RETURNS VARCHAR LAMBDA \'l\' SELECT f(1)',read='athena'):print(t.token_type,t.text)"
9130:    def _parse_ddl_select(self) -> exp.Expr | None:
9131-        return self._parse_query_modifiers(
9132-            self._parse_set_operations(self._parse_select(nested=True, parse_subquery_alias=False))
9133-        )
9134-
9135-    def _parse_transaction(self) -> exp.Transaction | exp.Command:
9136-        this = None
9137-        if self._match_texts(self.TRANSACTION_KIND):
9138-            this = self._prev.text
9139-
9140-        self._match_texts(("TRANSACTION", "WORK"))
9141-
9142-        modes = []
9871:    def _parse_as_command(self, start: Token) -> exp.Command:
9872-        while self._curr:
9873-            self._advance()
9874-        text = self._find_sql(start, self._prev)
9875-        size = len(start.text)
9876-        self._warn_unsupported()
9877-        return exp.Command(this=text[:size], expression=text[size:])
9878-
9879-    def _parse_dict_property(self, this: str) -> exp.DictProperty:
9880-        settings = []
9881-
9882-        self._match_l_paren()
9883-        kind = self._parse_id_var()
9884-
9885-        if self._match(TokenType.L_PAREN):
9886-            while True:
Unable to set __version__, run `pip install -e .` or `python setup.py develop` first.
TokenType.CREATE CREATE
TokenType.TABLE TABLE
TokenType.VAR t
TokenType.ALIAS AS
TokenType.USING USING
TokenType.VAR EXTERNAL
TokenType.FUNCTION FUNCTION
TokenType.VAR f
TokenType.L_PAREN (
TokenType.VAR x
TokenType.VARCHAR VARCHAR
TokenType.R_PAREN )
TokenType.VAR RETURNS
TokenType.VARCHAR VARCHAR
TokenType.VAR LAMBDA
TokenType.STRING l
TokenType.SELECT SELECT
TokenType.VAR f
TokenType.L_PAREN (
TokenType.NUMBER 1
TokenType.R_PAREN )

$ grep -n "DDL_SELECT_TOKENS" -B1 -A3 sqlglot/parser.py sqlglot/parsers/*.py | head -40; sed -n 2739,2760p sqlglot/parser.py
sqlglot/parser.py-1649-
sqlglot/parser.py:1650:    DDL_SELECT_TOKENS: t.ClassVar = {TokenType.SELECT, TokenType.WITH, TokenType.L_PAREN}
sqlglot/parser.py-1651-
sqlglot/parser.py-1652-    PRE_VOLATILE_TOKENS: t.ClassVar = {TokenType.CREATE, TokenType.REPLACE, TokenType.UNIQUE}
sqlglot/parser.py-1653-
--
sqlglot/parser.py-2711-            has_alias = self._match(TokenType.ALIAS)
sqlglot/parser.py:2712:            if not self._match_set(self.DDL_SELECT_TOKENS, advance=False):
sqlglot/parser.py-2713-                # exp.Properties.Location.POST_ALIAS
sqlglot/parser.py-2714-                extend_props(self._parse_properties())
sqlglot/parser.py-2715-
                # Some dialects also support using a table as an alias instead of a SELECT.
                # Here we fallback to this as an alternative.
                if not expression and has_alias:
                    expression = self._try_parse(self._parse_table_parts)

            if create_token_type == TokenType.TABLE:
                # exp.Properties.Location.POST_EXPRESSION
                extend_props(self._parse_properties())

                indexes = []
                while True:
                    index = self._parse_index()

                    # exp.Properties.Location.POST_INDEX
                    extend_props(self._parse_properties())
                    if not index:
                        break
                    else:
                        self._match(TokenType.COMMA)
                        indexes.append(index)
            elif create_token_type == TokenType.VIEW:
                if self._match_text_seq("WITH", "NO", "SCHEMA", "BINDING"):

[grep 'EXTERNAL|def _parse_create|Command' in sqlglot/dialects/athena.py]
30:        - CREATE [EXTERNAL] TABLE (without AS SELECT)
104:        if second_text in ("DATABASE", "EXTERNAL", "SCHEMA"):

[grep 'def _parse_create\\b' in sqlglot]
sqlglot/parser.py:2510:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/fabric.py:8:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/snowflake.py:1058:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/starrocks.py:108:    def _parse_create(self) -> exp.Create | exp.Command:
sqlglot/parsers/tsql.py:823:    def _parse_create(self) -> exp.Create | exp.Command:

$ cd  && grep -n "expression = self._parse_ddl_select\|_parse_ddl_select\|def _parse_create" sqlglot/parser.py | head; grep -n "_parse_command\b" sqlglot/parser.py | head -3
/bin/bash: line 1: cd: too many arguments
2308:    def _parse_command(self) -> exp.Command:
2418:            return self._parse_command()

$ sed -n 2510,2530p sqlglot/parser.py; grep -n "AS USING\|USING EXTERNAL" -r tests/dialects/test_athena.py; grep -n "_parse_ddl_select\|expression = self._parse_ddl\|create_token.token_type in" sqlglot/parser.py | head; grep -n "def _parse_as_command" -A12 sqlglot/parser.py
    def _parse_create(self) -> exp.Create | exp.Command:
        # Note: this can't be None because we've matched a statement parser
        start = self._prev

        replace = (
            start.token_type == TokenType.REPLACE
            or self._match_pair(TokenType.OR, TokenType.REPLACE)
            or self._match_pair(TokenType.OR, TokenType.ALTER)
        )
        refresh = self._match_pair(TokenType.OR, TokenType.REFRESH)

        unique = self._match(TokenType.UNIQUE)

        if self._match_text_seq("CLUSTERED", "COLUMNSTORE"):
            clustered = True
        elif self._match_text_seq("NONCLUSTERED", "COLUMNSTORE") or self._match_text_seq(
            "COLUMNSTORE"
        ):
            clustered = False
        else:
            clustered = None
24:            """USING EXTERNAL FUNCTION some_function(input VARBINARY)
2737:                expression = self._parse_ddl_select()
3751:                or self._parse_ddl_select(),
9130:    def _parse_ddl_select(self) -> exp.Expr | None:
9871:    def _parse_as_command(self, start: Token) -> exp.Command:
9872-        while self._curr:
9873-            self._advance()
9874-        text = self._find_sql(start, self._prev)
9875-        size = len(start.text)
9876-        self._warn_unsupported()
9877-        return exp.Command(this=text[:size], expression=text[size:])
9878-
9879-    def _parse_dict_property(self, this: str) -> exp.DictProperty:
9880-        settings = []
9881-
9882-        self._match_l_paren()
9883-        kind = self._parse_id_var()

[grep 'EXTERNAL|Command|def _parse_create|def _parse_as_command' in sqlglot/dialects/athena.py]
30:        - CREATE [EXTERNAL] TABLE (without AS SELECT)
104:        if second_text in ("DATABASE", "EXTERNAL", "SCHEMA"):

[grep 'def _parse_create|def _parse_as_command' in sqlglot/parser.py]
2510:    def _parse_create(self) -> exp.Create | exp.Command:
3526:    def _parse_create_like(self) -> exp.LikeProperty | None:
9871:    def _parse_as_command(self, start: Token) -> exp.Command:

[read sqlglot/parser.py lines 9865-9889]
9865	
9866	                self._retreat(index)
9867	                return None
9868	
9869	        return exp.var(option)
9870	
9871	    def _parse_as_command(self, start: Token) -> exp.Command:
9872	        while self._curr:
9873	            self._advance()
9874	        text = self._find_sql(start, self._prev)
9875	        size = len(start.text)
9876	        self._warn_unsupported()
9877	        return exp.Command(this=text[:size], expression=text[size:])
9878	
9879	    def _parse_dict_property(self, this: str) -> exp.DictProperty:
9880	        settings = []
9881	
9882	        self._match_l_paren()
9883	        kind = self._parse_id_var()
9884	
9885	        if self._match(TokenType.L_PAREN):
9886	            while True:
9887	                key = self._parse_id_var()
9888	                value = self._parse_function() or self._parse_primary_or_var()
9889	                if not key and value is None:

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
