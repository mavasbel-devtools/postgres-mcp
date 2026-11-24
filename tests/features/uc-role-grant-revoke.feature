Feature: Grant and revoke open and close write paths

  Write exercises grant, verify the write applies, then revoke and
  verify the same write fails 42501: no grant may leak. Live tests
  touch only the postgres database and always drop temporary roles.

  @feature-role.uc-role-grant-revoke @scenario-positive @dependency-postgres-18
  Scenario: a granted INSERT applies
    Given the gate is open
    And write granted on the exercise table
    When the agent calls "execute_sql" with granted INSERT SQL
    Then the call succeeds
    And the result reports row count 1

  @feature-role.uc-role-grant-revoke @scenario-negative @dependency-postgres-18
  Scenario: the post-revoke INSERT fails 42501
    Given the gate is open
    And the write grant revoked on the exercise table
    When the agent calls "execute_sql" with revoked INSERT SQL
    Then the call fails mentioning "42501"
    And the failure mentions "permission denied for table cuenta_p07"
