"""Symptom-only prompts for the mined ripple commits (the change asked for is the parent-side change the commit made;
child dialects are never mentioned). Example outputs are computed at the base and fix commits by build_tasks5.py."""

SPEC = {
'ba0bff3d91': ("JSONPath bracket unions lose members that are falsey: in Presto, JSON_EXTRACT(x, '$[1,0]') and "
  "JSON_EXTRACT(x, '$[\"a\",\"\"]') come back without the 0 or the empty-string member. Union members such as 0 and \"\" "
  "must be kept by the JSONPath parser and round-trip unchanged.",
  ['parse_one("SELECT JSON_EXTRACT(x, \'$[1,0]\')", read="presto").sql("presto")',
   'parse_one("""SELECT JSON_EXTRACT(x, \'$["a",""]\')""", read="presto").sql("presto")',
   "parse_one('SELECT JSON_EXTRACT_SCALAR(x, \\'$[\"\"]\\')', read='presto').sql('presto')"]),
'efbc5e220c': ("Postgres TO_CHAR / TO_TIMESTAMP format tokens for month and weekday names, AM/PM and HH are not mapped, so "
  "formats such as 'Mon YYYY', 'Month', 'Day', 'Dy', 'HH12:MI AM' transpile wrongly to other dialects (e.g. ClickHouse) "
  "or do not round-trip. These tokens should map to their equivalents and Postgres output should keep them.",
  ['transpile("SELECT TO_CHAR(dt, \'Mon YYYY\')", read="postgres", write="clickhouse")[0]',
   'transpile("SELECT TO_CHAR(dt, \'Day\')", read="postgres", write="clickhouse")[0]',
   'transpile("SELECT TO_CHAR(dt, \'HH12:MI AM\')", read="postgres", write="clickhouse")[0]',
   'parse_one("SELECT TO_TIMESTAMP(\'05 Dec 2000 10:00 AM\', \'DD Mon YYYY HH12:MI AM\')", read="postgres").sql("postgres")']),
'5d997d94d8': ("ALTER TABLE ... DROP without the COLUMN keyword (ALTER TABLE t DROP b, ALTER TABLE t DROP b, DROP c RESTRICT) "
  "is not parsed as dropping a column in MySQL and Postgres. A bare DROP of a name should mean DROP COLUMN, also for column "
  "names that are keywords elsewhere (date, materialized, concurrently), and be written as DROP COLUMN.",
  ['parse_one("ALTER TABLE t DROP b, DROP c", read="mysql").sql("mysql")',
   'parse_one("ALTER TABLE t DROP b RESTRICT", read="postgres").sql("postgres")',
   'parse_one("ALTER TABLE t DROP concurrently", read="postgres").sql("postgres")']),
'7f1cf60c88': ("MySQL ALTER TABLE statements that only set table options or partitioning, without an ADD/DROP/... action, fall back "
  "to a Command or are split wrongly, e.g. ALTER TABLE t FORCE, ALTER TABLE t ROW_FORMAT=COMPRESSED KEY_BLOCK_SIZE=8 and ALTER "
  "TABLE t ENGINE=InnoDB PARTITION BY LIST (a) (PARTITION p0 VALUES IN (1)). Actions should be optional: such statements should "
  "parse into exp.Alter, table options must be kept as options (generated comma-separated, after any actions), and partition "
  "definitions sqlglot cannot model should still fall back to a Command with the usual warning.",
  ['type(parse_one("ALTER TABLE t FORCE", read="mysql")).__name__',
   'parse_one("ALTER TABLE t ROW_FORMAT=COMPRESSED KEY_BLOCK_SIZE=8", read="mysql").sql("mysql")',
   'parse_one("ALTER TABLE t COMMENT=\'hi\', ADD COLUMN c INT", read="mysql").sql("mysql")']),
'9114355463': ("MySQL lets CONSTRAINT appear without a constraint name before UNIQUE, PRIMARY KEY, CHECK and FOREIGN KEY, in both "
  "CREATE TABLE and ALTER TABLE ... ADD. sqlglot fails on these or misreads the next keyword as the name. They should parse, "
  "and the nameless CONSTRAINT keyword should be dropped on output.",
  ['parse_one("ALTER TABLE t ADD CONSTRAINT UNIQUE uq_a (a)", read="mysql").sql("mysql")',
   'parse_one("CREATE TABLE t (a INT, CONSTRAINT PRIMARY KEY (a))", read="mysql").sql("mysql")',
   'parse_one("CREATE TABLE t (a INT CONSTRAINT CHECK (a > 0))", read="mysql").sql("mysql")']),
'862fd55467': ("Trino drops the precision of temporal literals: TIMESTAMP '2012-08-08 01:00:00.123' and TIME literals lose their "
  "fractional-second precision when parsed and generated, so the type changes. Trino keeps the precision implied by the literal "
  "(TIMESTAMP(3) for three fractional digits, TIMESTAMP(0) for none); sqlglot should preserve it for all temporal literals.",
  ['parse_one("SELECT TIMESTAMP \'2012-08-08 01:00:00.123\'", read="trino").sql("trino")',
   'parse_one("SELECT TIMESTAMP \'2012-08-08 01:00:00\'", read="trino").sql("trino")',
   'parse_one("SELECT TIME \'01:02:03.456\'", read="trino").sql("trino")']),
'4ada15a429': ("INSERT ... ON CONFLICT targets that contain expressions, not only column names, are not parsed: ON CONFLICT(a, "
  "LOWER(b)) DO UPDATE ..., targets with COLLATE / ASC / DESC, CASE expressions, and a WHERE clause on the target fail in "
  "Postgres and SQLite. Conflict targets should accept index expressions and round-trip.",
  ['parse_one("INSERT INTO tbl (a, b) VALUES (1, \'x\') ON CONFLICT(a, LOWER(b)) DO UPDATE SET b = excluded.b", read="postgres").sql("postgres")',
   'parse_one("INSERT INTO tbl (x, y) VALUES (1, \'a\') ON CONFLICT(x, LOWER(y) COLLATE NOCASE ASC, y DESC) DO NOTHING", read="sqlite").sql("sqlite")',
   'parse_one("INSERT INTO tbl (x, y) VALUES (1, \'a\') ON CONFLICT(x) WHERE x > 0 DO UPDATE SET y = excluded.y", read="sqlite").sql("sqlite")']),
'a313c8bee1': ("The right-hand side of an assignment in UPDATE ... SET (and in MERGE ... UPDATE SET, ON DUPLICATE KEY UPDATE and "
  "ON CONFLICT ... DO UPDATE SET) cannot be a boolean expression: UPDATE t SET a = x OR y misparses or fails. Assignments should "
  "accept full boolean expressions (OR, AND, comparisons) in all these places and round-trip.",
  ['parse_one("UPDATE t SET a = x OR y AND z, b = x = y WHERE id = 1", read="postgres").sql("postgres")',
   'parse_one("INSERT INTO t (id, a) VALUES (1, FALSE) ON DUPLICATE KEY UPDATE a = x OR y, b = x AND y", read="mysql").sql("mysql")',
   'parse_one("INSERT INTO t (id, a) VALUES (1, FALSE) ON CONFLICT(id) DO UPDATE SET a = t.x OR t.y, b = t.x AND t.y WHERE t.id = 1 RETURNING a", read="postgres").sql("postgres")']),
'd7fd83a7dc': ("START WITH is tokenized as a single keyword, so a table or view named start followed by WITH breaks: CREATE VIEW v "
  "AS SELECT * FROM start WITH CHECK OPTION, CREATE VIEW start WITH (security_barrier=TRUE) AS SELECT 1, SELECT x FROM start WITH "
  "(NOLOCK) fail or misparse. START and WITH should be separate tokens; hierarchical queries (START WITH ... CONNECT BY) must keep "
  "working, and two START WITH clauses in one query should raise a ParseError saying \"Found multiple 'START WITH' clauses\".",
  ['parse_one("CREATE VIEW start WITH (security_barrier=TRUE) AS SELECT 1", read="postgres").sql("postgres")',
   'parse_one("SELECT x FROM start WITH (NOLOCK)", read="tsql").sql("tsql")',
   'parse_one("SELECT id FROM t START WITH (x) CONNECT BY PRIOR id = parent_id", read="oracle").sql("oracle")']),
}
