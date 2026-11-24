Feature: Catalog questions answered with reads only

  Schema questions against information_schema run as plain reads.
  Malformed SQL never reaches the server: the classifier rejects it
  with a parse-error denial.

  @feature-read.uc-read-catalog @scenario-positive @dependency-postgres-18
  Scenario Outline: a catalog read returns catalog rows
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call succeeds
    And the result has at least one row

    Examples:
      | sql                                                                  |
      | SELECT table_name FROM information_schema.tables LIMIT 5              |
      | SELECT column_name FROM information_schema.columns LIMIT 5            |

  @feature-read.uc-read-catalog @scenario-negative @dependency-none
  Scenario: garbage SQL is rejected with a parse error
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "SELECT FROM WHERE ((("}
    Then the call fails mentioning "rejected: could not parse SQL:"
