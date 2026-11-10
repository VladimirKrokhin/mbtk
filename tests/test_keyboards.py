"""Unit tests for MAX keyboard and attachment builders."""

import json
import unittest

from mbtk.max.keyboards import button, keyboard, location_attachment


class KeyboardTests(unittest.TestCase):
    def test_button_serializes_payload_with_unicode(self):
        item = button("Меню", {"a": "menu", "n": "Сегодня"})

        self.assertEqual(item["type"], "callback")
        self.assertEqual(item["text"], "Меню")
        self.assertEqual(
            json.loads(item["payload"]), {"a": "menu", "n": "Сегодня"}
        )
        self.assertNotIn("\\u", item["payload"])

    def test_keyboard_limits_rows(self):
        rows = [[button("x", {})] for _ in range(35)]

        board = keyboard(rows)

        self.assertEqual(board["type"], "inline_keyboard")
        self.assertEqual(len(board["payload"]["buttons"]), 30)

    def test_custom_keyboard_limit(self):
        rows = [[button("x", {})] for _ in range(3)]

        self.assertEqual(len(keyboard(rows, limit=2)["payload"]["buttons"]), 2)

    def test_location_attachment(self):
        attachment = location_attachment(55.75, 37.61)

        self.assertEqual(
            attachment,
            {"type": "location", "latitude": 55.75, "longitude": 37.61},
        )


if __name__ == "__main__":
    unittest.main()
