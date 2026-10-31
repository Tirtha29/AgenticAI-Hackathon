import unittest

from backend.worker import DEAD_LETTER_STREAM, process_entry


class FakeRedis:
    def __init__(self):
        self.acknowledged = []
        self.deleted_attempts = []
        self.dead_letters = []
        self.attempts = 0
        self.incremented_keys = []

    async def xack(self, stream, group, message_id):
        self.acknowledged.append((stream, group, message_id))

    async def hdel(self, key, message_id):
        self.deleted_attempts.append((key, message_id))

    async def hincrby(self, key, field, value):
        self.incremented_keys.append((key, field, value))
        self.attempts += value
        return self.attempts

    async def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))


class SuccessfulResponse:
    def raise_for_status(self):
        return None


class SuccessfulClient:
    def __init__(self):
        self.calls = []

    async def post(self, *_args, **_kwargs):
        self.calls.append((_args, _kwargs))
        return SuccessfulResponse()


class FailedClient:
    def __init__(self):
        self.calls = []

    async def post(self, *_args, **_kwargs):
        self.calls.append((_args, _kwargs))
        raise ValueError("invalid backend response")


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_acknowledges_stream_entry(self):
        redis = FakeRedis()
        await process_entry(
            redis,
            SuccessfulClient(),
            "1-0",
            {"payload": '{"event_id":"evt-1","device_id":"RTR1","metrics":{}}'},
        )
        self.assertEqual(redis.acknowledged, [("netcoop:telemetry", "netcoop-workers", "1-0")])
        self.assertEqual(redis.deleted_attempts, [("netcoop:telemetry:attempts", "1-0")])

    async def test_max_delivery_count_moves_entry_to_dead_letter(self):
        redis = FakeRedis()
        redis.attempts = 4
        await process_entry(
            redis,
            FailedClient(),
            "1-1",
            {"payload": '{"event_id":"evt-2","device_id":"RTR1","metrics":{}}'},
        )
        self.assertEqual(redis.dead_letters[0][0], DEAD_LETTER_STREAM)
        self.assertEqual(redis.acknowledged, [("netcoop:telemetry", "netcoop-workers", "1-1")])
        self.assertEqual(redis.deleted_attempts, [("netcoop:telemetry:attempts", "1-1")])


if __name__ == "__main__":
    unittest.main()
