Feature: Writes are denied while the gate is closed

  Out of the box (PG_ALLOW_WRITES unset or anything but exactly "1")
  every write is denied with a verbatim node denial. Comments hiding
  the keyword change nothing.

  @feature-gate.uc-write-denied-default @scenario-positive @dependency-none
  Scenario Outline: a plain write is denied while the gate is closed
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: <node> is not allowed while PG_ALLOW_WRITES is closed"

    Examples:
      | sql                                | node       |
      | INSERT INTO t VALUES (1)           | InsertStmt |
      | UPDATE t SET a = 1                 | UpdateStmt |
      | DELETE FROM t                      | DeleteStmt |
      | DROP TABLE t                       | DropStmt   |
      | CREATE TABLE t (a int)             | CreateStmt |
      | ALTER TABLE t ADD COLUMN b int     | AlterTableStmt |

  @feature-gate.uc-write-denied-default @scenario-negative @dependency-none
  Scenario Outline: a comment-obfuscated write is still denied
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: <node> is not allowed while PG_ALLOW_WRITES is closed"

    Examples:
      | sql                                  | node       |
      | /* hidden */ INSERT INTO t VALUES (1) | InsertStmt |
      | INSERT /* mid */ INTO t VALUES (1)  | InsertStmt |
      | UPDATE /* mid */ t SET a = 1         | UpdateStmt |
