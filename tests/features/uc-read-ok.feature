Feature: Plain SELECT returns rows

  A plain SELECT (including TABLE and VALUES, which parse to a bare
  SelectStmt) runs against the live database and returns its rows.
  An unreachable host fails with a connection error and runs nothing.

  @feature-read.uc-read-ok @scenario-positive @dependency-postgres-18
  Scenario Outline: a plain read returns its rows
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call succeeds
    And the result rows are <rows>

    Examples:
      | sql         | rows  |
      | SELECT 1    | [(1,)] |
      | TABLE t_one | [(1,)] |
      | VALUES (1)  | [(1,)] |

  @feature-read.uc-read-ok @scenario-negative @dependency-postgres-18
  Scenario: an unreachable host fails without running anything
    Given the database host is unreachable
    When the agent calls "execute_sql" with {"sql": "SELECT 1"}
    Then the call fails mentioning "08001"
    And no statement ran on the server
