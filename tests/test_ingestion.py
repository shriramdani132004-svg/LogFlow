import os
import tempfile
import unittest

from app.ingestion import ingest_logs
from app.log_generator import generate_logs


class TestIngestion(unittest.TestCase):
    def test_ingests_generated_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=30, output_file=log_file, seed=42)

            records, stats = ingest_logs(input_file=log_file)

            self.assertEqual(stats["total_lines_read"], 30)
            self.assertEqual(len(records), 30)

    def test_ingestion_count_matches_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=100, output_file=log_file, seed=42)

            records, stats = ingest_logs(input_file=log_file)

            self.assertEqual(stats["total_lines_read"], 100)

    def test_missing_input_file_raises_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "nonexistent.log")
            with self.assertRaises(FileNotFoundError):
                ingest_logs(input_file=fake_path)

    def test_empty_input_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_file = os.path.join(tmpdir, "empty.log")
            with open(empty_file, "w") as f:
                pass

            records, stats = ingest_logs(input_file=empty_file)

            self.assertEqual(stats["total_lines_read"], 0)
            self.assertEqual(len(records), 0)

    def test_preserves_raw_log_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=10, output_file=log_file, seed=42)

            with open(log_file, "r") as f:
                raw_lines = [line.strip() for line in f if line.strip()]

            records, _ = ingest_logs(input_file=log_file)

            self.assertEqual(records, raw_lines)

    def test_skips_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            with open(log_file, "w") as f:
                f.write("line1\n")
                f.write("\n")
                f.write("line2\n")
                f.write("   \n")
                f.write("line3\n")

            records, stats = ingest_logs(input_file=log_file)

            self.assertEqual(len(records), 3)
            self.assertEqual(stats["total_lines_read"], 3)


if __name__ == "__main__":
    unittest.main()
