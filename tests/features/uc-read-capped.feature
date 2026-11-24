Feature: Every result is bounded by the row cap

  No read returns more than ROW_CAP rows: over-cap results carry
  truncated=true. A comment-smuggled cap bypass is still truncated.

  @feature-read.uc-read-capped @scenario-positive @dependency-postgres-18
  Scenario: an over-cap query returns row-cap rows flagged truncated
    Given the gate is closed
    When the agent calls "execute_sql" with over-cap SELECT SQL
    Then the call succeeds
    And the result has exactly ROW_CAP rows
    And the result field "truncated" is true

  @feature-read.uc-read-capped @scenario-negative @dependency-postgres-18
  Scenario Outline: a comment-smuggled cap bypass is still truncated
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call succeeds
    And the result field "truncated" is true

    Examples:
      | sql                                                              |
      | SELECT /* bypass */ generate_series(1, 2000) AS n                |
      | SELECT generate_series(1, 2000) AS n -- trailing comment bypass  |
