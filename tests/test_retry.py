"""Retry classification tests."""

import unittest

from mbtk.errors import RemoteServiceError
from mbtk.retry import is_permanent, is_permanent_max, is_transient


class RetryTests(unittest.TestCase):
    def test_transient_statuses(self):
        for status in (None, 408, 429, 500, 503):
            error = RemoteServiceError("x", status, service="MAX")
            self.assertTrue(is_transient(error), status)

    def test_max_401_is_transient(self):
        self.assertTrue(
            is_transient(RemoteServiceError("x", 401, service="MAX"))
        )

    def test_bakery_401_is_not_permanent(self):
        error = RemoteServiceError("x", 401, service="Bakery")
        self.assertFalse(is_transient(error))
        self.assertFalse(is_permanent(error))

    def test_permanent_client_errors(self):
        for status in (400, 403, 404, 409):
            error = RemoteServiceError("x", status, service="MAX")
            self.assertTrue(is_permanent(error), status)

    def test_non_remote_error_is_not_permanent(self):
        self.assertFalse(is_permanent(RuntimeError("x")))

    def test_is_permanent_max_checks_service(self):
        self.assertTrue(
            is_permanent_max(RemoteServiceError("x", 403, service="MAX"))
        )
        self.assertFalse(
            is_permanent_max(RemoteServiceError("x", 403, service="Bakery"))
        )


if __name__ == "__main__":
    unittest.main()
