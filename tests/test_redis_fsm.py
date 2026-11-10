"""Redis FSM storage: state, data, and atomic claims."""

import json
import unittest

from mbtk.storage.redis import RedisFSMStorage


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None, keepttl=False):
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex

    def delete(self, key):
        self.ttls.pop(key, None)
        return self.values.pop(key, None) is not None

    def eval(self, script, key_count, key, *args):
        if script == RedisFSMStorage.FSM_CLAIM_SCRIPT:
            raw = self.values.get(key)
            if not raw:
                return False
            record = json.loads(raw)
            if not record.get("state"):
                return False
            if record.get("claim"):
                return record["claim"] == args[0]
            record["claim"] = args[0]
            self.values[key] = json.dumps(record)
            return True
        if script == RedisFSMStorage.FSM_COMPLETE_SCRIPT:
            raw = self.values.get(key)
            if not raw:
                return False
            record = json.loads(raw)
            if record.get("claim") != args[0]:
                return False
            return self.delete(key)
        raise AssertionError("unexpected script")


class RedisFSMTests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.store = RedisFSMStorage(self.redis)

    def test_state_is_stored_per_chat_and_user_with_ttl(self):
        self.store.set_state(("10", "20"), "waiting_photo", ttl=600)

        key = "maxbot:fsm:10:20"
        self.assertEqual(
            json.loads(self.redis.values[key])["state"], "waiting_photo"
        )
        self.assertEqual(self.redis.ttls[key], 600)
        self.assertEqual(self.store.get_state(("10", "20")), "waiting_photo")
        self.assertIsNone(self.store.get_state(("10", "21")))

    def test_data_survives_state_change_and_can_be_updated(self):
        self.store.set_state(("10", "20"), "waiting_photo", ttl=600)
        self.store.update_data(("10", "20"), {"a": 1})
        self.store.update_data(("10", "20"), {"b": 2})

        self.assertEqual(self.store.get_data(("10", "20")), {"a": 1, "b": 2})
        self.assertEqual(self.store.get_state(("10", "20")), "waiting_photo")

        self.store.clear_state(("10", "20"))
        self.assertIsNone(self.store.get_state(("10", "20")))
        self.assertEqual(self.store.get_data(("10", "20")), {"a": 1, "b": 2})

    def test_claim_is_retryable_but_exclusive_to_one_event(self):
        self.assertFalse(self.store.claim(("10", "20"), "mid-1"))

        self.store.set_state(("10", "20"), "waiting_photo", ttl=600)

        self.assertTrue(self.store.claim(("10", "20"), "mid-1"))
        self.assertTrue(self.store.claim(("10", "20"), "mid-1"))
        self.assertFalse(self.store.claim(("10", "20"), "mid-2"))
        self.assertFalse(self.store.complete_claim(("10", "20"), "mid-2"))
        self.assertTrue(self.store.complete_claim(("10", "20"), "mid-1"))
        self.assertIsNone(self.store.get_state(("10", "20")))

    def test_corrupted_record_is_treated_as_empty(self):
        self.redis.values["maxbot:fsm:10:20"] = "not-json"

        self.assertIsNone(self.store.get_state(("10", "20")))
        self.assertEqual(self.store.get_data(("10", "20")), {})

    def test_clear_removes_record(self):
        self.store.set_state(("10", "20"), "waiting_photo")

        self.assertTrue(self.store.clear(("10", "20")))
        self.assertNotIn("maxbot:fsm:10:20", self.redis.values)

    def test_custom_prefix_and_default_ttl(self):
        store = RedisFSMStorage(self.redis, prefix="app:state:", ttl=60)
        store.set_state(("1", "2"), "waiting")

        self.assertIn("app:state:1:2", self.redis.values)
        self.assertEqual(self.redis.ttls["app:state:1:2"], 60)


if __name__ == "__main__":
    unittest.main()
