Feature: Writes hidden inside read-shaped syntax are denied

  The classifier sees through smuggling: data-modifying CTEs (a CTE
  body that is a DeleteStmt, not a SelectStmt), keywords hidden in
  comments or string literals, SELECT INTO (intoClause), FOR UPDATE
  (lockingClause), EXPLAIN ANALYZE (options carrying analyze), stacked
  statements, and the COPY PROGRAM / SET / DO / CALL / MERGE /
  TRUNCATE / GRANT / function-in-FROM write paths. Each row below
  quotes the verbatim denial the classifier must return.

  @feature-gate.uc-write-smuggled @scenario-positive @dependency-none
  Scenario Outline: a smuggled write is denied with its verbatim denial
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: <denial>"

    Examples:
      | sql                                                              | denial                          |
      | WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x            | DeleteStmt                      |
      | WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x | InsertStmt                      |
      | WITH x AS (UPDATE t SET a = 1 RETURNING *) SELECT * FROM x       | UpdateStmt                      |
      | WITH x AS (DELETE /* hidden */ FROM t RETURNING *) SELECT * FROM x | DeleteStmt                   |
      | SELECT * INTO n FROM t                                           | IntoClause                      |
      | SELECT 'INTO' INTO n FROM t                                       | IntoClause                      |
      | SELECT * FROM t FOR UPDATE                                       | LockingClause                   |
      | SELECT * FROM t FOR UPDATE /* trailing */                        | LockingClause                   |
      | EXPLAIN ANALYZE SELECT * FROM t                                  | ExplainStmt with options        |
      | EXPLAIN /* comment */ ANALYZE SELECT * FROM t                    | ExplainStmt with options        |
      | SELECT * FROM pg_read_file('pg_hba.conf')                         | function pg_read_file           |

  @feature-gate.uc-write-smuggled @scenario-negative @dependency-none
  Scenario Outline: a stacked or utility write path is denied verbatim
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: <denial>"

    Examples:
      | sql                                                              | denial                                     |
      | SELECT 1; DELETE FROM t                                          | exactly one statement is required, got 2   |
      | SELECT 1; SELECT 2 -- stacked read-smuggled stack                | exactly one statement is required, got 2   |
      | COPY t FROM PROGRAM 'id'                                         | CopyStmt                                   |
      | SET statement_timeout = 0                                        | VariableSetStmt                            |
      | SET TRANSACTION READ WRITE                                       | VariableSetStmt                            |
      | DO $$ BEGIN RAISE NOTICE 'hi'; END $$                            | DoStmt                                     |
      | CALL p_procedure()                                               | CallStmt                                   |
      | MERGE INTO t USING s ON t.a = s.a WHEN MATCHED THEN DELETE       | MergeStmt                                  |
      | TRUNCATE t                                                       | TruncateStmt                               |
      | GRANT SELECT ON t TO readonly_mcp                                | GrantStmt                                  |
