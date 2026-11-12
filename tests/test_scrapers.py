import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webscrape"))
import scraper
import wayback_scraper


class ScraperTests(unittest.TestCase):
    def test_later_page_is_processed_after_failed_page(self):
        client = Mock()
        client.get.side_effect = ["page 1", None, "page 3"]
        listing = {"id": "id", "vehicle": {"make": "BMW"}}
        with patch.object(scraper, "parse_page", side_effect=[([listing], 3, 3), ([listing], 3, 3)]), \
             patch.object(scraper, "parse_listing", return_value={"price_eur": 5000}):
            rows = {}
            complete = scraper.scrape_body_type(client, "BMW", "bmw", 2020, "1", "sedan", rows, {})
        self.assertFalse(complete)
        self.assertEqual(client.get.call_count, 3)
        self.assertEqual(rows, {"id": {"price_eur": 5000}})

    def test_incomplete_combination_is_not_marked_done(self):
        storage = Mock(done=set(), seen_ids=set())
        with patch.object(sys, "argv", ["scraper.py", "--brand", "BMW", "--year", "2020"]), \
             patch.object(scraper, "Storage", return_value=storage), \
             patch.object(scraper, "Client"), \
             patch.object(scraper, "scrape_brand_year", return_value=(1, False)), \
             patch.object(scraper, "estimate") as estimate:
            scraper.main()
        storage.mark_done.assert_not_called()
        estimate.assert_not_called()

    def test_failed_snapshot_remains_pending(self):
        storage = Mock(done=set())
        client = Mock()
        client.get.return_value = None
        with patch.object(wayback_scraper, "monthly_snapshots", return_value={"202301": ["20230115120000"]}), \
             patch.object(wayback_scraper, "read_lines", return_value=set()):
            self.assertEqual(wayback_scraper.scrape_model(client, storage, "BMW", "320", False), 0)
        storage.mark_done.assert_not_called()
        storage.save.assert_not_called()
