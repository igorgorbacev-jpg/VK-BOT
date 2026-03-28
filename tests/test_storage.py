import json
import os
import tempfile
import unittest
import unittest.mock

import storage
from storage import _load_json, _save_json, add_to_blacklist, add_to_favorites

SAMPLE_CANDIDATE = {
    "id": 123456,
    "first_name": "Иван",
    "last_name": "Иванов",
    "profile_url": "https://vk.com/id123456",
    "photos": ["photo123_456", "photo123_789"],
}


class TestAddToFavorites(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._orig_favorites = storage.FAVORITES_FILE
        self._orig_blacklist = storage.BLACKLIST_FILE
        storage.FAVORITES_FILE = os.path.join(self.tmp_dir, "favorites.json")
        storage.BLACKLIST_FILE = os.path.join(self.tmp_dir, "blacklist.json")

    def tearDown(self):
        storage.FAVORITES_FILE = self._orig_favorites
        storage.BLACKLIST_FILE = self._orig_blacklist
        # Clean up temp files
        for fname in ["favorites.json", "blacklist.json"]:
            path = os.path.join(self.tmp_dir, fname)
            if os.path.exists(path):
                os.remove(path)
        os.rmdir(self.tmp_dir)

    def test_add_new(self):
        """add_to_favorites with a new candidate returns 'added' and writes 1 entry."""
        result = add_to_favorites(111, SAMPLE_CANDIDATE)
        self.assertEqual(result, "added")
        with open(storage.FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_duplicate(self):
        """Adding same candidate twice: second call returns 'duplicate', file has 1 entry."""
        add_to_favorites(111, SAMPLE_CANDIDATE)
        result = add_to_favorites(111, SAMPLE_CANDIDATE)
        self.assertEqual(result, "duplicate")
        with open(storage.FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_entry_schema(self):
        """Entry has all 7 required fields: owner_id, id, first_name, last_name, profile_url, photos, added_at."""
        add_to_favorites(111, SAMPLE_CANDIDATE)
        with open(storage.FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        entry = data[0]
        for key in (
            "owner_id",
            "id",
            "first_name",
            "last_name",
            "profile_url",
            "photos",
            "added_at",
        ):
            self.assertIn(key, entry, f"Missing key: {key}")
        self.assertEqual(entry["owner_id"], 111)
        self.assertEqual(entry["id"], SAMPLE_CANDIDATE["id"])

    def test_cyrillic_names(self):
        """Cyrillic names are stored as readable UTF-8, not escaped unicode sequences."""
        add_to_favorites(111, SAMPLE_CANDIDATE)
        with open(storage.FAVORITES_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
        # If ensure_ascii=True, Cyrillic would appear as \uXXXX
        self.assertIn(
            "Иван", raw, "Cyrillic first_name must be readable, not escaped"
        )
        self.assertIn(
            "Иванов", raw, "Cyrillic last_name must be readable, not escaped"
        )
        self.assertNotIn(
            "\\u0418", raw, "No escaped Cyrillic characters expected"
        )


class TestAddToBlacklist(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._orig_favorites = storage.FAVORITES_FILE
        self._orig_blacklist = storage.BLACKLIST_FILE
        storage.FAVORITES_FILE = os.path.join(self.tmp_dir, "favorites.json")
        storage.BLACKLIST_FILE = os.path.join(self.tmp_dir, "blacklist.json")

    def tearDown(self):
        storage.FAVORITES_FILE = self._orig_favorites
        storage.BLACKLIST_FILE = self._orig_blacklist
        for fname in ["favorites.json", "blacklist.json"]:
            path = os.path.join(self.tmp_dir, fname)
            if os.path.exists(path):
                os.remove(path)
        os.rmdir(self.tmp_dir)

    def test_add_new(self):
        """add_to_blacklist with a new candidate returns 'added' and writes 1 entry."""
        result = add_to_blacklist(111, SAMPLE_CANDIDATE)
        self.assertEqual(result, "added")
        with open(storage.BLACKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_duplicate(self):
        """Adding same candidate twice to blacklist: second returns 'duplicate', file has 1 entry."""
        add_to_blacklist(111, SAMPLE_CANDIDATE)
        result = add_to_blacklist(111, SAMPLE_CANDIDATE)
        self.assertEqual(result, "duplicate")
        with open(storage.BLACKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)


class TestLoadJson(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_missing_file(self):
        """_load_json on a nonexistent file returns [] without crashing."""
        path = os.path.join(self.tmp_dir, "nonexistent.json")
        result = _load_json(path)
        self.assertEqual(result, [])

    def test_existing_file(self):
        """_load_json on an existing file returns parsed list."""
        data = [{"id": 1, "name": "test"}]
        path = os.path.join(self.tmp_dir, "existing.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = _load_json(path)
        self.assertEqual(result, data)


class TestSaveJsonAtomic(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._orig_favorites = storage.FAVORITES_FILE
        self._orig_blacklist = storage.BLACKLIST_FILE
        storage.FAVORITES_FILE = os.path.join(self.tmp_dir, "favorites.json")
        storage.BLACKLIST_FILE = os.path.join(self.tmp_dir, "blacklist.json")

    def tearDown(self):
        import shutil

        storage.FAVORITES_FILE = self._orig_favorites
        storage.BLACKLIST_FILE = self._orig_blacklist
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_atomic_write_creates_file(self):
        """_save_json creates a valid JSON file at the given path."""
        path = os.path.join(self.tmp_dir, "test.json")
        _save_json(path, [{"id": 1}])
        with open(path, "r", encoding="utf-8") as f:
            result = json.load(f)
        self.assertEqual(result, [{"id": 1}])

    def test_atomic_write_no_tmp_leftover(self):
        """After _save_json completes, no {path}.tmp file remains on disk."""
        path = os.path.join(self.tmp_dir, "test.json")
        _save_json(path, [{"id": 1}])
        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_atomic_write_uses_os_replace(self):
        """_save_json calls os.replace(path + '.tmp', path) for atomic write."""
        with unittest.mock.patch(
            "storage.os.replace"
        ) as mock_os_replace, unittest.mock.patch(
            "builtins.open", unittest.mock.mock_open()
        ):
            _save_json("test.json", [])
        self.assertTrue(mock_os_replace.called)
        mock_os_replace.assert_called_with("test.json.tmp", "test.json")


if __name__ == "__main__":
    unittest.main()
