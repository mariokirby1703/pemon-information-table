import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import json

spec = importlib.util.spec_from_file_location("sync", Path(__file__).resolve().parents[1] / "scripts/sync_pemons.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    @staticmethod
    def discovery_page(*ids):
        raw = "|".join(f"1:{value}:15:5:17:1:18:10" for value in ids) + "#users#songs#total"
        return Mock(text=raw)

    def test_discovery_allows_overlapping_pages(self):
        responses = [self.discovery_page(1, 2), self.discovery_page(2, 3),
                     self.discovery_page(2, 3), self.discovery_page(3, 4), Mock(text="-1")]
        with patch.object(sync.builder, "_post", side_effect=responses) as post:
            result = sync.discover(True)
        self.assertEqual(set(result), {"1", "2", "3", "4"})
        self.assertEqual(post.call_count, 5)

    def test_discovery_rejects_stuck_pagination(self):
        with patch.object(sync.builder, "_post", return_value=self.discovery_page(1, 2)) as post:
            with self.assertRaisesRegex(RuntimeError, "no progress for three pages"):
                sync.discover(True)
        self.assertEqual(post.call_count, 4)

    def test_newest_first_and_resume_after_new_additions(self):
        batch, next_id = sync.refresh_batch(["1", "2", "3", "4", "5"], {}, 2)
        self.assertEqual(batch, ["5", "4"])
        batch, next_id = sync.refresh_batch(["1", "2", "3", "4", "5", "6"], {"next_level_id": next_id}, 2)
        self.assertEqual(batch, ["3", "2"])
        batch, next_id = sync.refresh_batch(["1", "2", "3", "4", "5", "6"], {"next_level_id": next_id}, 2)
        self.assertEqual((batch, next_id), (["1"], None))
        self.assertEqual(sync.refresh_batch(["1", "2", "3"], {"next_level_id": None}, 2)[0], ["3", "2"])

    def test_watch_mode_skips_rotation_without_advancing_cursor(self):
        ids = ["1", "2", "3"]
        batch, cursor = sync.refresh_batch(ids, {"next_level_id": "2"}, 0)
        self.assertEqual(batch, [])
        self.assertEqual(cursor, "2")

    def test_watch_only_downloads_new_or_changed_levels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output, ids = root / "pemons.json", root / "ids.txt"
            previous = {"ID": 100, "number": 1, "creator": "Author",
                        "level": "Old", "difficulty": "Hard Demon",
                        "rating": "Rated", "rateDate": "01.01.2025"}
            output.write_text(json.dumps([previous]))
            ids.write_text("100\n")
            raw = "1:100:2:Old:15:5:17:1:18:10:43:0:42:0:19:0#users#songs#1:0:10"
            with patch.object(sync.builder, "OUTPUT_FILE", output), \
                 patch.object(sync.builder, "INPUT_FILE", ids), \
                 patch.object(sync, "STATE", root / "state/cursor.json"), \
                 patch.object(sync, "discover", return_value={"100": raw}), \
                 patch.object(sync.builder, "_fetch_download") as download:
                sync.sync(batch_size=0)
                download.assert_not_called()
            self.assertEqual(json.loads(output.read_text()), [previous])

    def test_watch_detects_rating_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output, ids = root / "pemons.json", root / "ids.txt"
            previous = {"ID": 100, "number": 1, "creator": "Author",
                        "level": "Old", "difficulty": "Hard Demon",
                        "rating": "Rated", "rateDate": "01.01.2025"}
            output.write_text(json.dumps([previous]))
            ids.write_text("100\n")
            raw = "1:100:2:Old:15:5:17:1:18:10:43:6:42:2:19:1#users#songs#1:0:10"
            fresh = {"ID": 100, "number": 1, "creator": "Author",
                     "level": "Old", "difficulty": "Extreme Demon",
                     "rating": "Legendary", "rateDate": ""}
            with patch.object(sync.builder, "OUTPUT_FILE", output), \
                 patch.object(sync.builder, "INPUT_FILE", ids), \
                 patch.object(sync, "STATE", root / "state/cursor.json"), \
                 patch.object(sync, "discover", return_value={"100": raw}), \
                 patch.object(sync.builder, "_fetch_download",
                              return_value={"1": "100", "2": "Old", "15": "5",
                                            "17": "1", "18": "10"}), \
                 patch.object(sync.builder, "get_level_data_gd", return_value=fresh):
                sync.sync(batch_size=0)
            saved = json.loads(output.read_text())[0]
            self.assertEqual(saved["difficulty"], "Extreme Demon")
            self.assertEqual(saved["rating"], "Legendary")
            self.assertEqual(saved["rateDate"], "01.01.2025")

    def test_creator_names_from_search_uses_player_ids(self):
        raw = "1:101:6:42#42:RenamedFox:900|43:OtherCreator:901#songs#total"
        self.assertEqual(sync.creator_names_from_search(raw),
                         {"42": "RenamedFox", "43": "OtherCreator"})

    def test_creator_rename_without_download_and_preserve_other_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output, ids = root / "pemons.json", root / "ids.txt"
            previous = {"ID": 100, "number": 1, "creator": "OldFox",
                        "level": "Example", "difficulty": "Hard Demon",
                        "rating": "Rated", "rateDate": "01.01.2025",
                        "checkpoints": 11, "primarySong": "Manual"}
            output.write_text(json.dumps([previous]))
            ids.write_text("100\n")
            raw = ("1:100:2:Example:6:42:15:5:17:1:18:10:43:0:42:0:19:0"
                   "#42:NewFox:900#songs#1:0:10")
            with patch.object(sync.builder, "OUTPUT_FILE", output), \
                 patch.object(sync.builder, "INPUT_FILE", ids), \
                 patch.object(sync, "STATE", root / "state/cursor.json"), \
                 patch.object(sync, "discover", return_value={"100": raw}), \
                 patch.object(sync.builder, "_fetch_download") as download:
                sync.sync(batch_size=0)
                download.assert_not_called()
            self.assertEqual(json.loads(output.read_text()),
                             [{**previous, "creator": "NewFox"}])

    def test_missing_creator_record_does_not_overwrite_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output, ids = root / "pemons.json", root / "ids.txt"
            previous = {"ID": 100, "number": 1, "creator": "KeepMe",
                        "difficulty": "Hard Demon", "rating": "Rated"}
            output.write_text(json.dumps([previous]))
            ids.write_text("100\n")
            raw = "1:100:6:42:15:5:17:1:18:10:43:0:42:0:19:0#43:SomeoneElse:900#songs"
            with patch.object(sync.builder, "OUTPUT_FILE", output), \
                 patch.object(sync.builder, "INPUT_FILE", ids), \
                 patch.object(sync, "STATE", root / "state/cursor.json"), \
                 patch.object(sync, "discover", return_value={"100": raw}), \
                 patch.object(sync.builder, "_fetch_download") as download:
                sync.sync(batch_size=0)
                download.assert_not_called()
            self.assertEqual(json.loads(output.read_text()), [previous])

    def test_request_interval(self):
        self.assertGreaterEqual(sync.builder.MIN_INTERVAL, 5)
        self.assertEqual(sync.builder.WINDOWS, [(10, 2), (60, 12)])

    def test_protected_values_and_updates(self):
        old = {"objects": 100000, "estimatedTime": 100, "songID": "NONG",
               "primarySong": "Manual", "artist": "Artist", "rateDate": "01.01.2024", "checkpoints": 4}
        fresh = {"objects": 65535, "estimatedTime": 90, "songID": 123,
                 "primarySong": "Other", "rateDate": "", "checkpoints": None,
                 "difficulty": "Extreme Demon", "SFX": 0}
        result = sync.builder.merge_entries(old, fresh)
        for key in old:
            self.assertEqual(result[key], old[key])
        self.assertEqual(result["difficulty"], "Extreme Demon")
        self.assertEqual(result["SFX"], 0)
        self.assertEqual(sync.builder.merge_entries(old, {"objects": 120000})["objects"], 120000)

    def test_add_date_and_failed_run_preserves_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output, ids = root / "pemons.json", root / "ids.txt"
            output.write_text("[]")
            ids.write_text("")
            raw = "1:123:2:Example:15:5:17:1:18:10:43:3#users#songs#1:0:10"
            fresh = {"ID": 123, "number": 1, "creator": "Tester", "level": "Example", "rateDate": ""}
            with patch.object(sync.builder, "OUTPUT_FILE", output), patch.object(sync.builder, "INPUT_FILE", ids), \
                 patch.object(sync, "STATE", root / "state/cursor.json"), \
                 patch.object(sync, "discover", return_value={"123": raw}), \
                 patch.object(sync.builder, "_fetch_download", return_value={"1": "123", "2": "Example", "15": "5", "17": "1", "18": "10"}), \
                 patch.object(sync.builder, "get_level_data_gd", return_value=fresh):
                sync.sync()
                saved = json.loads(output.read_text(encoding="utf-8"))
                self.assertRegex(saved[0]["rateDate"], r"^\d{2}\.\d{2}\.\d{4}$")
                before = output.read_bytes(), ids.read_bytes()
                with patch.object(sync.builder, "_fetch_download", return_value={}):
                    with self.assertRaises(RuntimeError):
                        sync.sync()
                self.assertEqual(before, (output.read_bytes(), ids.read_bytes()))



    def test_hyped_search_filters_and_pagination(self):
        raw = ("1:100:15:5:17:1:18:0|1:101:15:5:17:1:18:10|"
               "1:102:15:4:17:1:18:0|1:103:15:5:17:0:18:0"
               "#users#songs#4:0:10")
        with patch.object(sync.builder, "_post", return_value=Mock(text=raw)) as post:
            self.assertEqual(set(sync.discover(full=True, hyped=True)), {"100", "101", "103"})
        params = post.call_args.kwargs["data"]
        self.assertEqual((params["type"], params["diff"], params["len"],
                          params["noStar"], params["hypeSecret"]), ("31", "-2", "5", "1", "1"))
        self.assertNotIn("star", params)

    def test_hyped_failure_does_not_publish(self):
        with patch.object(sync.builder, "_post", return_value=Mock(text="-1")):
            with self.assertRaises(RuntimeError):
                sync.discover(full=True, hyped=True)

    def test_hyped_snapshot_and_promotion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "pemons.json"
            output.write_text("[]")
            raw = "1:100:2:Example:6:42:15:5:17:0:18:10#42:Fox:900#songs#1:0:10"
            kv = {"1": "100", "2": "Example", "15": "5", "17": "0", "18": "0"}
            fresh = {"ID": 100, "number": 1, "creator": "Fox", "level": "Example",
                     "difficulty": "Hard Demon", "rateDate": ""}
            with patch.object(sync.builder, "OUTPUT_FILE", output), \
                 patch.object(sync, "STATE", root / "state/cursor.json"), \
                 patch.object(sync, "discover", return_value={"100": raw}), \
                 patch.object(sync.builder, "_fetch_download", return_value=kv) as download, \
                 patch.object(sync.builder, "get_level_data_gd", return_value=fresh):
                sync.save_unrated(sync.prepare_unrated())
                result = json.loads((root / "unrated-pemons.json").read_text())
                self.assertEqual(result[0]["rating"], "Unrated")
                self.assertEqual(result[0]["difficulty"], "Demon")
                self.assertRegex(result[0]["firstSeen"], r"^\d{2}\.\d{2}\.\d{4}$")
                self.assertEqual((root / "unrated-pemon-ids.txt").read_text(), "100\n")
                sync.save_unrated(sync.prepare_unrated())
                self.assertEqual(download.call_count, 1)
                output.write_text(json.dumps([{"ID": 100}]))
                sync.save_unrated(sync.prepare_unrated())
                self.assertEqual(json.loads((root / "unrated-pemons.json").read_text()), [])
                self.assertEqual((root / "unrated-pemon-ids.txt").read_text(), "")


    def test_hyped_download_rejects_awarded_moons(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "pemons.json"
            output.write_text("[]")
            raw = "1:100:15:5:17:0:18:10#users#songs#1:0:10"
            kv = {"1": "100", "2": "Example", "15": "5", "17": "1", "18": "10"}
            with patch.object(sync.builder, "OUTPUT_FILE", output), \
                 patch.object(sync, "STATE", root / "cursor.json"), \
                 patch.object(sync, "discover", return_value={"100": raw}), \
                 patch.object(sync.builder, "_fetch_download", return_value=kv), \
                 patch.object(sync.builder, "get_level_data_gd") as metadata:
                self.assertEqual(sync.prepare_unrated(), ([], {}))
                metadata.assert_not_called()

    def test_unrated_only_skips_rated_sync(self):
        with patch.object(sync, "prepare_unrated", return_value=([], {})) as prepare, \
             patch.object(sync, "sync") as rated, \
             patch.object(sync, "save_unrated") as save:
            sync.sync_datasets(0, dataset="unrated")
            prepare.assert_called_once_with(full=False)
            rated.assert_not_called()
            save.assert_called_once_with(([], {}))

    def test_rated_only_skips_hyped_sync(self):
        with patch.object(sync, "prepare_unrated") as prepare, \
             patch.object(sync, "sync") as rated, \
             patch.object(sync, "save_unrated") as save:
            sync.sync_datasets(0, dataset="rated")
            rated.assert_called_once_with(0)
            prepare.assert_not_called()
            save.assert_not_called()

    def test_default_sync_runs_both(self):
        with patch.object(sync, "prepare_unrated", return_value=([], {})) as prepare, \
             patch.object(sync, "sync") as rated, \
             patch.object(sync, "save_unrated") as save:
            sync.sync_datasets(0)
            prepare.assert_called_once_with(full=False)
            rated.assert_called_once_with(0)
            save.assert_called_once_with(([], {}))


class DailyRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runner_spec = importlib.util.spec_from_file_location(
            "daily_runner", Path(__file__).resolve().parents[1] / "scripts/run_daily_sync.py"
        )
        cls.runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(cls.runner)

    def test_dataset_arguments_and_file_scope(self):
        runner = self.runner
        self.assertEqual(runner.parse_args([]).dataset, "both")
        self.assertEqual(runner.parse_args(["--force", "--unrated-only"]).dataset, "unrated")
        self.assertEqual(runner.parse_args(["--force", "--rated-only"]).dataset, "rated")
        self.assertEqual(runner.dataset_options("unrated"),
                         (["--unrated-only"], runner.UNRATED_FILES))
        self.assertEqual(runner.dataset_options("rated"),
                         (["--rated-only"], runner.RATED_FILES))
        self.assertEqual(runner.dataset_options("both"), ([], runner.DATA_FILES))
        with self.assertRaises(SystemExit):
            runner.parse_args(["--rated-only", "--unrated-only"])

    def test_success_marker_survives_restarts_and_changes_by_day(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "last-success.json"
            with patch.object(self.runner, "SUCCESS_STATE", path), \
                 patch.object(self.runner, "RUNTIME", Path(folder)):
                self.assertFalse(self.runner.already_synced_today("2026-11-22"))
                self.runner.record_success("2026-11-22")
                self.assertTrue(self.runner.already_synced_today("2026-11-22"))
                self.assertFalse(self.runner.already_synced_today("2026-11-23"))
                self.assertEqual(json.loads(path.read_text()), {"date": "2026-11-22"})

    def test_preflight_does_not_mark_daily_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "last-success.json"
            with patch.object(self.runner, "SUCCESS_STATE", path), \
                 patch.object(self.runner, "RUNTIME", Path(folder)):
                self.assertFalse(self.runner.already_synced_today("2026-11-22"))
                self.assertFalse(path.exists())



if __name__ == "__main__":
    unittest.main()
