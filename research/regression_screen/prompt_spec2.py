SPEC = {
'c7957e8c86': ("When sqlglot simulates NULL ordering for dialects whose default NULL order differs (it adds CASE WHEN x IS NULL THEN 1 ELSE 0 END "
  "to ORDER BY, e.g. when transpiling Trino or Postgres to MySQL or T-SQL), it resolves ORDER BY names against the wrong projection: "
  "aliases of an enclosing query, of another UNION branch, or the ORDER BY inside aggregates such as ARRAY_AGG(... ORDER BY ...) and "
  "LISTAGG ... WITHIN GROUP. Only a query's own ORDER BY may be resolved against that query's own projection, so the added CASE must "
  "refer to the right expression.",
  ['transpile("SELECT x AS v, ARRAY_AGG(v ORDER BY v) AS w FROM t GROUP BY x", read="trino", write="mysql")[0]',
   'transpile("WITH c AS (SELECT a AS v, b AS x FROM t UNION ALL SELECT a, b FROM u ORDER BY v LIMIT 1) SELECT x AS v FROM c", read="postgres", write="mysql")[0]',
   ]),
'd5d436bc32': ("Quoted identifiers that contain the dialect's identifier escape character are generated incorrectly. In ClickHouse a backslash "
  "inside a quoted identifier is an escape, so it must be doubled when generating (\"a\\\\\"), backtick identifiers become double-quoted, "
  "and transpiling between ClickHouse and Postgres (where a backslash in an identifier is literal) must convert the escaping both ways.",
  ['parse_one(r\'SELECT "a\\\\"\', read="clickhouse").sql("clickhouse")', 'transpile(r\'SELECT "a\\b"\', read="postgres", write="clickhouse")[0]',
   ]),
'cf39265a3e': ("Expressions that differ only in letter case compare (and hash) as equal even where case is significant: Postgres E'a' vs E'A', "
  "dollar-quoted $$a$$ vs $$A$$ (also as a function body), U&'a' strings, N'a' strings, JSON paths and arrow operators, placeholders "
  "(:a vs :A), SingleStore ::? casts, MySQL DEFINER users, and the names of exp.AnonymousAggFunc / exp.CombinedAggFunc (sumMap vs summap). "
  "Such nodes must only be equal when their text matches exactly; ordinary case-insensitive identifiers keep comparing as before.",
  ['parse_one("E\'a\'", read="postgres") == parse_one("E\'A\'", read="postgres")', 'parse_one(":a") == parse_one(":A")',
   'exp.AnonymousAggFunc(this="sumMap", expressions=[]) == exp.AnonymousAggFunc(this="summap", expressions=[])']),
'840b4823e6': ("In Postgres, LATERAL UNNEST(...) WITH ORDINALITY AS r(v, idx) loses its ordinality column alias and round-trips as AS r(v). "
  "The extra column must be kept, also for several arrays (UNNEST(t.a, t.b) WITH ORDINALITY AS r(x, y, idx)), when generating Postgres "
  "and DuckDB, and Spark must get the equivalent LATERAL VIEW POSEXPLODE.",
  ['parse_one("SELECT r.v, r.idx FROM t CROSS JOIN LATERAL UNNEST(t.a) WITH ORDINALITY AS r(v, idx)", read="postgres").sql("postgres")',
   'parse_one("SELECT * FROM t, LATERAL UNNEST(t.a, t.b) WITH ORDINALITY AS r(x, y, idx)", read="postgres").sql("postgres")']),
'1a0fc4299a': ("MySQL's ALTER TABLE accepts table options and actions in any order (ADD c INT, AUTO_INCREMENT=5, ADD d INT), but sqlglot "
  "only handles a fixed order. Options and actions should be accepted in any order, kept apart (actions as actions, options as options), "
  "and generated with the actions first and the options after; column attributes sqlglot does not support must still fall back to a "
  "Command with the usual warning.",
  ['parse_one("ALTER TABLE t ADD c INT, AUTO_INCREMENT=5, ADD d INT", read="mysql").sql("mysql")',
   'len(parse_one("ALTER TABLE t ADD c INT, AUTO_INCREMENT=5, ADD d INT", read="mysql").args.get("actions") or [])']),
'b3b6c57cea': ("sqlglot.transforms.eliminate_qualify, used when transpiling QUALIFY to dialects without it, projects every column that "
  "appears inside the QUALIFY window function into the subquery. Those projections are redundant and break grouped queries (an "
  "ungrouped column gets selected) and windows over aggregates or subqueries. Only the window's own value, plus columns the outer "
  "filter still needs, should be projected.",
  ['eliminate_qualify(parse_one("SELECT d, c, SUM(s) AS t FROM x GROUP BY d, c QUALIFY RANK() OVER (PARTITION BY d ORDER BY SUM(s) DESC) <= 3")).sql()',
   'eliminate_qualify(parse_one("SELECT a, b FROM t QUALIFY ROW_NUMBER() OVER (PARTITION BY d ORDER BY e) = 1 AND f > 0")).sql()']),
'93aa16deb9': ("MySQL casts with a character set lose the CHAR length: CAST('ab' AS CHAR(4) CHARACTER SET utf8mb4) comes back without the "
  "(4). The length must be kept (CHARSET is written as CHARACTER SET), also for CONVERT(x, CHAR(n) CHARACTER SET cs), and CHAR without a "
  "length must stay without one.",
  ['parse_one("SELECT CAST(\'ab\' AS CHAR(4) CHARACTER SET utf8mb4)", read="mysql").sql("mysql")',
   'parse_one("SELECT CONVERT(\'abc\', CHAR(2) CHARACTER SET latin1)", read="mysql").sql("mysql")']),
'1d2a99b9cc': ("Several ALTER TABLE ... DROP and ALTER COLUMN forms in MySQL and Postgres parse wrongly or fall back to a Command: DROP "
  "PRIMARY KEY should be an exp.DropPrimaryKey action; DROP COLUMN <name> must work for keyword-like names (charset, partitioned_by) "
  "with optional RESTRICT or CASCADE and give an exp.Drop action; RENAME INDEX any TO b must parse; DROP COLUMN a, b must give an "
  "exp.Alter; and unsupported ALTER COLUMN forms (RESTART, SET STATISTICS 100) should fall back to a Command with a warning.",
  ['parse_one("ALTER TABLE t RENAME INDEX any TO b", read="mysql").sql("mysql")',
   'parse_one("ALTER TABLE t DROP COLUMN partitioned_by", read="mysql").sql("mysql")',
   'parse_one("ALTER TABLE t DROP COLUMN partitioned_by CASCADE", read="postgres").sql("postgres")']),
'49d6ed4366': ("Hive and Spark string literals with backslash escapes are not decoded. In Hive and Spark, sequences such as \\n, octal "
  "\\001, \\u0041 and \\U0001F600 denote characters, so the parsed value should hold the decoded character and generation must escape it "
  "again; Spark raw strings r'...' keep backslashes literally; Spark 2 does not decode \\U.",
  ['repr(parse_one(r"SELECT \'\\001\'", read="hive").selects[0].this)', 'parse_one(r"\'\\U0001F600\'", read="spark").sql("spark")',
   ]),
'fc8178edd3': ("DROP INDEX cannot take a qualified table name: DROP INDEX i ON db.t in MySQL and DROP INDEX IF EXISTS i ON dbo.t in T-SQL "
  "fail. Both should parse into exp.Drop and round-trip.",
  ['parse_one("DROP INDEX i ON db.t", read="mysql").sql("mysql")', 'parse_one("DROP INDEX IF EXISTS i ON dbo.t", read="tsql").sql("tsql")']),
}
