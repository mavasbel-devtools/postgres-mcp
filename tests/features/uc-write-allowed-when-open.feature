Feature: Genuine writes apply only when the gate is open

  With PG_ALLOW_WRITES exactly "1" a genuine write applies (subject to
  the role's grants). The function denylist stays enforced in both
  gates as defence in depth.

  @feature-gate.uc-write-allowed-when-open @scenario-positive @dependency-postgres-18
  Scenario: an INSERT applies when the gate is open
    Given the gate is open
    When the agent calls "execute_sql" with granted INSERT SQL
    Then the call succeeds
    And the result reports row count 1

  @feature-gate.uc-write-allowed-when-open @scenario-negative @dependency-none
  Scenario Outline: a dangerous function is still denied when the gate is open
    Given the gate is open
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: function <name> is not allowed while PG_ALLOW_WRITES is closed"

    Examples:
      | sql                            | name                |
      | SELECT pg_terminate_backend(1) | pg_terminate_backend |
      | SELECT set_config('a','b',false) | set_config         |
