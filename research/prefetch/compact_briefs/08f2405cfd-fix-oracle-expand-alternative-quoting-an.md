[read sqlglot/tokenizer_core.py lines 660-739]
660	        self._current = 0
661	        self._line = 1
662	        self._col = 0
663	        self._comments: list[str] = []
664	        self._char = ""
665	        self._end = False
666	        self._peek = ""
667	        self._prev_token_line = -1
668	
669	    def reset(self) -> None:
670	        self.sql = ""
671	        self.size = 0
672	        self.tokens = []
673	        self._start = 0
674	        self._current = 0
675	        self._line = 1
676	        self._col = 0
677	        self._comments = []
678	        self._char = ""
679	        self._end = False
680	        self._peek = ""
681	        self._prev_token_line = -1
682	
683	    def tokenize(self, sql: str) -> list[Token]:
684	        """Returns a list of tokens corresponding to the SQL string `sql`."""
685	        self.reset()
686	        self.sql = sql
687	        self.size = len(sql)
688	
689	        try:
690	            self._scan()
691	        except Exception as e:
692	            start = max(self._current - 50, 0)
693	            end = min(self._current + 50, self.size - 1)
694	            context = self.sql[start:end]
695	            raise TokenError(f"Error tokenizing '{context}'", start=start, end=end) from e
696	
697	        return self.tokens
698	
699	    def _scan(self, check_semicolon: bool = False) -> None:
700	        identifiers = self.identifiers
701	        digit_chars = _DIGIT_CHARS
702	
703	        while self.size and not self._end:
704	            current = self._current
705	
706	            # Skip spaces here rather than iteratively calling advance() for performance reasons
707	            while current < self.size:
708	                char = self.sql[current]
709	
710	                if char == " " or char == "\t":
711	                    current += 1
712	                else:
713	                    break
714	
715	            offset = current - self._current if current > self._current else 1
716	
717	            self._start = current
718	            self._advance(offset)
719	
720	            if not self._char.isspace():
721	                if self._char in digit_chars:
722	                    self._scan_number()
723	                elif self._char in identifiers:
724	                    self._scan_identifier(identifiers[self._char])
725	                else:
726	                    self._scan_keywords()
727	
728	            if check_semicolon and self._peek == ";":
729	                break
730	
731	        if self.tokens and self._comments:
732	            self.tokens[-1].comments.extend(self._comments)
733	
734	    def _chars(self, size: int) -> str:
735	        if size == 1:
736	            return self._char
737	
738	        start = self._current - 1
739	        end = start + size

[read sqlglot/tokenizer_core.py lines 740-884]
740	
741	        return self.sql[start:end] if end <= self.size else ""
742	
743	    def _advance(self, i: int = 1, alnum: bool = False) -> None:
744	        char = self._char
745	
746	        if char == "\n" or char == "\r":
747	            # Ensures we don't count an extra line if we get a \r\n line break sequence
748	            if not (char == "\r" and self._peek == "\n"):
749	                self._col = i
750	                self._line += 1
751	        else:
752	            self._col += i
753	
754	        self._current += i
755	        sql = self.sql
756	        size = self.size
757	        self._end = self._current >= size
758	        self._char = sql[self._current - 1]
759	        self._peek = "" if self._end else sql[self._current]
760	
761	        if alnum and self._char.isalnum():
762	            # Cache to local variables instead of attributes for better performance
763	            _col = self._col
764	            _current = self._current
765	            _end = self._end
766	            _peek = self._peek
767	
768	            while _peek.isalnum():
769	                _col += 1
770	                _current += 1
771	                _end = _current >= size
772	                _peek = "" if _end else sql[_current]
773	
774	            self._col = _col
775	            self._current = _current
776	            self._end = _end
777	            self._peek = _peek
778	            self._char = sql[_current - 1]
779	
780	    @property
781	    def _text(self) -> str:
782	        return self.sql[self._start : self._current]
783	
784	    def _add(self, token_type: TokenType, text: str | None = None) -> None:
785	        self._prev_token_line = self._line
786	
787	        if self._comments and token_type == TokenType.SEMICOLON and self.tokens:
788	            self.tokens[-1].comments.extend(self._comments)
789	            self._comments = []
790	
791	        if text is None:
792	            text = self.sql[self._start : self._current]
793	
794	        self.tokens.append(
795	            Token(
796	                token_type,
797	                text=text,
798	                line=self._line,
799	                col=self._col,
800	                start=self._start,
801	                end=self._current - 1,
802	                comments=self._comments,
803	            )
804	        )
805	        self._comments = []
806	
807	        # If we have either a semicolon or a begin token before the command's token, we'll parse
808	        # whatever follows the command's token as a string
809	        if (
810	            token_type in self.commands
811	            and self._peek != ";"
812	            and (len(self.tokens) == 1 or self.tokens[-2].token_type in self.command_prefix_tokens)
813	        ):
814	            start = self._current
815	            tokens = len(self.tokens)
816	            self._scan(check_semicolon=True)
817	            self.tokens = self.tokens[:tokens]
818	            text = self.sql[start : self._current].strip()
819	            if text:
820	                self._add(TokenType.STRING, text)
821	
822	    def _scan_keywords(self) -> None:
823	        sql = self.sql
824	        sql_size = self.size
825	        single_tokens = self.single_tokens
826	        char_upper = _CHAR_UPPER
827	        size = 0
828	        word = None
829	        chars = self._char
830	        char = chars
831	        prev_space = False
832	        skip = False
833	        trie = self.keyword_trie
834	        single_token = char in single_tokens
835	
836	        while chars:
837	            if not skip:
838	                sub = trie.get(char_upper.get(char, char))
839	                if sub is None:
840	                    break
841	                trie = sub
842	                if 0 in trie:
843	                    word = chars
844	
845	            end = self._current + size
846	            size += 1
847	
848	            if end < sql_size:
849	                char = sql[end]
850	                single_token = single_token or char in single_tokens
851	                is_space = char.isspace()
852	
853	                if not is_space or not prev_space:
854	                    if is_space:
855	                        char = " "
856	                    chars += char
857	                    prev_space = is_space
858	                    skip = False
859	                else:
860	                    skip = True
861	            else:
862	                char = ""
863	                break
864	
865	        if word:
866	            if self._scan_string(word):
867	                return
868	            if self._scan_comment(word):
869	                return
870	            if prev_space or single_token or not char:
871	                word = word.upper()
872	                if word in self.keywords:
873	                    self._advance(size - 1)
874	                    self._add(self.keywords[word], text=word)
875	                    return
876	
877	        if self._char in single_tokens:
878	            self._add(single_tokens[self._char], text=self._char)
879	            return
880	
881	        self._scan_var()
882	
883	    def _scan_comment(self, comment_start: str) -> bool:
884	        if comment_start not in self.comments:

[read sqlglot/tokenizer_core.py lines 1270-1399]
1270	
1271	    def _extract_string(
1272	        self,
1273	        delimiter: str,
1274	        escapes: set[str] | None = None,
1275	        raw_string: bool = False,
1276	        raise_unmatched: bool = True,
1277	        bytes_literal: bool = False,
1278	    ) -> str:
1279	        """
1280	        Extracts a string up to the delimiter, decoding its escape sequences. For byte literals,
1281	        each char of the result is a byte, so non-ASCII chars are stored as their UTF-8 bytes.
1282	        """
1283	        text = ""
1284	        delim_size = len(delimiter)
1285	        escapes = self.string_escapes if escapes is None else escapes
1286	        unescaped_sequences = self.unescaped_sequences
1287	        numeric_escapes = self.numeric_escapes
1288	        drop_unknown_escapes = self.drop_unknown_escapes
1289	        string_escapes_allowed_in_raw_strings = self.string_escapes_allowed_in_raw_strings
1290	        quotes = self.quotes
1291	        sql = self.sql
1292	
1293	        # use str.find() when the string is simple... no \ or other escapes
1294	        if delim_size == 1:
1295	            pos = self._current - 1
1296	            end = sql.find(delimiter, pos)
1297	
1298	            if (
1299	                # the closing delimiter was found
1300	                end != -1
1301	                # there's no doubled delimiter (e.g. '' escape), or the delimiter isn't an escape char
1302	                and (end + 1 >= self.size or sql[end + 1] != delimiter or delimiter not in escapes)
1303	                # no backslash in the string that would need escape processing
1304	                and (not (unescaped_sequences or "\\" in escapes) or sql.find("\\", pos, end) == -1)
1305	            ):
1306	                newlines = sql.count("\n", pos, end)
1307	                if newlines:
1308	                    self._line += newlines
1309	                    self._col = end - sql.rfind("\n", pos, end)
1310	                else:
1311	                    self._col += end - pos
1312	
1313	                self._current = end + 1
1314	                self._end = self._current >= self.size
1315	                self._char = sql[end]
1316	                self._peek = "" if self._end else sql[self._current]
1317	                text = sql[pos:end]
1318	                if bytes_literal and not text.isascii():
1319	                    text = text.encode("utf-8").decode("latin-1")
1320	                return text
1321	
1322	        while True:
1323	            backslash_escape = not raw_string and self._char == "\\" and "\\" in escapes
1324	
1325	            # Numeric escapes come first, since they may overlap fixed sequences (e.g. \000 vs \0)
1326	            if backslash_escape and numeric_escapes:
1327	                decoded = self._scan_numeric_escape()
1328	                if decoded:
1329	                    text += decoded
1330	                    continue
1331	
1332	            # An escape at the end of the input is left to the checks below, which report the
1333	            # unterminated string
1334	            if (
1335	                not raw_string
1336	                and unescaped_sequences
1337	                and self._char in escapes
1338	                and self._current + 1 < self.size
1339	            ):
1340	                unescaped_sequence = unescaped_sequences.get(self._char + self._peek)
1341	                if unescaped_sequence is not None:
1342	                    # Advance one char at a time so that line numbers are updated for a newline
1343	                    if self._peek in "\n\r":
1344	                        self._advance()
1345	                        self._advance()
1346	                    else:
1347	                        self._advance(2)
1348	                    text += unescaped_sequence
1349	                    continue
1350	
1351	            # Not decoded: drop the backslash if configured, unless the string is unterminated
1352	            if backslash_escape and drop_unknown_escapes and self._current + 1 < self.size:
1353	                # Advance one char at a time so that line numbers are updated if `peek` is a newline
1354	                peek = self._peek
1355	                self._advance()
1356	                self._advance()
1357	                text += peek.encode("utf-8").decode("latin-1") if bytes_literal else peek
1358	                continue
1359	
1360	            # An escaped quote before the closing delimiter (e.g. \" in """a\"""") must be
1361	            # consumed here, otherwise it'd be picked up by the delimiter check below and
1362	            # terminate the string early. This is only relevant for multi-char delimiters
1363	            # made up of quote chars, e.g. it shouldn't apply to Snowflake's $$ strings
1364	            escaped_delimiter = self._peek == delimiter or (
1365	                delim_size > 1 and self._peek == delimiter[0] and self._peek in quotes
1366	            )
1367	
1368	            if (
1369	                (string_escapes_allowed_in_raw_strings or not raw_string)
1370	                and self._char in escapes
1371	                and (escaped_delimiter or self._peek in escapes)
1372	                and (self._char not in quotes or self._char == self._peek)
1373	            ):
1374	                if escaped_delimiter:
1375	                    text += self._peek if not raw_string else self._char + self._peek
1376	                else:
1377	                    text += self._char + self._peek
1378	
1379	                if self._current + 1 < self.size:
1380	                    self._advance(2)
1381	                else:
1382	                    raise TokenError(f"Missing {delimiter} from {self._line}:{self._current}")
1383	            else:
1384	                if self._chars(delim_size) == delimiter:
1385	                    if delim_size > 1:
1386	                        self._advance(delim_size - 1)
1387	                    break
1388	
1389	                if self._end:
1390	                    if not ra
… (472 more characters)

[read sqlglot/dialects/oracle.py lines 50-109]
50	    PSEUDOCOLUMNS = {"ROWNUM", "ROWID", "OBJECT_ID", "OBJECT_VALUE", "LEVEL"}
51	
52	    def can_quote(self, identifier: exp.Identifier, identify: str | bool = "safe") -> bool:
53	        # Disable quoting for pseudocolumns as it may break queries e.g
54	        # `WHERE "ROWNUM" = ...` does not work but `WHERE ROWNUM = ...` does
55	        return (
56	            identifier.quoted or not isinstance(identifier.parent, exp.Pseudocolumn)
57	        ) and super().can_quote(identifier, identify=identify)
58	
59	    class Tokenizer(tokens.Tokenizer):
60	        VAR_SINGLE_TOKENS = {"@", "$", "#"}
61	
62	        UNICODE_STRINGS = [
63	            (prefix + q, q)
64	            for q in t.cast(list[str], tokens.Tokenizer.QUOTES)
65	            for prefix in ("U", "u")
66	        ]
67	
68	        # https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Literals.html
69	        # Alternative quoting, e.g. q'[it's]': the delimiters are part of the quote, so the
70	        # text in between is taken as is, without escapes
71	        RAW_STRINGS = [
72	            (f"{prefix}'{start}", f"{end}'")
73	            for prefix in ("q", "Q")
74	            for start, end in (
75	                ("[", "]"),
76	                ("{", "}"),
77	                ("(", ")"),
78	                ("<", ">"),
79	                *((c, c) for c in '!"#$%&*+,-./:;=?@\\^_`|~'),
80	            )
81	        ]
82	        STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = False
83	
84	        NESTED_COMMENTS = False
85	
86	        KEYWORDS = {
87	            **tokens.Tokenizer.KEYWORDS,
88	            "(+)": TokenType.JOIN_MARKER,
89	            # https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Comparison-Conditions.html
90	            "^=": TokenType.NEQ,
91	            "BINARY_DOUBLE": TokenType.DOUBLE,
92	            "BINARY_FLOAT": TokenType.FLOAT,
93	            "BULK COLLECT INTO": TokenType.BULK_COLLECT_INTO,
94	            "COLUMNS": TokenType.COLUMN,
95	            "MATCH_RECOGNIZE": TokenType.MATCH_RECOGNIZE,
96	            "MINUS": TokenType.EXCEPT,
97	            "NVARCHAR2": TokenType.NVARCHAR,
98	            "ORDER SIBLINGS BY": TokenType.ORDER_SIBLINGS_BY,
99	            "SAMPLE": TokenType.TABLE_SAMPLE,
100	            "START": TokenType.BEGIN,
101	            "SUBPARTITION": TokenType.PARTITION,
102	            "TOP": TokenType.TOP,
103	            "VARCHAR2": TokenType.VARCHAR,
104	            "SYSTIMESTAMP": TokenType.SYSTIMESTAMP,
105	        }
106	
107	    Parser = OracleParser
108	
109	    Generator = OracleGenerator

[read tests/dialects/test_oracle.py lines 1165-1194]
1165	            'WITH "T" AS (SELECT 1 AS "COL") SELECT "T"."COL" AS "COL", ROWID AS "ROWID" FROM "T" "T" WHERE ROWNUM = 1',
1166	        )
1167	
1168	    def test_chr(self):
1169	        self.validate_identity("SELECT CHR(187 USING NCHAR_CS)")
1170	        self.validate_identity("SELECT CHR(187)")
1171	
1172	    def test_alternative_quoting(self):
1173	        for sql in (
1174	            "SELECT q'[it's]' FROM dual",
1175	            "SELECT q'{it's}' FROM dual",
1176	            "SELECT q'(it's)' FROM dual",
1177	            "SELECT q'<it's>' FROM dual",
1178	            "SELECT q'!it's!' FROM dual",
1179	            "SELECT Q'#it's#' FROM dual",
1180	        ):
1181	            with self.subTest(sql):
1182	                self.validate_identity(sql, "SELECT 'it''s' FROM dual")
1183	
1184	        self.validate_identity("SELECT q'[a''b]' FROM dual", "SELECT 'a''''b' FROM dual")
1185	        self.validate_identity("SELECT q'[a]b]' FROM dual", "SELECT 'a]b' FROM dual")
1186	        self.validate_identity("SELECT q'|\\n|' FROM dual", "SELECT '\\n' FROM dual")
1187	
1188	        expressions = parse(
1189	            "INSERT INTO t VALUES (q'[a;b]'); CREATE TABLE u (id NUMBER)", read="oracle"
1190	        )
1191	        self.assertEqual(
1192	            [e.sql("oracle") for e in expressions],
1193	            ["INSERT INTO t VALUES ('a;b')", "CREATE TABLE u (id NUMBER)"],
1194	        )

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
