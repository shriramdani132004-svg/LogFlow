import os
import tempfile
import unittest

from app.log_generator import generate_logs, generate_log_line
from app.config import RANDOM_SEED
from datetime import datetime
import random


class TestLogGenerator(unittest.TestCase):
    def test_generates_requested_record_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.log")
            count, _ = generate_logs(record_count=50, output_file=output_file, seed=1)

            self.assertEqual(count, 50)

            with open(output_file, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
            self.assertEqual(len(lines), 50)

    def test_generated_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=10, output_file=output_file, seed=1)
            self.assertTrue(os.path.exists(output_file))

    def test_log_line_structure(self):
        rng = random.Random(42)
        timestamp = datetime(2026, 9, 20, 10, 15, 32, 123000)
        line = generate_log_line(timestamp, "INFO", "API_REQUEST", "auth", rng)

        parts = [p.strip() for p in line.split("|")]
        self.assertGreaterEqual(len(parts), 4)
        self.assertIn(parts[1], ["DEBUG", "INFO", "WARN", "ERROR"])
        self.assertEqual(parts[2], "API_REQUEST")
        self.assertIn("service=", parts[3])

    def test_deterministic_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "log1.log")
            file2 = os.path.join(tmpdir, "log2.log")

            generate_logs(record_count=20, output_file=file1, seed=42)
            generate_logs(record_count=20, output_file=file2, seed=42)

            with open(file1, "r") as f:
                lines1 = f.readlines()
            with open(file2, "r") as f:
                lines2 = f.readlines()

            self.assertEqual(lines1, lines2)

    def test_different_seeds_produce_different_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "log1.log")
            file2 = os.path.join(tmpdir, "log2.log")

            generate_logs(record_count=20, output_file=file1, seed=1)
            generate_logs(record_count=20, output_file=file2, seed=99)

            with open(file1, "r") as f:
                lines1 = f.readlines()
            with open(file2, "r") as f:
                lines2 = f.readlines()

            self.assertNotEqual(lines1, lines2)

    def test_lines_are_sorted_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=100, output_file=output_file, seed=42)

            with open(output_file, "r") as f:
                lines = [line.strip() for line in f if line.strip()]

            timestamps = [line[:23] for line in lines]
            self.assertEqual(timestamps, sorted(timestamps))

    def test_contains_multiple_log_levels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=500, output_file=output_file, seed=42)

            with open(output_file, "r") as f:
                lines = [line.strip() for line in f if line.strip()]

            levels = set()
            for line in lines:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    levels.add(parts[1])

            self.assertTrue(levels.issubset({"DEBUG", "INFO", "WARN", "ERROR"}))
            self.assertTrue(len(levels) >= 2, "Should contain multiple log levels")


if __name__ == "__main__":
    unittest.main()
