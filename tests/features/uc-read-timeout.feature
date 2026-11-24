Feature: Every call is bounded by the statement timeout

  A fast allowed SELECT returns rows within budget. A slow but allowed
  SELECT is aborted by statement_timeout and surfaces sqlstate 57014.
  (pg_sleep cannot be the slow vehicle: it is deny-listed.)

  @feature-read.uc-read-timeout @scenario-positive @dependency-postgres-18
  Scenario: a fast query returns rows within budget
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "SELECT 1"}
    Then the call succeeds
    And the result rows are [(1,)]

  @feature-read.uc-read-timeout @scenario-negative @dependency-postgres-18
  Scenario: a slow query is aborted with a timeout error
    Given the gate is closed
    When the agent calls "execute_sql" with slow but allowed SELECT SQL
    Then the call fails mentioning "57014"
    And the failure mentions "statement timeout"
