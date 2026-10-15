MUTANTS = [
 ('M1', 'agent code', 'sqlglot/generators/oracle.py', "return f\"AS OF {expression.name} {self.sql(expression, 'expression')}\"", "return f\"AS OF {expression.name}\"", 'Oracle drops the flashback value when generating'),
 ('M2', 'agent code', 'sqlglot/parser.py', "kind = \"AS OF\"\n            expression = self._parse_bitwise()", "kind = \"AS OF\"\n            expression = self._parse_primary()", 'AS OF value parsed as a single primary, not an expression'),
 ('M3', 'agent code', 'sqlglot/parser.py', "            parse_partition\n            and self._next.token_type == TokenType.L_PAREN\n", "            parse_partition\n", 'partition keyword accepted without parentheses'),
 ('M4', 'agent code', 'sqlglot/parsers/oracle.py', "        (\"AS\", \"OF\", \"TIMESTAMP\"): \"TIMESTAMP\",\n", "", 'AS OF TIMESTAMP phrase missing'),
 ('M5', 'agent code', 'sqlglot/parser.py', "not this.args.get(\"version\")", "this.args.get(\"version\")", 'version-after-sample condition inverted'),
 ('M8', 'agent code', 'sqlglot/parsers/oracle.py', "            return self._parse_schema(this=this)", "            return this", 'INSERT target column list dropped'),
 ('M6', 'shared code', 'sqlglot/parser.py', "        if self.dialect.ALIAS_POST_TABLESAMPLE:\n            this.set(\"sample\", self._parse_table_sample())\n\n            # The time", "        if not self.dialect.ALIAS_POST_TABLESAMPLE:\n            this.set(\"sample\", self._parse_table_sample())\n\n            # The time", 'sample-before-alias rule inverted for every dialect'),
 ('M7', 'shared code', 'sqlglot/generator.py', "\"SUBPARTITION\" if expression.args.get(\"subpartition\") else \"PARTITION\"", "\"PARTITION\" if expression.args.get(\"subpartition\") else \"SUBPARTITION\"", 'PARTITION and SUBPARTITION swapped in all dialects'),
 ('M9', 'shared code', 'sqlglot/generator.py', "        return f\"{this} {kind} {expr}\"", "        return f\"{this} {expr}\"", 'time-travel kind dropped for dialects using the default generator'),
 ('M10', 'shared code', 'sqlglot/generator.py', "return f\"{partition_keyword}({self.expressions(expression, flat=True)})\"", "return f\"{partition_keyword} ({self.expressions(expression, flat=True)})\"", 'space added after PARTITION in all dialects'),
]
