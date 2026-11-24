"""Component binding of the role feature scenarios (fake executor, no I/O)."""

from pytest_bdd import scenarios

scenarios("../../features/uc-role-readonly.feature")
scenarios("../../features/uc-role-grant-revoke.feature")
