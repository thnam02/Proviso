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

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
