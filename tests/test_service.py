import os
import threading
import unittest
from unittest.mock import patch

from service import positive_seconds, repeat_task


class PersistentServiceTests(unittest.TestCase):
    def test_positive_seconds_reads_valid_setting(self):
        with patch.dict(os.environ, {"TEST_INTERVAL": "45"}):
            self.assertEqual(positive_seconds("TEST_INTERVAL", 10), 45)

    def test_positive_seconds_rejects_invalid_setting(self):
        with patch.dict(os.environ, {"TEST_INTERVAL": "zero"}):
            with self.assertRaisesRegex(ValueError, "whole number"):
                positive_seconds("TEST_INTERVAL", 10)
        with patch.dict(os.environ, {"TEST_INTERVAL": "0"}):
            with self.assertRaisesRegex(ValueError, "at least 1"):
                positive_seconds("TEST_INTERVAL", 10)

    def test_repeat_task_can_be_stopped_after_one_safe_cycle(self):
        stop = threading.Event()
        calls: list[str] = []

        def task() -> None:
            calls.append("ran")
            stop.set()

        repeat_task("test", task, 60, stop_event=stop)
        self.assertEqual(calls, ["ran"])

    def test_repeat_task_survives_task_failure(self):
        stop = threading.Event()

        def task() -> None:
            stop.set()
            raise RuntimeError("temporary")

        with patch("builtins.print") as output:
            repeat_task("test", task, 60, stop_event=stop)
        self.assertIn("test failed", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
