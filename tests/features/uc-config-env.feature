Feature: All configuration comes from the environment

  Credentials are never tool parameters. Valid env connects; a
  malformed value fails loudly with a fixed config error. Any
  PG_ALLOW_WRITES value other than exactly "1" means closed and is
  never an error.

  @feature-config.uc-config-env @scenario-positive @dependency-postgres-18
  Scenario: valid env connects
    Given valid PG_HOST PG_PORT PG_USER PG_PASSWORD env
    When the server loads its configuration
    Then the configuration connects to the postgres database
    And the gate is closed

  @feature-config.uc-config-env @scenario-negative @dependency-none
  Scenario Outline: a malformed env value fails with a fixed config error
    Given env var <name> is "<value>"
    When the server loads its configuration
    Then the load fails mentioning "<error>"

    Examples:
      | name        | value   | error                                          |
      | PG_PORT     | abc     | invalid PG_PORT 'abc': must be 1-65535         |
      | PG_PORT     | 99999   | invalid PG_PORT '99999': must be 1-65535       |
      | PG_HOST     | (empty) | missing required variable: PG_HOST            |
      | PG_USER     | (empty) | missing required variable: PG_USER            |
      | PG_PASSWORD | (empty) | missing required variable: PG_PASSWORD        |
