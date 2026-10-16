"""Symptom-only bug reports for ripple-prone tasks (fixes that edit a parent dialect). Example outputs are computed
at the base and fix commits by build_tasks4.py."""

SPEC = {
'676ba36549': ("MySQL foreign keys can carry an index name (ALTER TABLE t ADD FOREIGN KEY fk (a) REFERENCES p (a)), but sqlglot "
  "does not parse the name. Named foreign keys should parse and round-trip, also when written after a bare CONSTRAINT keyword, "
  "which is then dropped.",
  ['parse_one("ALTER TABLE t ADD FOREIGN KEY fk (a) REFERENCES p (a)", read="mysql").sql("mysql")',
   'parse_one("ALTER TABLE t ADD CONSTRAINT FOREIGN KEY fk (a) REFERENCES p (a)", read="mysql").sql("mysql")']),
'9114355463': ("MySQL lets CONSTRAINT appear without a constraint name before UNIQUE, PRIMARY KEY, CHECK and FOREIGN KEY, in both "
  "CREATE TABLE and ALTER TABLE ... ADD. sqlglot fails on these or misreads the next keyword as the name. They should parse, "
  "and the nameless CONSTRAINT keyword should be dropped on output.",
  ['parse_one("ALTER TABLE t ADD CONSTRAINT UNIQUE uq_a (a)", read="mysql").sql("mysql")',
   'parse_one("CREATE TABLE t (a INT, CONSTRAINT PRIMARY KEY (a))", read="mysql").sql("mysql")',
   'parse_one("CREATE TABLE t (a INT CONSTRAINT CHECK (a > 0))", read="mysql").sql("mysql")']),
'97a2fa2ed6': ("MySQL index options (KEY_BLOCK_SIZE, COMMENT, USING) written after a PRIMARY KEY in ALTER TABLE ... ADD or inside "
  "CREATE TABLE are misplaced or rejected, and table options such as KEY_BLOCK_SIZE and MAX_ROWS after the column list are "
  "not kept as table options. Index options must stay with their index and table options with the table.",
  ['parse_one("ALTER TABLE t ADD PRIMARY KEY (a) COMMENT \'c\'", read="mysql").sql("mysql")',
   'parse_one("CREATE TABLE t (a INT) ENGINE=InnoDB KEY_BLOCK_SIZE=8 MAX_ROWS=100", read="mysql").sql("mysql")']),
'47b94d424a': ("MySQL table options may be separated by spaces instead of commas (CHARSET=utf8mb4 ENGINE=InnoDB), and CHARSET / "
  "CHAR SET are synonyms of CHARACTER SET, also on columns. sqlglot does not accept these forms; they should parse, CHARSET "
  "should be written as CHARACTER SET, and in ALTER TABLE the options should be written comma-separated after the actions.",
  ['parse_one("CREATE TABLE t (a VARCHAR(5) CHARSET utf8mb4 COLLATE utf8mb4_bin) CHARSET=utf8mb4 ENGINE=InnoDB", read="mysql").sql("mysql")',
   'parse_one("ALTER TABLE t ADD COLUMN a VARCHAR(5) CHARSET utf8mb4 COLLATE utf8mb4_bin, CHARSET=utf8mb4 ENGINE=InnoDB", read="mysql").sql("mysql")']),
'9ec72cf883': ("MySQL allows the index type before the key parts (UNIQUE KEY u USING BTREE (c)) and a UNIQUE without a name "
  "(UNIQUE USING BTREE (a)). sqlglot misparses these. They should parse, and be written with the index type after the key parts "
  "(UNIQUE u (c) USING BTREE); an index literally named `using` must still work.",
  ['parse_one("ALTER TABLE t ADD UNIQUE KEY u USING BTREE (c)", read="mysql").sql("mysql")',
   'parse_one("CREATE TABLE t (a INT, UNIQUE USING BTREE (a))", read="mysql").sql("mysql")']),
'8b374bd525': ("MySQL UNIQUE keys accept index options after the key parts (USING BTREE, COMMENT, VISIBLE / INVISIBLE, "
  "KEY_BLOCK_SIZE). sqlglot fails on or drops them. They should parse into the unique constraint's options (INVISIBLE gives "
  "visible = False) and round-trip.",
  ['parse_one("ALTER TABLE t ADD UNIQUE KEY uq (a) USING BTREE COMMENT \'why\' INVISIBLE", read="mysql").sql("mysql")',
   'parse_one("CREATE TABLE foo (a BIGINT, UNIQUE KEY d (a) KEY_BLOCK_SIZE=8)", read="mysql").sql("mysql")']),
'03c96cbbfd': ("MySQL treats SOUNDS LIKE as the two words SOUNDS and LIKE, so a column named sounds followed by LIKE must parse "
  "as an ordinary LIKE. sqlglot tokenizes SOUNDS LIKE as one operator and breaks such queries.",
  ['parse_one("SELECT * FROM t WHERE sounds LIKE \'a%\'", read="mysql").sql("mysql")']),
'6b9cb87bd0': ("In Postgres the quoted type \"char\" is a distinct one-byte type, not CHAR, but sqlglot drops the quotes and turns it "
  "into CHAR. The quotes must be preserved (also for arrays and :: casts), while an unquoted or upper-case \"CHAR\" stays CHAR.",
  ['parse_one(\'CAST(65 AS "char")\', read="postgres").sql("postgres")',
   'parse_one(\'65::"char"\', read="postgres").sql("postgres")']),
'930f1a32f7': ("When JSON_EXTRACT with a compound path expression is written with Postgres's -> operator (from DuckDB or Postgres), "
  "sqlglot drops the parentheses around the right-hand side, which changes the meaning because of operator precedence. The "
  "right-hand side must stay grouped, e.g. a -> ('x' || 'y').",
  ['transpile("SELECT JSON_EXTRACT(a, \'x\' || \'y\')", read="duckdb", write="postgres")[0]',
   'transpile("SELECT JSON_EXTRACT(a, 1 + 2)", read="postgres", write="postgres")[0]']),
'5e6887adc8': ("T-SQL accepts a table hint without WITH directly after a table name, e.g. SELECT * FROM t (NOLOCK), also for "
  "qualified and bracketed names. sqlglot parses (NOLOCK) as something else. It should parse as the same table hint as "
  "WITH (NOLOCK) and be written that way.",
  ['parse_one("SELECT * FROM t (NOLOCK)", read="tsql").sql("tsql")',
   'parse_one("SELECT * FROM [dbo].[t] (NOLOCK)", read="tsql").sql("tsql")']),
'1e6c6c58e1': ("T-SQL JSON_QUERY and JSON_VALUE grow on every round trip: each pass wraps them in another "
  "ISNULL(JSON_QUERY(...), JSON_VALUE(...)). JSON_QUERY and JSON_VALUE must round-trip as themselves; only a generic JSON "
  "extraction whose result kind is unknown needs the ISNULL form, and that form must itself be stable.",
  ['parse_one("JSON_QUERY(x, \'$.a\')", read="tsql").sql("tsql")',
   'parse_one("ISNULL(JSON_QUERY(x, \'$.a\'), JSON_VALUE(x, \'$.a\'))", read="tsql").sql("tsql")']),
'03744a2a83': ("Hive and Spark ALTER TABLE ... REPLACE COLUMNS (col type [COMMENT ...], ...) [CASCADE|RESTRICT] falls back to a "
  "generic Command. It should parse into an exp.Alter whose action is a dedicated REPLACE COLUMNS node, and round-trip; column "
  "definitions sqlglot cannot parse yet should keep falling back to a Command.",
  ['type(parse_one("ALTER TABLE X REPLACE COLUMNS (y INT COMMENT \'c\', z STRING) CASCADE", read="hive")).__name__',
   'parse_one("ALTER TABLE X REPLACE COLUMNS (y INT COMMENT \'c\', z STRING) CASCADE", read="spark").sql("spark")']),
'0b00178215': ("Spark's ALTER TABLE ... DROP COLUMN and DROP COLUMNS forms (with IF EXISTS, nested names like a.b, a parenthesised "
  "list, keyword-like names such as from) fall back to a Command or parse wrongly. All forms should give an exp.Alter and "
  "round-trip, with a bare list DROP COLUMNS a, b written as DROP COLUMNS (a, b).",
  ['type(parse_one("ALTER TABLE t DROP COLUMNS (a, b.c)", read="spark")).__name__',
   'parse_one("ALTER TABLE t DROP COLUMNS a, b", read="spark").sql("spark")']),
'3086608e6f': ("Trino's JSON_QUERY requires a path mode, but sqlglot writes JSON_QUERY(x, '$.a') when transpiling to Trino. Paths "
  "without an explicit mode must be prefixed with the lax mode specifier: JSON_QUERY(x, 'lax $.a').",
  ['transpile("SELECT JSON_QUERY(x, \'$.a\')", read="tsql", write="trino")[0]']),
}
