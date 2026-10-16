"""Symptom-only bug reports for the multi-file tasks. Each example's "currently"/"expected" output is computed by
running it at the base and fix commits (build_tasks3.py)."""

SPEC = {
'f5dd70bff7': ("Integer division (x DIV y in Hive, Spark and MySQL, x // y in DuckDB, DIV(x, y) in BigQuery) truncates towards "
  "zero, but sqlglot's rewrite for dialects without an integer-division operator does not preserve that: Presto gets "
  "CAST(CAST(x AS DOUBLE) / y AS INTEGER), which rounds instead of truncating and can overflow, and the generic integer-division "
  "cast (also produced by the Python expression builder, x // 1) uses INT instead of BIGINT. Separately, a one-argument TRUNC(n) "
  "from Oracle or Snowflake transpiled to MySQL must give a valid TRUNCATE call with an explicit 0 decimals argument.",
  ['transpile("SELECT x DIV y", read="hive", write="presto")[0]',
   '(exp.column("x") // 1).sql()',
   'transpile("SELECT TRUNC(3.14159)", read="oracle", write="mysql")[0]']),
'eeece5a564': ("ORDER BY and pagination (LIMIT, OFFSET, FETCH, TOP) that belong to one branch of a set operation (UNION, INTERSECT, "
  "EXCEPT) are not kept in that branch, and pagination of the whole set operation is not applied to all of it, when generating "
  "dialects that need explicit scoping. A branch's own ORDER BY ... FETCH FIRST must stay with that branch: parenthesised for "
  "DuckDB and Postgres, wrapped in SELECT * FROM (...) for SQLite and T-SQL (T-SQL needs an alias and OFFSET 0 ROWS), unchanged "
  "for ClickHouse; pagination after the last branch that applies to the whole set operation must wrap it where the dialect "
  "requires (e.g. ClickHouse).",
  ['transpile("SELECT 1 AS x ORDER BY x NULLS FIRST FETCH FIRST 1 ROWS ONLY UNION ALL SELECT 2 AS x", write="duckdb")[0]',
   'transpile("SELECT 1 AS x ORDER BY x NULLS FIRST FETCH FIRST 1 ROWS ONLY UNION ALL SELECT 2 AS x", write="tsql")[0]',
   'transpile("SELECT 1 AS x ORDER BY x NULLS FIRST FETCH FIRST 1 ROWS ONLY UNION ALL SELECT 2 AS x", write="sqlite")[0]',
   'transpile("SELECT * FROM a UNION SELECT * FROM b OFFSET 1", write="clickhouse")[0]']),
'6581f8c38b': ("Spark 3 parses MM and dd in date formats strictly (exactly two digits), while %m and %d in lenient dialects such as "
  "DuckDB and MySQL accept one or two digits. Transpiling a lenient date format to Spark, Hive or Databricks therefore gives a "
  "format that rejects inputs the source accepted. A lax month/day from a lenient dialect must become M/d in Spark-family "
  "dialects, while a zero-padded MM/dd written in Spark still round-trips (and maps to %m/%d for lenient dialects); formatting "
  "functions such as DATE_FORMAT keep MM/dd, since their output is always padded.",
  ['transpile("SELECT STRPTIME(\'2016-1-1\', \'%Y-%m-%d\')", read="duckdb", write="spark")[0]',
   'transpile("SELECT STR_TO_DATE(\'04/05/2013\', \'%m/%d/%Y\')", read="mysql", write="spark")[0]']),
'66316e335f': ("Spark 3 parses HH, hh, mm and ss in time formats strictly (exactly two digits), while %H, %M and %S in lenient dialects "
  "such as DuckDB and MySQL accept one or two digits. Transpiling a lenient time format to Spark, Hive or Databricks therefore "
  "gives a format that rejects inputs the source accepted. Lax hour/minute/second fields from a lenient dialect must become H, h, "
  "m and s in Spark-family dialects (as month and day already become M and d), while a zero-padded HH:mm:ss written in Spark still "
  "round-trips and maps to %H:%M:%S for lenient dialects. A time field directly adjacent to other digits (yyyyMMddHHmmss) stays "
  "zero-padded, since a digit run cannot be split.",
  ['transpile("SELECT STRPTIME(\'2016-1-1 3:4:5\', \'%Y-%m-%d %H:%M:%S\')", read="duckdb", write="spark")[0]',
   'transpile("SELECT STR_TO_DATE(\'04/05/2013 01:02:03\', \'%m/%d/%Y %H:%i:%s\')", read="mysql", write="spark")[0]',
   'transpile("SELECT STR_TO_TIME(x, \'%Y-%m-%d %H:%M:%S\')", write="spark")[0]']),
'2aae7f7605': ("In Postgres, x IS NOT NULL is normalised to NOT x IS NULL. sqlglot should keep IS NOT NULL as written, represented as an "
  "exp.Is whose negate flag is set, while NOT x IS NULL stays as written too; the Postgres shorthands NOTNULL and ISNULL should read "
  "as IS NOT NULL / IS NULL, IS NOT UNKNOWN as IS NOT NULL, and constant folding in the optimizer must respect the negation "
  "(NULL IS NOT NULL simplifies to FALSE).",
  ['parse_one("SELECT r IS NOT NULL FROM t", read="postgres").sql("postgres")',
   'parse_one("r IS NOT NULL", read="postgres").args.get("negate")',
   'parse_one("SELECT r NOTNULL FROM t", read="postgres").sql("postgres")']),
'646295528c': ("T-SQL's DAY(x), MONTH(x) and YEAR(x) accept a date or a string, but transpiling them to Postgres gives functions "
  "Postgres does not have. They should become EXTRACT(DAY FROM CAST(x AS DATE)) and so on in Postgres (no cast needed when the "
  "argument is already known to be a DATE after type annotation, and an unsupported error when its type is known not to be a "
  "date), and T-SQL round-trips must not gain casts.",
  ['transpile("SELECT DAY(x), MONTH(x), YEAR(x)", read="tsql", write="postgres")[0]']),
'7f1cf60c88': ("MySQL ALTER TABLE statements that only set table options or partitioning, without an ADD/DROP/... action, fall back "
  "to a Command or are split wrongly, e.g. ALTER TABLE t FORCE, ALTER TABLE t ROW_FORMAT=COMPRESSED KEY_BLOCK_SIZE=8 and ALTER "
  "TABLE t ENGINE=InnoDB PARTITION BY LIST (a) (PARTITION p0 VALUES IN (1)). Actions should be optional: such statements should "
  "parse into exp.Alter, table options must be kept as options (generated comma-separated, after any actions), and partition "
  "definitions sqlglot cannot model should still fall back to a Command with the usual warning.",
  ['type(parse_one("ALTER TABLE t FORCE", read="mysql")).__name__',
   'parse_one("ALTER TABLE t ROW_FORMAT=COMPRESSED KEY_BLOCK_SIZE=8", read="mysql").sql("mysql")',
   'parse_one("ALTER TABLE t COMMENT=\'hi\', ADD COLUMN c INT", read="mysql").sql("mysql")']),
'66ecca3397': ("ClickHouse ALTER TABLE ... MODIFY COLUMN is not parsed as a column change. It should parse into exp.Alter with an "
  "exp.AlterColumn action and be generated canonically as ALTER COLUMN ... TYPE, including with IF EXISTS; MODIFY COLUMN forms "
  "sqlglot does not support (for example REMOVE DEFAULT) should still fall back to a Command.",
  ['parse_one("ALTER TABLE t MODIFY COLUMN c Int64", read="clickhouse").sql("clickhouse")',
   'type(parse_one("ALTER TABLE t MODIFY COLUMN c Int64", read="clickhouse").args["actions"][0]).__name__',
   'parse_one("ALTER TABLE t MODIFY COLUMN IF EXISTS c Int64", read="clickhouse").sql("clickhouse")']),
}
