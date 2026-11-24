"""Component binding of the read-path feature scenarios (fake executor, no I/O)."""

from pytest_bdd import scenarios

scenarios("../../features/uc-read-ok.feature")
scenarios("../../features/uc-read-catalog.feature")
scenarios("../../features/uc-read-capped.feature")
scenarios("../../features/uc-read-timeout.feature")
