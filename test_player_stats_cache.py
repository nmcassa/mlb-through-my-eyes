import tempfile
import unittest
from pathlib import Path

from player_stats_cache import PlayerStatsCache


class PlayerStatsCacheTest(unittest.TestCase):
    def test_persists_entries_between_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.jsonl"
            PlayerStatsCache(path, 1).put("nba:1", [{"pts": 20}])

            self.assertEqual(PlayerStatsCache(path, 1).get("nba:1"), [{"pts": 20}])

    def test_ignores_entries_from_another_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.jsonl"
            PlayerStatsCache(path, 1).put("mlb:1", {"hits": 2})

            self.assertIsNone(PlayerStatsCache(path, 2).get("mlb:1"))

    def test_skips_a_truncated_final_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.jsonl"
            PlayerStatsCache(path, 1).put("nfl:1", {"yards": 300})
            with path.open("a", encoding="utf-8") as cache_file:
                cache_file.write('{"schema":1')

            self.assertEqual(PlayerStatsCache(path, 1).get("nfl:1"), {"yards": 300})


if __name__ == "__main__":
    unittest.main()
