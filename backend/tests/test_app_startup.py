import unittest
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class AppStartupTest(unittest.TestCase):
    def test_fastapi_app_can_be_imported(self) -> None:
        from app.main import app

        self.assertEqual(app.title, "CodeMind API")
