Feature: Dangerous functions are denied anywhere in the tree

  Every FuncCall anywhere in the parsed tree — including inside
  RangeFunction entries (fromClause functions) and targetList values —
  is lowercased and compared by unqualified and pg_catalog-qualified
  name against DENIED_FUNCTIONS.

  @feature-gate.uc-dangerous-function @scenario-positive @dependency-none
  Scenario Outline: a dangerous function in the select list is denied
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: function <name> is not allowed while PG_ALLOW_WRITES is closed"

    Examples:
      | sql                                            | name               |
      | SELECT set_config('a', 'b', false)             | set_config         |
      | SELECT pg_read_file('pg_hba.conf')             | pg_read_file       |
      | SELECT pg_ls_dir('.')                          | pg_ls_dir          |
      | SELECT lo_creat(-1)                            | lo_creat           |
      | SELECT nextval('s_seq')                        | nextval            |

  @feature-gate.uc-dangerous-function @scenario-negative @dependency-none
  Scenario Outline: a dangerous function hidden in FROM or qualified is denied
    Given the gate is closed
    When the agent calls "execute_sql" with {"sql": "<sql>"}
    Then the call fails mentioning "rejected: function <name> is not allowed while PG_ALLOW_WRITES is closed"

    Examples:
      | sql                                              | name                |
      | SELECT pg_sleep(0.1)                             | pg_sleep            |
      | SELECT * FROM pg_sleep(0.1)                      | pg_sleep            |
      | SELECT * FROM pg_catalog.pg_read_file('x')      | pg_read_file        |
      | SELECT pg_terminate_backend(1)                   | pg_terminate_backend |
      | SELECT PG_SLEEP(0.1)                             | pg_sleep            |
