[grep "q'|RAW_STRING|nq|NATIONAL" in sqlglot/dialects/oracle.py]
69:        # Alternative quoting, e.g. q'[it's]': the delimiters are part of the quote, so the
71:        RAW_STRINGS = [
82:        STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = False

[grep '_scan_string|def _scan_var|_extract_string|def _scan_raw|format_strings|STRING_ESCAPES' in sqlglot ({tokens.py,tokenizer_core.py})]
sqlglot/tokenizer_core.py:555:        "format_strings",
sqlglot/tokenizer_core.py:592:        format_strings: dict[str, tuple[str, TokenType]],
sqlglot/tokenizer_core.py:626:        self.format_strings = format_strings
sqlglot/tokenizer_core.py:866:            if self._scan_string(word):
sqlglot/tokenizer_core.py:1069:    def _scan_string(self, start: str) -> bool:
sqlglot/tokenizer_core.py:1075:        elif start in self.format_strings:
sqlglot/tokenizer_core.py:1076:            end, token_type = self.format_strings[start]
sqlglot/tokenizer_core.py:1088:                    tag = self._extract_string(
sqlglot/tokenizer_core.py:1111:        text = self._extract_string(
sqlglot/tokenizer_core.py:1135:        text = self._extract_string(
sqlglot/tokenizer_core.py:1140:    def _scan_var(self) -> None:
sqlglot/tokenizer_core.py:1271:    def _extract_string(
sqlglot/tokens.py:51:    STRING_ESCAPES: t.ClassVar[list[str]]
sqlglot/tokens.py:52:    BYTE_STRING_ESCAPES: t.ClassVar[list[str]]
sqlglot/tokens.py:62:    STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS: t.ClassVar[bool]
sqlglot/tokens.py:76:    _STRING_ESCAPES: t.ClassVar[set[str]]
sqlglot/tokens.py:77:    _BYTE_STRING_ESCAPES: t.ClassVar[set[str]]
sqlglot/tokens.py:101:            "BYTE_STRING_ESCAPES" in k.__dict__ for k in cls.__mro__ if k.__module__ != __name__
sqlglot/tokens.py:103:            cls.BYTE_STRING_ESCAPES = cls.STRING_ESCAPES.copy()
sqlglot/tokens.py:104:        cls._STRING_ESCAPES = set(cls.STRING_ESCAPES)
sqlglot/tokens.py:105:        cls._BYTE_STRING_ESCAPES = set(cls.BYTE_STRING_ESCAPES)
sqlglot/tokens.py:169:    STRING_ESCAPES: t.ClassVar[list[str]] = ["'"]
sqlglot/tokens.py:170:    BYTE_STRING_ESCAPES: t.ClassVar[list[str]] = []
sqlglot/tokens.py:185:    STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = True
sqlglot/tokens.py:222:    _STRING_ESCAPES: t.ClassVar[set[str]] = set()
sqlglot/tokens.py:223:    _BYTE_STRING_ESCAPES: t.ClassVar[set[str]] = set()
sqlglot/tokens.py:575:            format_strings=self._FORMAT_STRINGS,
sqlglot/tokens.py:578:            string_escapes=self._STRING_ESCAPES,
sqlglot/tokens.py:579:            byte_string_escapes=self._BYTE_STRING_ESCAPES,
sqlglot/tokens.py:592:            string_escapes_allowed_in_raw_strings=self.STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS,

[read sqlglot/dialects/oracle.py lines 55-104]
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

[read sqlglot/tokenizer_core.py lines 820-899]
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
885	            return False
886	
887	        if comment_start == "--" and self.dash_comment_requires_boundary:
888	            boundary_index = self._current + 1
889	            if boundary_index < self.size:
890	                boundary_char = self.sql[boundary_index]
891	                if not (
892	                    boundary_char.isspace() or ord(boundary_char) < 32 or ord(boundary_char) == 127
893	                ):
894	                    return False
895	
896	        comment_start_line = self._line
897	        comment_start_size = len(comment_start)
898	        comment_end = self.comments[comment_start]
899

[read sqlglot/tokenizer_core.py lines 1060-1149]
1060	        while True:
1061	            char = self._peek.strip()
1062	            if char and char not in single_tokens:
1063	                self._advance(alnum=True)
1064	            else:
1065	                break
1066	
1067	        return self._text
1068	
1069	    def _scan_string(self, start: str) -> bool:
1070	        base = None
1071	        token_type = TokenType.STRING
1072	
1073	        if start in self.quotes:
1074	            end = self.quotes[start]
1075	        elif start in self.format_strings:
1076	            end, token_type = self.format_strings[start]
1077	
1078	            if token_type == TokenType.HEX_STRING:
1079	                base = 16
1080	            elif token_type == TokenType.BIT_STRING:
1081	                base = 2
1082	            elif token_type == TokenType.HEREDOC_STRING:
1083	                self._advance()
1084	
1085	                if self._char == end:
1086	                    tag = ""
1087	                else:
1088	                    tag = self._extract_string(
1089	                        end,
1090	                        raw_string=True,
1091	                        raise_unmatched=not self.heredoc_tag_is_identifier,
1092	                    )
1093	
1094	                if (
1095	                    tag
1096	                    and self.heredoc_tag_is_identifier
1097	                    and (self._end or tag.isdigit() or any(c.isspace() for c in tag))
1098	                ):
1099	                    if not self._end:
1100	                        self._advance(-1)
1101	
1102	                    self._advance(-len(tag))
1103	                    self._add(self.heredoc_string_alternative)
1104	                    return True
1105	
1106	                end = f"{start}{tag}{end}"
1107	        else:
1108	            return False
1109	
1110	        self._advance(len(start))
1111	        text = self._extract_string(
1112	            end,
1113	            escapes=(
1114	                self.byte_string_escapes
1115	                if token_type == TokenType.BYTE_STRING
1116	                else self.string_escapes
1117	            ),
1118	            raw_string=token_type in (TokenType.RAW_STRING, TokenType.HEREDOC_STRING),
1119	            bytes_literal=token_type == TokenType.BYTE_STRING and self.byte_strings_are_bytes,
1120	        )
1121	
1122	        if base and text:
1123	            try:
1124	                int(text, base)
1125	            except Exception:
1126	                raise TokenError(
1127	                    f"Numeric string contains invalid characters from {self._line}:{self._start}"
1128	                )
1129	
1130	        self._add(token_type, text)
1131	        return True
1132	
1133	    def _scan_identifier(self, identifier_end: str) -> None:
1134	        self._advance()
1135	        text = self._extract_string(
1136	            identifier_end, escapes=self.identifier_escapes | {identifier_end}
1137	        )
1138	        self._add(TokenType.IDENTIFIER, text)
1139	
1140	    def _scan_var(self) -> None:
1141	        var_single_tokens = self.var_single_tokens
1142	        single_tokens = self.single_tokens
1143	
1144	        while True:
1145	            peek = self._peek
1146	            if not peek or peek.isspace():
1147	                break
1148	            if peek not in var_single_tokens and peek in single_tokens:
1149	                break

[read sqlglot/tokenizer_core.py lines 1265-1344]
1265	                # Move past the whole escape, from the backslash through its last digit
1266	                self._advance(end - start + 1)
1267	                return chr(value)
1268	
1269	        return ""
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

[grep 'RAW_STRING|raw_string|NATIONAL_STRING' in sqlglot ({tokens.py,tokenizer_core.py,dialects/oracle.py,generator.py})]
sqlglot/tokenizer_core.py:112:    NATIONAL_STRING = auto()
sqlglot/tokenizer_core.py:113:    RAW_STRING = auto()
sqlglot/tokenizer_core.py:572:        "string_escapes_allowed_in_raw_strings",
sqlglot/tokenizer_core.py:609:        string_escapes_allowed_in_raw_strings: bool,
sqlglot/tokenizer_core.py:643:        self.string_escapes_allowed_in_raw_strings = string_escapes_allowed_in_raw_strings
sqlglot/tokenizer_core.py:1090:                        raw_string=True,
sqlglot/tokenizer_core.py:1118:            raw_string=token_type in (TokenType.RAW_STRING, TokenType.HEREDOC_STRING),
sqlglot/tokenizer_core.py:1275:        raw_string: bool = False,
sqlglot/tokenizer_core.py:1289:        string_escapes_allowed_in_raw_strings = self.string_escapes_allowed_in_raw_strings
sqlglot/tokenizer_core.py:1323:            backslash_escape = not raw_string and self._char == "\\" and "\\" in escapes
sqlglot/tokenizer_core.py:1335:                not raw_string
sqlglot/tokenizer_core.py:1369:                (string_escapes_allowed_in_raw_strings or not raw_string)
sqlglot/tokenizer_core.py:1375:                    text += self._peek if not raw_string else self._char + self._peek
sqlglot/dialects/oracle.py:71:        RAW_STRINGS = [
sqlglot/dialects/oracle.py:82:        STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = False
sqlglot/tokens.py:48:    RAW_STRINGS: t.ClassVar[list[str | tuple[str, str]]]
sqlglot/tokens.py:62:    STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS: t.ClassVar[bool]
sqlglot/tokens.py:89:                p + s: (e, TokenType.NATIONAL_STRING)
sqlglot/tokens.py:96:            **_quotes_to_format(TokenType.RAW_STRING, cls.RAW_STRINGS),
sqlglot/tokens.py:164:    RAW_STRINGS: t.ClassVar[list[str | tuple[str, str]]] = []
sqlglot/tokens.py:185:    STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = True
sqlglot/tokens.py:592:            string_escapes_allowed_in_raw_strings=self.STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS,

[read sqlglot/tokenizer_core.py lines 548-657]
548	        "_char",
549	        "_end",
550	        "_peek",
551	        "_prev_token_line",
552	        "single_tokens",
553	        "keywords",
554	        "quotes",
555	        "format_strings",
556	        "identifiers",
557	        "comments",
558	        "string_escapes",
559	        "byte_string_escapes",
560	        "identifier_escapes",
561	        "commands",
562	        "command_prefix_tokens",
563	        "nested_comments",
564	        "dash_comment_requires_boundary",
565	        "comments_terminate_at_newline_only",
566	        "hint_start",
567	        "tokens_preceding_hint",
568	        "has_bit_strings",
569	        "has_hex_strings",
570	        "numeric_literals",
571	        "var_single_tokens",
572	        "string_escapes_allowed_in_raw_strings",
573	        "heredoc_tag_is_identifier",
574	        "heredoc_string_alternative",
575	        "keyword_trie",
576	        "numbers_can_be_underscore_separated",
577	        "numbers_can_have_decimals",
578	        "identifiers_can_start_with_digit",
579	        "unescaped_sequences",
580	        "numeric_escapes",
581	        "drop_unknown_escapes",
582	        "numeric_escapes_are_bytes",
583	        "byte_strings_are_bytes",
584	        "lone_surrogate_replacement",
585	    )
586	
587	    def __init__(
588	        self,
589	        single_tokens: dict[str, TokenType],
590	        keywords: dict[str, TokenType],
591	        quotes: dict[str, str],
592	        format_strings: dict[str, tuple[str, TokenType]],
593	        identifiers: dict[str, str],
594	        comments: dict[str, str | None],
595	        string_escapes: set[str],
596	        byte_string_escapes: set[str],
597	        identifier_escapes: set[str],
598	        commands: set[TokenType],
599	        command_prefix_tokens: set[TokenType],
600	        nested_comments: bool,
601	        dash_comment_requires_boundary: bool,
602	        comments_terminate_at_newline_only: bool,
603	        hint_start: str,
604	        tokens_preceding_hint: set[TokenType],
605	        has_bit_strings: bool,
606	        has_hex_strings: bool,
607	        numeric_literals: dict[str, str],
608	        var_single_tokens: set[str],
609	        string_escapes_allowed_in_raw_strings: bool,
610	        heredoc_tag_is_identifier: bool,
611	        heredoc_string_alternative: TokenType,
612	        keyword_trie: dict,
613	        numbers_can_be_underscore_separated: bool,
614	        numbers_can_have_decimals: bool,
615	        identifiers_can_start_with_digit: bool,
616	        unescaped_sequences: dict[str, str],
617	        numeric_escapes: dict[str, tuple[int, int, int, int]],
618	        drop_unknown_escapes: bool,
619	        numeric_escapes_are_bytes: bool,
620	        byte_strings_are_bytes: bool,
621	        lone_surrogate_replacement: str,
622	    ) -> None:
623	        self.single_tokens = single_tokens
624	        self.keywords = keywords
625	        self.quotes = quotes
626	        self.format_strings = format_strings
627	        self.identifiers = identifiers
628	        self.comments = comments
629	        self.string_escapes = string_escapes
630	        self.byte_string_escapes = byte_string_escapes
631	        self.identifier_escapes = identifier_escapes
632	        self.commands = commands
633	        self.command_prefix_tokens = command_prefix_tokens
634	        self.nested_comments = nested_comments
635	        self.dash_comment_requires_boundary = dash_comment_requires_boundary
636	        self.comments_terminate_at_newline_only = comments_terminate_at_newline_only
637	        self.hint_start = hint_start
638	        self.tokens_preceding_hint = tokens_preceding_hint
639	        self.has_bit_strings = has_bit_strings
640	        self.has_hex_strings = has_hex_strings
641	        self.numeric_literals = numeric_literals
642	        self.var_single_tokens = var_single_tokens
643	        self.string_escapes_allowed_in_raw_strings = string_escapes_allowed_in_raw_strings
644	        self.heredoc_tag_is_identifier = heredoc_tag_is_identifier
645	        self.heredoc_string_alternative = heredoc_string_alternative
646	        self.keyword_trie = keyword_trie
647	        self.numbers_can_be_underscore_separated = numbers_can_be_underscore_separated
648	        self.numbers_can_have_decimals = numbers_can_have_decimals
649	        self.identifiers_can_start_with_digit = identifiers_can_start_with_digit
650	        self.unescaped_sequences = unescaped_sequences
651	        self.numeric_escapes = numeric_escapes
652	        self.drop_unknown_escapes = drop_unknown_escapes
653	        self.numeric_escapes_are_bytes = numeric_escapes_are_bytes
654	        self.byte_strings_are_bytes = byte_strings_are_bytes
655	        self.lone_surrogate_replacement = lone_surrogate_replacement
656	        self.sql = ""
657	        self.size = 0

[read sqlglot/tokens.py lines 560-604]
560	        "dialect",
561	        "_core",
562	    )
563	
564	    def __init__(self, dialect: DialectType = None) -> None:
565	        from sqlglot.dialects.dialect import Dialect
566	
567	        self.dialect = Dialect.get_or_raise(dialect)
568	        self._core = self._init_core()
569	
570	    def _init_core(self) -> TokenizerCore:
571	        return TokenizerCore(
572	            single_tokens=self.SINGLE_TOKENS,
573	            keywords=self.KEYWORDS,
574	            quotes=self._QUOTES,
575	            format_strings=self._FORMAT_STRINGS,
576	            identifiers=self._IDENTIFIERS,
577	            comments=self._COMMENTS,
578	            string_escapes=self._STRING_ESCAPES,
579	            byte_string_escapes=self._BYTE_STRING_ESCAPES,
580	            identifier_escapes=self._IDENTIFIER_ESCAPES,
581	            commands=self.COMMANDS,
582	            command_prefix_tokens=self.COMMAND_PREFIX_TOKENS,
583	            nested_comments=self.NESTED_COMMENTS,
584	            dash_comment_requires_boundary=self.DASH_COMMENT_REQUIRES_BOUNDARY,
585	            comments_terminate_at_newline_only=self.COMMENTS_TERMINATE_AT_NEWLINE_ONLY,
586	            hint_start=self.HINT_START,
587	            tokens_preceding_hint=self.TOKENS_PRECEDING_HINT,
588	            has_bit_strings=bool(self.BIT_STRINGS),
589	            has_hex_strings=bool(self.HEX_STRINGS),
590	            numeric_literals=self.NUMERIC_LITERALS,
591	            var_single_tokens=self.VAR_SINGLE_TOKENS,
592	            string_escapes_allowed_in_raw_strings=self.STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS,
593	            heredoc_tag_is_identifier=self.HEREDOC_TAG_IS_IDENTIFIER,
594	            heredoc_string_alternative=self.HEREDOC_STRING_ALTERNATIVE,
595	            keyword_trie=self._KEYWORD_TRIE,
596	            numbers_can_be_underscore_separated=self.dialect.NUMBERS_CAN_BE_UNDERSCORE_SEPARATED,
597	            numbers_can_have_decimals=self.NUMBERS_CAN_HAVE_DECIMALS,
598	            identifiers_can_start_with_digit=self.dialect.IDENTIFIERS_CAN_START_WITH_DIGIT,
599	            unescaped_sequences=self.dialect.UNESCAPED_SEQUENCES,
600	            numeric_escapes=self.NUMERIC_ESCAPES,
601	            drop_unknown_escapes=self.DROP_UNKNOWN_ESCAPES,
602	            numeric_escapes_are_bytes=self.NUMERIC_ESCAPES_ARE_BYTES,
603	            byte_strings_are_bytes=self.dialect.BYTE_STRING_IS_BYTES_TYPE,
604	            lone_surrogate_replacement=self.LONE_SURROGATE_REPLACEMENT,

[read sqlglot/tokenizer_core.py lines 740-821]
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

[grep "q'|RAW_STRING|QUOTE_START|nq|NATIONAL" in sqlglot/dialects/oracle.py]
69:        # Alternative quoting, e.g. q'[it's]': the delimiters are part of the quote, so the
71:        RAW_STRINGS = [
82:        STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = False

[grep "q'|Q'" in sqlglot]
sqlglot/parser.py:6544:        # parse_types() returns a Cast if we parsed BQ's inline constructor <type>(<values>) e.g.
sqlglot/expressions/temporal.py:169:        # Across most dialects it's safe to unabbreviate the unit (e.g. 'Q' -> 'QUARTER') except Oracle
sqlglot/dialects/oracle.py:69:        # Alternative quoting, e.g. q'[it's]': the delimiters are part of the quote, so the
sqlglot/dialects/dialect.py:1906:    # Transpile BQ's TIME(timestamp, zone) to CAST(TIMESTAMPTZ <timestamp> AT TIME ZONE <zone> AS TIME)
sqlglot/dialects/dialect.py:1917:        # Transpile BQ's DATETIME(timestamp, zone) to CAST(TIMESTAMPTZ <timestamp> AT TIME ZONE <zone> AS TIMESTAMP)
sqlglot/parsers/bigquery.py:557:        # Converts BQ's "signature 2" of JSON_OBJECT into SQLGlot's canonical representation
sqlglot/generators/hive.py:335:            "SPLIT", e.this, self.func("CONCAT", "'\\\\Q'", e.expression, "'\\\\E'")
sqlglot/generators/duckdb.py:986:    # BQ's GENERATE_DATE_ARRAY & GENERATE_TIMESTAMP_ARRAY are transformed to DuckDB'S GENERATE_SERIES
sqlglot/generators/duckdb.py:992:        # The GENERATE_SERIES result type is TIMESTAMP array, so to match BQ's semantics for
sqlglot/generators/duckdb.py:4010:            # If BQ's UNNEST is aliased, we transform it from a column alias to a table alias in DDB

[grep 'raw_string|RAW_STRING|_scan_string|_extract_string|def _scan_keywords|_scan_var' in sqlglot (*{tokens,tokenizer_core}.py)]
sqlglot/tokenizer_core.py:113:    RAW_STRING = auto()
sqlglot/tokenizer_core.py:572:        "string_escapes_allowed_in_raw_strings",
sqlglot/tokenizer_core.py:609:        string_escapes_allowed_in_raw_strings: bool,
sqlglot/tokenizer_core.py:643:        self.string_escapes_allowed_in_raw_strings = string_escapes_allowed_in_raw_strings
sqlglot/tokenizer_core.py:822:    def _scan_keywords(self) -> None:
sqlglot/tokenizer_core.py:866:            if self._scan_string(word):
sqlglot/tokenizer_core.py:881:        self._scan_var()
sqlglot/tokenizer_core.py:1069:    def _scan_string(self, start: str) -> bool:
sqlglot/tokenizer_core.py:1088:                    tag = self._extract_string(
sqlglot/tokenizer_core.py:1090:                        raw_string=True,
sqlglot/tokenizer_core.py:1111:        text = self._extract_string(
sqlglot/tokenizer_core.py:1118:            raw_string=token_type in (TokenType.RAW_STRING, TokenType.HEREDOC_STRING),
sqlglot/tokenizer_core.py:1135:        text = self._extract_string(
sqlglot/tokenizer_core.py:1140:    def _scan_var(self) -> None:
sqlglot/tokenizer_core.py:1271:    def _extract_string(
sqlglot/tokenizer_core.py:1275:        raw_string: bool = False,
sqlglot/tokenizer_core.py:1289:        string_escapes_allowed_in_raw_strings = self.string_escapes_allowed_in_raw_strings
sqlglot/tokenizer_core.py:1323:            backslash_escape = not raw_string and self._char == "\\" and "\\" in escapes
sqlglot/tokenizer_core.py:1335:                not raw_string
sqlglot/tokenizer_core.py:1369:                (string_escapes_allowed_in_raw_strings or not raw_string)
sqlglot/tokenizer_core.py:1375:                    text += self._peek if not raw_string else self._char + self._peek
sqlglot/tokens.py:48:    RAW_STRINGS: t.ClassVar[list[str | tuple[str, str]]]
sqlglot/tokens.py:62:    STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS: t.ClassVar[bool]
sqlglot/tokens.py:96:            **_quotes_to_format(TokenType.RAW_STRING, cls.RAW_STRINGS),
sqlglot/tokens.py:164:    RAW_STRINGS: t.ClassVar[list[str | tuple[str, str]]] = []
sqlglot/tokens.py:185:    STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = True
sqlglot/tokens.py:592:            string_escapes_allowed_in_raw_strings=self.STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS,

[grep 'RawString|rawstring|national' in sqlglot/generators/oracle.py]
No matches found

[read sqlglot/generator.py lines 1730-1739]
1730	            this = self.escape_str(this, escape_backslash=False)
1731	
1732	        return f"{left_quote}{this}{right_quote}{escape_sql}"
1733	
1734	    def rawstring_sql(self, expression: exp.RawString) -> str:
1735	        string = expression.this
1736	        if "\\" in self.dialect.tokenizer_class.STRING_ESCAPES:
1737	            string = string.replace("\\", "\\\\")
1738	
1739	        string = self.escape_str(string, escape_backslash=False)

[read sqlglot/generator.py lines 2095-2102]
2095	        output_format = self.sql(expression, "output_format")
2096	        output_format = f"OUTPUTFORMAT {output_format}" if output_format else ""
2097	        return self.sep().join((input_format, output_format))
2098	
2099	    def national_sql(self, expression: exp.National, prefix: str = "N") -> str:
2100	        string = self.sql(exp.Literal.string(expression.name))
2101	        return f"{prefix}{string}"
2102

[grep "q'|RAW_STRING|nq|alternative|QUOTE" in sqlglot/dialects/oracle.py]
64:            for q in t.cast(list[str], tokens.Tokenizer.QUOTES)
69:        # Alternative quoting, e.g. q'[it's]': the delimiters are part of the quote, so the
71:        RAW_STRINGS = [
82:        STRING_ESCAPES_ALLOWED_IN_RAW_STRINGS = False

Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
