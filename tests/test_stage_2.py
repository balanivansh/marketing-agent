"""Unit tests for Stage 2 Ingestion and Rubric-Based Triage components."""

import unittest
from pipeline.ingest import clean_html, extract_feed_urls
from pipeline.triage import TRIAGE_SYSTEM_PROMPT


class TestStage2(unittest.TestCase):
    def test_clean_html(self):
        html_input = "<p>This is a <b>bold</b> test &amp; summary.<br></p>"
        cleaned = clean_html(html_input)
        self.assertEqual(cleaned, "This is a bold test & summary.")

    def test_extract_feed_urls_from_dict_and_list(self):
        # List of dicts
        sources_list = [
            {"name": "Feed 1", "url": "https://example.com/feed1.xml"},
            {"name": "Feed 2", "url": "https://example.com/feed2.xml"},
            "https://example.com/raw.xml",
        ]
        urls = extract_feed_urls(sources_list)
        self.assertEqual(
            urls,
            [
                "https://example.com/feed1.xml",
                "https://example.com/feed2.xml",
                "https://example.com/raw.xml",
            ],
        )

        # Categorized dict
        sources_dict = {
            "tech": ["https://tech.example.com/rss"],
            "fitness": [{"url": "https://fit.example.com/rss"}],
        }
        urls_from_dict = extract_feed_urls(sources_dict)
        self.assertIn("https://tech.example.com/rss", urls_from_dict)
        self.assertIn("https://fit.example.com/rss", urls_from_dict)

    def test_rubric_system_prompt_structure(self):
        """Verify the rubric prompt requires the 3 key criteria and JSON keys."""
        self.assertIn("Audience Alignment", TRIAGE_SYSTEM_PROMPT)
        self.assertIn("Actionability", TRIAGE_SYSTEM_PROMPT)
        self.assertIn("Hook Potential", TRIAGE_SYSTEM_PROMPT)
        self.assertIn("one_line_angle", TRIAGE_SYSTEM_PROMPT)
        self.assertIn("matched_pillar", TRIAGE_SYSTEM_PROMPT)
        self.assertIn("TIMELINESS & EVERGREEN RULE", TRIAGE_SYSTEM_PROMPT)
        self.assertIn("Never include outdated past years", TRIAGE_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
