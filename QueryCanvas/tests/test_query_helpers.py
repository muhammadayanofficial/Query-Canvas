import tempfile
import unittest
from pathlib import Path

import app as app_module


class QueryCanvasTests(unittest.TestCase):
    def test_column_names_become_safe_and_unique(self):
        names = app_module.normalize_column_names(["Order ID", "Order-ID", "", "3rd value", "A/B"])
        self.assertEqual(names, ["order_id", "order_id_2", "column_3", "col_3rd_value", "a_b"])
        self.assertEqual(len(names), len(set(names)))

    def test_parse_scalar(self):
        self.assertEqual(app_module.parse_scalar("17"), 17)
        self.assertEqual(app_module.parse_scalar("3.25"), 3.25)
        self.assertIsNone(app_module.parse_scalar("  "))
        self.assertEqual(app_module.parse_scalar("0081"), 81)
        self.assertEqual(app_module.parse_scalar("North"), "North")

    def test_only_select_or_with_is_accepted(self):
        self.assertTrue(app_module.validate_select_query("SELECT * FROM orders_sample").lower().startswith("select"))
        self.assertTrue(app_module.validate_select_query("WITH a AS (SELECT 1) SELECT * FROM a").lower().startswith("with"))
        with self.assertRaises(ValueError):
            app_module.validate_select_query("DELETE FROM orders_sample")

    def test_comments_before_select_are_supported(self):
        self.assertTrue(app_module.validate_select_query("-- comment\n SELECT 1").lower().startswith("select"))
        with self.assertRaises(ValueError):
            app_module.validate_select_query("/* bad comment")

    def test_read_query_cannot_write(self):
        dataset = app_module.get_dataset("sample-orders")
        result = app_module.run_safe_query(dataset, "SELECT region, COUNT(*) AS orders FROM orders_sample GROUP BY region ORDER BY orders DESC")
        self.assertEqual(len(result["rows"]), 4)
        with self.assertRaises(ValueError):
            app_module.run_safe_query(dataset, "DELETE FROM orders_sample")

    def test_query_cannot_access_another_table(self):
        dataset = app_module.get_dataset("sample-orders")
        with self.assertRaises(ValueError):
            app_module.run_safe_query(dataset, "SELECT name FROM datasets")

    def test_select_is_limited_to_one_statement(self):
        dataset = app_module.get_dataset("sample-orders")
        with self.assertRaises(ValueError):
            app_module.run_safe_query(dataset, "SELECT * FROM orders_sample; SELECT * FROM orders_sample")


if __name__ == "__main__":
    unittest.main()
