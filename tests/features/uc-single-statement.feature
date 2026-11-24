Feature: Exactly one statement per call

  The classifier owns single-statement enforcement (n_stmts == 1):
  other protocols would run a stack, so the check cannot rely on the
  driver's prepared-statement rejection alone.

  @feature-gate.uc-single-statement @scenario-positive @dependency-postgres-18
  Scenario: a single SELECT passes the statement-count check
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "SELECT 1"}
    Then the call succeeds
    And the result rows are [(1,)]

  @feature-gate.uc-single-statement @scenario-negative @dependency-none
  Scenario Outline: a stacked statement string is denied before execution
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: exactly one statement is required, got <n>"

    Examples:
      | sql                       | n |
      | SELECT 1; SELECT 2        | 2 |
      | SELECT 1; DELETE FROM t   | 2 |
      | SELECT 1; SELECT 2; SELECT 3 | 3 |
