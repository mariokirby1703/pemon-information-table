import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

spec = importlib.util.spec_from_file_location("sync", Path(__file__).resolve().parents[1] / "scripts/sync_pemons.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
