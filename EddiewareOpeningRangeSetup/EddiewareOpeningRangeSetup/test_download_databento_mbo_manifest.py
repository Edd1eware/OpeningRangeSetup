import tempfile
import unittest
from pathlib import Path

from download_databento_mbo_manifest import output_path, validate_key


class DownloadManifestTests(unittest.TestCase):
    def test_key_validation_and_output_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key_file = root / "key.txt"
            key_file.write_text("db-01234567890123456789012345678\n", encoding="utf-8")
            self.assertTrue(validate_key(key_file).startswith("db-"))
            self.assertEqual(output_path(root, "REQ_1").name, "REQ_1.mbo.dbn.zst")

    def test_placeholder_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            key_file = Path(folder) / "key.txt"
            key_file.write_text("PEGA_AQUI_LA_API_KEY_DE_DATABENTO", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_key(key_file)


if __name__ == "__main__":
    unittest.main()
