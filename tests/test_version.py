"""Package version stays in sync with the installed distribution."""

import importlib.metadata
import unittest

import mbtk


class VersionTests(unittest.TestCase):
    def test_version_matches_distribution(self):
        self.assertEqual(mbtk.__version__, importlib.metadata.version("mbtk"))


if __name__ == "__main__":
    unittest.main()
