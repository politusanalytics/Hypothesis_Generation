import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
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
        self.secrets = patch("streamlit.secrets", {"DATABASE_BACKEND": "sqlite", "SQLITE_DB_PATH": str(self.path),
                                                   "OPENAI_API_KEY": "", "CLICKHOUSE_HOST": ""})
        self.secrets.start()
        self.env = patch.dict(os.environ, {"DATABASE_BACKEND": "sqlite", "SQLITE_DB_PATH": str(self.path),
                                            "OPENAI_API_KEY": "", "CLICKHOUSE_HOST": ""})
        self.env.start()
        # Tests never read a developer's real credentials.
        self.config = patch("agent.get_secret", side_effect=lambda key, default="": os.getenv(key, default))
        self.config.start()

    def tearDown(self):
        self.config.stop()
        self.env.stop()
        self.secrets.stop()

    def app(self, mode):
        app = self.new_app().run()
        self.assertEqual(len(app.exception), 0)
        app.sidebar.radio[0].set_value(mode).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def new_app(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
        app.secrets.update({"DATABASE_BACKEND": "sqlite", "SQLITE_DB_PATH": os.getenv("SQLITE_DB_PATH"),
                            "OPENAI_API_KEY": "", "CLICKHOUSE_HOST": ""})
        return app

    def test_people_comparison_without_openai(self):
        app = self.app("🧪 Hipotez Doğrulama Modu")
        self.assertNotIn("Tablo", [element.label for element in app.selectbox])
        app.checkbox(key="hyp_independent").check()
        app.button(key="hyp_run").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertIn("p_value", app.session_state["statistical_result"])

    def test_forecast_interface_without_openai(self):
        app = self.app("🔮 Tahminleme (Predictive) Modu")
        self.assertNotIn("Tarih sütunu", [element.label for element in app.selectbox])
        app.button(key="forecast_run").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertEqual(len(app.session_state["forecast_result"]["forecast"]), 6)
        if not app.session_state["forecast_result"]["beats_naive"]:
            self.assertEqual(len(app.get("plotly_chart")), 0)
            app.checkbox(key="forecast_weak").check().run()
            self.assertEqual(len(app.get("plotly_chart")), 1)

    def test_autonomous_summary_is_simple_and_survives_rerun(self):
        app = self.app("🤖 Otonom İçgörü Modu")
        app.button(key="overview_run").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertEqual(len(app.success), 1)
        self.assertNotIn("SQL", app.success[0].value)
        self.assertEqual(len(app.get("plotly_chart")), 0)
        app.run()
        self.assertEqual(len(app.success), 1)

    def test_manual_age_emotions_do_not_invent_products(self):
        app = self.app("👤 Manuel Soru Modu")
        app.chat_input[0].set_value("Yaş gruplarının baskın duyguları neler?").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        history = app.session_state["friendly_chat"]
        self.assertEqual(len(history), 1)
        self.assertNotIn("Kahve", history[0]["result"]["summary"])
        self.assertFalse(app.checkbox(key="chat_follow").value)

    def test_clickhouse_mode_cannot_use_sqlite(self):
        app = self.app("📊 Veri Analiz Modu (ClickHouse)")
        self.assertEqual(len(app.error), 1)
        self.assertIn("ClickHouse", app.error[0].value)

    def test_explore_presets_charts_and_custom_answer_have_no_nested_expanders(self):
        from database import SQLiteDatabase
        from marketing_data import marketing_database
        from agents.query_agent import QueryAgent
        db = marketing_database(SQLiteDatabase(self.path))
        planner = QueryAgent(db=db, catalog=db.catalog, dialect="sqlite")
        # Only the UI is isolated with this fixture; the real factory's
        # ClickHouse-only requirement is covered separately above.
        with patch("data_analysis.get_analysis_engine", return_value=SimpleNamespace(planner=planner)):
            app = self.app("📊 Veri Analiz Modu (ClickHouse)")
            app.button(key="explore_run").click().run()
            self.assertEqual(len(app.error), 0)
            self.assertIn("Başlık", app.dataframe[0].value.columns)
            app.checkbox(key="explore_chart").check().run()
            self.assertEqual(len(app.get("plotly_chart")), 1)
            app.text_area[0].set_value("Yaş gruplarının baskın duyguları neler?")
            next(b for b in app.button if b.label == "Soruyu yanıtla").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn("distribution", app.session_state["explore_answer"])

    def test_missing_sqlite_file_explains_backend_selection(self):
        with patch.dict(os.environ, {"SQLITE_DB_PATH": str(Path(self.folder.name) / "missing.db")}):
            app = self.new_app().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertIn("DATABASE_BACKEND", app.error[0].value)
