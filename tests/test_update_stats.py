import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from update_stats import STAT_KEYS, build_stats, calculate_streaks, update_files  # noqa: E402


class UpdateStatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = ROOT / "tests" / "fixtures" / "api-response.json"
        cls.fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_builds_complete_metrics_and_dynamic_streaks(self):
        stats = build_stats(self.fixture)
        self.assertEqual(
            stats,
            {
                "commits": "120",
                "prs": "14",
                "issues": "6",
                "repos": "17",
                "overall": "250",
                "current_streak": "2 days",
                "longest_streak": "2 days",
            },
        )

    def test_two_zero_days_end_current_streak(self):
        days = [
            {"date": "2025-01-01", "contributionCount": 1},
            {"date": "2025-01-02", "contributionCount": 0},
            {"date": "2025-01-03", "contributionCount": 0},
        ]
        self.assertEqual(calculate_streaks(days), (0, 1))

    def test_updates_both_files_and_then_becomes_noop(self):
        stats = build_stats(self.fixture)
        markers = "\n".join(
            f"<!--stat:{key}-->stale<!--/stat:{key}-->" for key in STAT_KEYS
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs").mkdir()
            (root / "README.md").write_text(
                markers + "\n<!--updated: old-->\n", encoding="utf-8"
            )
            (root / "docs" / "index.html").write_text(markers, encoding="utf-8")

            self.assertTrue(update_files(root, stats, "2025-01-01T00:00:00Z"))
            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("<!--stat:commits-->120<!--/stat:commits-->", readme)
            self.assertIn("<!--updated: 2025-01-01T00:00:00Z-->", readme)

            self.assertFalse(update_files(root, stats, "2025-01-02T00:00:00Z"))
            self.assertEqual(
                readme, (root / "README.md").read_text(encoding="utf-8")
            )


if __name__ == "__main__":
    unittest.main()
