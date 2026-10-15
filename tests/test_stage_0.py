"""Unit tests for Stage 0 components using Python standard unittest."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.config import (
    BASE_DIR,
    get_brand_config_path,
    get_brand_db_path,
    get_brand_dir,
    get_brand_templates_dir,
    load_brand_config,
    settings,
)
from core.db import (
    EXPECTED_TABLES,
    get_db_connection,
    get_db_session,
    get_existing_tables,
    init_db,
)
from core.logger import logfire, logger
from core.schemas import BrandConfig, Draft, DraftDiff, ResearchItem, StyleObservation


class TestStage0(unittest.TestCase):
    def test_path_resolution(self):
        tenant = "test_tenant"
        self.assertEqual(get_brand_dir(tenant), BASE_DIR / "brands" / tenant)
        self.assertEqual(
            get_brand_config_path(tenant),
            BASE_DIR / "brands" / tenant / "brand.json",
        )
        self.assertEqual(
            get_brand_db_path(tenant),
            BASE_DIR / "brands" / tenant / "brand.db",
        )
        self.assertEqual(
            get_brand_templates_dir(tenant),
            BASE_DIR / "brands" / tenant / "templates",
        )

    def test_brand_config_schema(self):
        config_data = {
            "tenant_id": "demo",
            "brand_name": "Demo Brand",
            "pillars": ["Pillar 1"],
            "tone": ["Informative"],
            "banned_words": ["bad_word"],
            "reel_default_mode": "talking_head",
            "custom_rules": ["rule 1"],
        }
        cfg = BrandConfig(**config_data)
        self.assertEqual(cfg.tenant_id, "demo")
        self.assertEqual(cfg.reel_default_mode, "talking_head")
        self.assertIn("bad_word", cfg.banned_words)

    def test_v_personal_brand_json_validation(self):
        cfg = load_brand_config("v_personal")
        self.assertEqual(cfg.tenant_id, "v_personal")
        self.assertEqual(cfg.brand_name, "V - Fitness & Tech")
        self.assertIn("Fitness & Training", cfg.pillars)
        self.assertIn("Direct", cfg.tone)
        self.assertIn("game changer", cfg.banned_words)
        self.assertEqual(cfg.reel_default_mode, "faceless")

    def test_db_initialization_and_crud(self):
        test_tenant = "_test_tmp_tenant"
        db_path = get_brand_db_path(test_tenant)

        try:
            init_db(test_tenant)
            self.assertTrue(db_path.exists())

            tables = get_existing_tables(test_tenant)
            self.assertTrue(EXPECTED_TABLES.issubset(tables))

            # Test insert into drafts and foreign key into draft_diffs
            with get_db_session(test_tenant) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO drafts (format, pillar, target_mode, caption)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("reel", "Fitness & Training", "faceless", "Initial test caption"),
                )
                draft_id = cursor.lastrowid
                self.assertIsNotNone(draft_id)

                cursor.execute(
                    """
                    INSERT INTO draft_diffs (draft_id, original_caption, edited_caption, diff_text)
                    VALUES (?, ?, ?, ?)
                    """,
                    (draft_id, "Initial test caption", "Edited caption", "+ Edited"),
                )
                self.assertIsNotNone(cursor.lastrowid)

                cursor.execute(
                    """
                    INSERT INTO research_items (source_type, title, url, raw_text)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("article", "Test Article", "https://example.com/test", "Article body"),
                )
                self.assertIsNotNone(cursor.lastrowid)

                cursor.execute(
                    """
                    INSERT INTO style_observations (observation, count)
                    VALUES (?, ?)
                    """,
                    ("Use short sentences", 2),
                )
                self.assertIsNotNone(cursor.lastrowid)

        finally:
            # Clean up test tenant directory
            brand_dir = get_brand_dir(test_tenant)
            if brand_dir.exists():
                shutil.rmtree(brand_dir, ignore_errors=True)

    def test_logfire_span_execution(self):
        with logfire.span("unit_test_span"):
            logger.info("Inside unit test span")
            self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
