"""Component binding of the write-gate feature scenarios (fake executor, no I/O)."""

from pytest_bdd import scenarios

scenarios("../../features/uc-write-denied-default.feature")
scenarios("../../features/uc-write-smuggled.feature")
scenarios("../../features/uc-dangerous-function.feature")
scenarios("../../features/uc-write-allowed-when-open.feature")
scenarios("../../features/uc-single-statement.feature")
