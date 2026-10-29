import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock


ROOT = Path(__file__).parent


def load_main(name, path, dependencies):
    previous = {dependency: sys.modules.get(dependency) for dependency in dependencies}
    sys.modules.update(dependencies)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for dependency, original in previous.items():
            if original is None:
                sys.modules.pop(dependency, None)
            else:
                sys.modules[dependency] = original


def stub():
    return ModuleType("stub")


class ScoreRefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mlb_api = stub()
        cls.mlb_store = stub()
        cls.mlb = load_main(
            "mlb_main_test",
            ROOT / "src" / "main.py",
            {
                "mlb": cls.mlb_api,
                "player_summary": stub(),
                "comparison": stub(),
                "json_store": cls.mlb_store,
            },
        )

        cls.nba_api = stub()
        cls.cbb_api = stub()
        cls.nba_store = stub()
        cls.nba = load_main(
            "nba_main_test",
            ROOT / "nba" / "nba_main.py",
            {
                "espn_nba": cls.nba_api,
                "espn_cbb": cls.cbb_api,
                "nba_dates": stub(),
                "nba_player_summary": stub(),
                "nba_json_store": cls.nba_store,
            },
        )

        cls.nfl_api = stub()
        cls.cfb_api = stub()
        cls.nfl_store = stub()
        cls.nfl = load_main(
            "nfl_main_test",
            ROOT / "nfl" / "nfl_main.py",
            {
                "espn_nfl": cls.nfl_api,
                "espn_cfb": cls.cfb_api,
                "nfl_dates": stub(),
                "nfl_player_summary": stub(),
                "nfl_json_store": cls.nfl_store,
            },
        )

    def setUp(self):
        for dependency in (
            self.mlb_api,
            self.mlb_store,
            self.nba_api,
            self.cbb_api,
            self.nba_store,
            self.nfl_api,
            self.cfb_api,
            self.nfl_store,
        ):
            dependency.__dict__.pop("fetch_games_by_date", None)
            dependency.__dict__.pop("save_watched", None)

    def test_mlb_refreshes_by_date_and_accepts_zero(self):
        watched = {
            "10": {"game_id": "10", "date": "2026-04-01", "away_score": "", "home_score": ""},
            "11": {"game_id": 11, "date": "2026-04-01", "away_score": None, "home_score": None},
            "12": {"game_id": 12, "date": "2026-04-02", "away_score": "3", "home_score": "2"},
        }
        self.mlb_api.fetch_games_by_date = Mock(return_value=[
            {"game_id": 10, "away_score": 0, "home_score": 2},
            {"game_id": "11", "away_score": "", "home_score": 4},
        ])
        self.mlb_store.save_watched = Mock()

        updated = self.mlb._refresh_missing_scores(watched)

        self.assertEqual(updated, 1)
        self.assertEqual((watched["10"]["away_score"], watched["10"]["home_score"]), (0, 2))
        self.assertIsNone(watched["11"]["away_score"])
        self.mlb_api.fetch_games_by_date.assert_called_once_with("2026-04-01")
        self.mlb_store.save_watched.assert_called_once_with(watched)

    def test_basketball_routes_each_league_and_saves_once(self):
        watched = {
            "1": {"game_id": "1", "date": "2026-10-21", "away_score": "", "home_score": ""},
            "2": {"game_id": "2", "date": "2026-10-21", "league": "college", "away_score": "", "home_score": ""},
        }
        self.nba_api.fetch_games_by_date = Mock(return_value=[
            {"game_id": 1, "away_score": "101", "home_score": "99"},
        ])
        self.cbb_api.fetch_games_by_date = Mock(return_value=[
            {"game_id": 2, "away_score": "70", "home_score": "65"},
        ])
        self.nba_store.save_watched = Mock()

        updated = self.nba._refresh_missing_scores(watched)

        self.assertEqual(updated, 2)
        self.nba_api.fetch_games_by_date.assert_called_once_with("2026-10-21")
        self.cbb_api.fetch_games_by_date.assert_called_once_with("2026-10-21")
        self.nba_store.save_watched.assert_called_once_with(watched)

    def test_football_continues_after_api_failure(self):
        watched = {
            "1": {"game_id": "1", "date": "2026-09-01", "away_score": "", "home_score": ""},
            "2": {"game_id": "2", "date": "2026-09-02", "league": "college", "away_score": "", "home_score": ""},
        }
        self.nfl_api.fetch_games_by_date = Mock(side_effect=RuntimeError("offline"))
        self.cfb_api.fetch_games_by_date = Mock(return_value=[
            {"game_id": 2, "away_score": "21", "home_score": "17"},
        ])
        self.nfl_store.save_watched = Mock()

        updated = self.nfl._refresh_missing_scores(watched)

        self.assertEqual(updated, 1)
        self.assertEqual(watched["1"]["away_score"], "")
        self.assertEqual(watched["2"]["home_score"], "17")
        self.nfl_store.save_watched.assert_called_once_with(watched)

    def test_no_missing_scores_skips_fetch_and_save(self):
        cases = (
            (self.mlb, self.mlb_api, self.mlb_store),
            (self.nba, self.nba_api, self.nba_store),
            (self.nfl, self.nfl_api, self.nfl_store),
        )
        watched = {"1": {"game_id": "1", "date": "2026-01-01", "away_score": 0, "home_score": 1}}
        for module, api, store in cases:
            with self.subTest(module=module.__name__):
                api.fetch_games_by_date = Mock()
                store.save_watched = Mock()
                self.assertEqual(module._refresh_missing_scores(watched), 0)
                api.fetch_games_by_date.assert_not_called()
                store.save_watched.assert_not_called()


if __name__ == "__main__":
    unittest.main()
