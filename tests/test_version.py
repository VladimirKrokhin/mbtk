"""Package version stays in sync with the installed distribution."""

import importlib.metadata
import unittest

import mbtk


class VersionTests(unittest.TestCase):
    def test_version_matches_distribution(self):
        self.assertEqual(mbtk.__version__, importlib.metadata.version("mbtk"))

    def test_version_is_bumped_for_this_release(self):
        self.assertEqual(mbtk.__version__, "0.1.1")


if __name__ == "__main__":
    unittest.main()
