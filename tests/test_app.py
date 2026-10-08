import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import streamlit as st
from streamlit.testing.v1 import AppTest
from scripts.create_demo import create_demo


class TestApplication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.path = create_demo(Path(cls.folder.name) / "demo.db")

    @classmethod
    def tearDownClass(cls):
        st.cache_resource.clear()
        cls.folder.cleanup()

    def setUp(self):
        st.cache_resource.clear()
        self.env = patch.dict(os.environ, {"DATABASE_BACKEND": "sqlite", "SQLITE_DB_PATH": str(self.path),
                                            "OPENAI_API_KEY": "", "CLICKHOUSE_HOST": ""})
        self.env.start()
        # Tests never read a developer's real credentials.
        self.config = patch("agent.get_secret", side_effect=lambda key, default="": os.getenv(key, default))
        self.config.start()

    def tearDown(self):
        self.config.stop()
        self.env.stop()

    def app(self, mode):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        app.sidebar.radio[0].set_value(mode).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_welch_interface_without_openai(self):
        app = self.app("🧪 Hipotez Doğrulama Modu")
        app.selectbox(key="hyp_table").set_value("tweets").run()
        app.selectbox(key="hyp_group_col").set_value("issue").run()
        app.selectbox(key="hyp_metric").set_value("engagement")
        app.checkbox(key="hyp_independent").check()
        app.button(key="hyp_run").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertIn("p_value", app.session_state["statistical_result"])

    def test_forecast_interface_without_openai(self):
        app = self.app("🔮 Tahminleme (Predictive) Modu")
        app.selectbox(key="forecast_table").set_value("tweets").run()
        app.button(key="forecast_run").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertEqual(len(app.session_state["forecast_result"]["forecast"]), 6)

    def test_clickhouse_mode_cannot_use_sqlite(self):
        app = self.app("📊 Veri Analiz Modu (ClickHouse)")
        self.assertEqual(len(app.error), 1)
        self.assertIn("ClickHouse", app.error[0].value)

    def test_missing_sqlite_file_explains_backend_selection(self):
        with patch.dict(os.environ, {"SQLITE_DB_PATH": str(Path(self.folder.name) / "missing.db")}):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertIn("DATABASE_BACKEND", app.error[0].value)
