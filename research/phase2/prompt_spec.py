# id prefix -> (symptom description, [python expressions shown as examples])
SPEC = {
'd84f7f3ee1': ("Hive and Spark BD (exact decimal) literals such as 10.50BD lose their decimal semantics in sqlglot. "
  "A BD literal should become the literal's text cast to a DECIMAL whose precision and scale follow each engine's rules: "
  "Hive keeps only the significant digits, while Spark, Spark 2 and Databricks keep the scale as written. Exponents "
  "(1E-18BD, 1E3BD), signs (-10.50bd, +10.50bd) and very long literals must work, a BD literal inside another CAST stays an "
  "inner cast, and Spark 2's handling of BD literals whose exponent would give a negative scale must be respected.",
  ['parse_one("10.50bd", read="hive").sql("hive")', 'parse_one("10.50bd", read="spark").sql("spark")',
   'parse_one("-1E-18bd", read="databricks").sql("databricks")', 'parse_one("CAST(10.50BD AS DECIMAL)", read="hive").sql("hive")']),
'08f2405cfd': ("sqlglot only understands some forms of Oracle's alternative quoting (q'[...]'). Oracle allows any delimiter "
  "after q': the brackets [ ] { } ( ) < > close with their partner, any other character closes with itself, the q may be upper "
  "or lower case, and the national form nq'...' (any case) gives an N'...' literal. Quotes and newlines inside the literal must be "
  "kept, the literal must round-trip, and text inside such literals must not be mistaken for SQL tokens.",
  ['parse_one("SELECT q\']it\'s]\' FROM dual", read="oracle").sql("oracle")', 'parse_one("SELECT Q\'Ait\'sA\' FROM dual", read="oracle").sql("oracle")',
   'parse_one("SELECT nq\'[it\'s]\' FROM dual", read="oracle").sql("oracle")']),
'59a96d868a': ("StarRocks REFRESH MATERIALIZED VIEW raises ParseError when it has its optional clauses: PARTITION START (...) END (...), "
  "FORCE, and WITH SYNC MODE / WITH ASYNC MODE. These should parse into exp.Refresh and round-trip in StarRocks; incomplete mode "
  "clauses (WITH, MODE, WITH SYNC, WITH ASYNC) must still raise ParseError; and generating these options for dialects that do not "
  "support them (the default dialect, Postgres) must report them as unsupported.",
  ['parse_one("REFRESH MATERIALIZED VIEW db.lo_mv1 PARTITION START (\'2020-02-01\') END (\'2020-03-01\') FORCE WITH SYNC MODE", read="starrocks").sql("starrocks")',
   'parse_one(\'REFRESH MATERIALIZED VIEW lo_mv1 PARTITION START ("2020-02-01") END ("2020-03-01")\', read="starrocks").sql("starrocks")',
   'parse_one("REFRESH MATERIALIZED VIEW mv WITH ASYNC MODE", read="starrocks").sql("starrocks")']),
'f3a6eb95e4': ("Doris full-text search operators do not parse: MATCH, MATCH_ANY, MATCH_ALL, MATCH_PHRASE, MATCH_PHRASE_PREFIX, "
  "MATCH_PHRASE_EDGE and MATCH_REGEXP (any case), optionally followed by USING ANALYZER <name>. Each should parse into exp.Match "
  "with `kind` None for plain MATCH and 'ANY', 'ALL', 'PHRASE', 'PHRASE_PREFIX', 'PHRASE_EDGE' or 'REGEXP' otherwise, round-trip in "
  "Doris (operator upper-cased), and combine correctly with NOT, AND and OR.",
  ['parse_one("SELECT * FROM t WHERE c MATCH_ANY \'word1 word2\'", read="doris").sql("doris")',
   'parse_one("SELECT * FROM t WHERE c MATCH \'hello world\' USING ANALYZER std_analyzer", read="doris").sql("doris")',
   'parse_one("SELECT * FROM t WHERE c match_regexp \'^key_word.*\'", read="doris").sql("doris")']),
'fc4964bbe8': ("MySQL and PostgreSQL allow one ALTER TABLE to mix operations, such as ADD and DROP in the same statement, but sqlglot "
  "falls back to a generic Command for these. Every action should parse into a proper action node (never exp.Command) and the "
  "statement should round-trip; in MySQL, table options mixed with actions (COMMENT='hi', AUTO_INCREMENT=3000000000) must be kept "
  "apart from the actions; and names that look like keywords (concurrently, any, charset) must keep working.",
  ['[type(a).__name__ for a in parse_one("ALTER TABLE t ADD COLUMN a INT, DROP COLUMN b, ADD COLUMN c INT, DROP COLUMN d", read="mysql").args.get("actions") or []]',
   '[type(a).__name__ for a in parse_one("ALTER TABLE t DROP INDEX i, ADD FULLTEXT INDEX i1 (s)", read="mysql").args.get("actions") or []]',
   'type(parse_one("ALTER TABLE t ALTER COLUMN c SET DEFAULT 1, ADD COLUMN d INT", read="postgres")).__name__']),
'1f8d15bbd6': ("Transpiling DuckDB's ARRAY_SLICE(arr, start, end) to Spark, Spark 2, Databricks, Presto and Trino SLICE gives the wrong "
  "elements: DuckDB's third argument is an inclusive end position and a start of 0 means the first element, while SLICE takes a "
  "length. The generated SLICE must select the same elements, including when the end is before the start and when the start is "
  "negative; DuckDB output itself must stay unchanged.",
  ['transpile("SELECT ARRAY_SLICE([1, 2, 3, 4], 2, 3)", read="duckdb", write="spark")[0]',
   'transpile("ARRAY_SLICE(x, 0, 2)", read="duckdb", write="presto")[0]', 'transpile("ARRAY_SLICE(x, 3, 2)", read="duckdb", write="spark")[0]']),
'15a77f1d89': ("MySQL string literals with backslash escapes are not decoded. In MySQL, sequences like \\0, \\n and \\t inside a string "
  "denote special characters, so the parsed value should hold the decoded character and generation must escape it correctly again, "
  "in MySQL-family dialects and when transpiling to others (for example ClickHouse). Related: IS_ASCII(x) from the default dialect "
  "should transpile to SingleStore as a regular-expression check on the ASCII range.",
  ['repr(parse_one(r"SELECT \'a\\0b\'", read="mysql").selects[0].this)', 'parse_one(r"SELECT \'\\0\'", read="mysql").sql("clickhouse")',
   'transpile("SELECT IS_ASCII(\'a\')", write="singlestore")[0]']),
'e3ed74860f': ("Hive and Spark's FROM-first multi-table INSERT (FROM x INSERT OVERWRITE TABLE a SELECT ... [INSERT ... SELECT ...]) fails "
  "to parse. It should parse into exp.MultitableInserts with no kind, including when it starts with a CTE, and be generated back in "
  "the same FROM-first form for Hive and Spark; other dialects should get an unsupported warning. LATERAL VIEWs after a leading FROM "
  "(FROM x LATERAL VIEW EXPLODE(y) t AS a SELECT a) must keep working.",
  ['parse_one("FROM x INSERT OVERWRITE TABLE a SELECT k, v", read="hive").sql("hive")',
   'parse_one("FROM x AS v INSERT OVERWRITE TABLE a PARTITION(ds = \'1\') SELECT v.k WHERE v.os = \'ios\' INSERT INTO c SELECT v.os", read="hive").sql("hive")',
   'transpile("FROM x LATERAL VIEW EXPLODE(y) t AS a SELECT a", read="hive", write="presto")[0]']),
'f337c70ee4': ("Snowflake's LIST command (and its alias LS) for stages is not modelled. LIST <location> [PATTERN = '<regex>'] should parse "
  "into exp.ListStage whose `this` is the location as exp.var(<location text>) and whose `pattern` is the string literal, and be "
  "generated as LIST <location> [PATTERN = '<regex>'] (LS becomes LIST, pattern keyword upper-cased), for table stages (@%t), the user "
  "stage (@~), named and qualified stages, quoted stage names and paths.",
  ['parse_one("ls @named_stage", read="snowflake").sql("snowflake")',
   'parse_one("LIST @named_stage/analysis/ pattern=\'.*data_0.*\'", read="snowflake").sql("snowflake")',
   'type(parse_one("LIST @~", read="snowflake")).__name__']),
'c7778cf56d': ("In MySQL, DROP INDEX concurrently ON t fails with a ParseError: concurrently should be read as the index name here. "
  "In ALTER TABLE as well, DROP INDEX concurrently must give an exp.Drop whose first table is named concurrently with its concurrently flag "
  "False, and a bare ALTER TABLE t DROP <name> (no COLUMN) must keep meaning a column drop even for keyword-like names such as temporary "
  "or iceberg. The same applies to the MySQL-family dialects Doris and StarRocks.",
  ['parse_one("DROP INDEX concurrently ON t", read="mysql").sql("mysql")']),
'361b23b87b': ("Recursive CTEs that use both a SEARCH and a CYCLE clause, or a CYCLE clause with SET col TO 'Y' DEFAULT 'N', fail to parse "
  "or lose parts. Both clauses should be parsed after the CTE, kept on the WITH (search with kind 'DEPTH' or 'BREADTH'; cycle with its "
  "`to` and `default` values), and round-trip, in Oracle and in Postgres, including Postgres's CYCLE ... USING path.",
  ['parse_one("WITH r(a) AS (SELECT 1 FROM dual UNION ALL SELECT a + 1 FROM r WHERE a < 3) SEARCH DEPTH FIRST BY a SET o CYCLE a SET is_cycle TO \'Y\' DEFAULT \'N\' SELECT a FROM r ORDER BY o", read="oracle").sql("oracle")',
   'parse_one("WITH RECURSIVE g(id, link) AS (SELECT 1, 2 UNION ALL SELECT g.id, g.link FROM g) CYCLE id SET is_cycle TO \'Y\' DEFAULT \'N\' USING path SELECT * FROM g", read="postgres").sql("postgres")']),
'818483464b': ("Transpiling Spark's SLICE(arr, start, length) to DuckDB's ARRAY_SLICE(arr, start, end) gets the bounds wrong: Spark's third "
  "argument is a length and a negative start counts from the end, while DuckDB takes an inclusive end position. The DuckDB output must "
  "select the same elements for normal, zero-length, very large and negative starts, and Spark, Spark 2 and Databricks round-trips must "
  "stay unchanged.",
  ['transpile("SELECT SLICE(ARRAY(1, 2, 3), 2, 4)", read="spark", write="duckdb")[0]', 'transpile("SLICE(ARRAY(1, 2, 3), 3, 0)", read="spark", write="duckdb")[0]',
   'transpile("SLICE(ARRAY(1, 2, 3), -2, 2)", read="spark", write="duckdb")[0]']),
'7d9a6cd599': ("Athena CREATE TABLE ... AS USING EXTERNAL FUNCTION f(x VARCHAR) RETURNS VARCHAR LAMBDA 'l' SELECT ... fails. It should still "
  "produce an exp.Create whose query part is kept verbatim as an exp.Command starting with USING (with sqlglot's usual warning about "
  "falling back to a Command), and round-trip; ordinary CTAS must keep parsing normally.",
  ['parse_one("CREATE TABLE t WITH (format=\'PARQUET\') AS USING EXTERNAL FUNCTION f(x VARCHAR) RETURNS VARCHAR LAMBDA \'l\' SELECT f(\'a\') AS b", read="athena").sql("athena")',
   'type(parse_one("CREATE TABLE t WITH (format=\'PARQUET\') AS USING EXTERNAL FUNCTION f(x VARCHAR) RETURNS VARCHAR LAMBDA \'l\' SELECT f(\'a\') AS b", read="athena")).__name__']),
'af9915fa4c': ("MySQL's WEIGHT_STRING(str AS CHAR(N)) and WEIGHT_STRING(str AS BINARY(N)) fail with \"Expecting )\". WEIGHT_STRING with one "
  "argument or with an AS type should parse into a dedicated exp.WeightString expression that keeps the type, and round-trip; calls "
  "with other argument counts, such as WEIGHT_STRING('ab', 0, 3, 0), should stay an anonymous function that keeps its name as written.",
  ['parse_one("SELECT WEIGHT_STRING(\'1\' AS CHAR(1))", read="mysql").sql("mysql")', 'parse_one("SELECT WEIGHT_STRING(\'ab\' AS BINARY(4))", read="mysql").sql("mysql")',
   'type(parse_one("SELECT WEIGHT_STRING(\'ab\')", read="mysql").selects[0]).__name__']),
'862fd55467': ("Trino temporal types and literals lose their fractional-second precision. In Trino, CAST(... AS TIMESTAMP(n)) and TIME(n), "
  "with or without WITH TIME ZONE, should keep the precision, and TIMESTAMP/TIME '...' literals should become casts whose precision "
  "matches the literal's fractional digits. Presto only supports millisecond precision, so generating Presto from any other precision "
  "should drop it and warn \"Presto only supports millisecond precision for temporal types\" (raising under ErrorLevel.RAISE).",
  ['parse_one("SELECT TIMESTAMP \'2020-01-01 00:00:00.10\'", read="trino").sql("trino")', 'parse_one("CAST(\'2020-01-01 00:00:00.123\' AS TIMESTAMP(6))", read="trino").sql("presto")',
   'parse_one("SELECT TIME \'12:00:00.1\'", read="trino").sql("trino")']),
'268ad021b8': ("ALTER TABLE ... DROP COLUMN a, b (several columns after one DROP COLUMN) falls back to a generic Command. It should parse into "
  "an exp.Alter with a single exp.Drop of kind COLUMN listing all the columns and round-trip, in Snowflake, "
  "without breaking how other dialects already handle DROP (for example MySQL's DROP COLUMN a, ALGORITHM=INPLACE or DROP PRIMARY KEY).",
  ['type(parse_one("ALTER TABLE tbl DROP COLUMN col1, col2", read="snowflake")).__name__',
   '[t.name for d in parse_one("ALTER TABLE tbl DROP COLUMN col1, col2", read="snowflake").find_all(exp.Drop) for t in d.args.get("tables") or []]',
   ]),
}
