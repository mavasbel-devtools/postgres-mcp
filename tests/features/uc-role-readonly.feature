Feature: The revoked read-only role is the final enforcement layer

  Reads serve fine as the revoked role; the role (not the
  transaction) is what stops writes: INSERT as the role fails 42501.
  A wrong password fails authentication with 28P01.

  @feature-role.uc-role-readonly @scenario-positive @dependency-postgres-18
  Scenario: reads serve as the revoked role while writes fail 42501
    Given the readonly_mcp role with revoked write grants
    When the agent calls "execute_sql" with {"sql": "SELECT 1"}
    Then the call succeeds
    And the result rows are [(1,)]
    When the agent calls "execute_sql" with {"sql": "INSERT INTO cuenta_p07 VALUES (1)"}
    Then the call fails mentioning "42501"

  @feature-role.uc-role-readonly @scenario-negative @dependency-postgres-18
  Scenario: a wrong password fails authentication
    Given the readonly_mcp role with a wrong password in env
    When the agent calls "execute_sql" with {"sql": "SELECT 1"}
    Then the call fails mentioning "28P01"
    And the failure mentions "password authentication failed for user readonly_mcp"
