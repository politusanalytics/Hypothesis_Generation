"""Catch deployment-breaking syntax and configuration merge conflicts offline."""
import ast
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestRepositoryIntegrity(unittest.TestCase):
    def test_python_sources_parse(self):
        sources = list(ROOT.glob("*.py"))
        for directory in ("agents", "scripts", "tests"):
            sources.extend((ROOT / directory).rglob("*.py"))
        for path in sources:
            with self.subTest(file=str(path.relative_to(ROOT))):
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))

    def test_secrets_example_is_valid_toml(self):
        config = tomllib.loads((ROOT / ".streamlit" / "secrets.toml.example").read_text(encoding="utf-8"))
        self.assertEqual(config["CLICKHOUSE_VERIFY"], "true")
        self.assertIn("CLICKHOUSE_TABLES", config)
