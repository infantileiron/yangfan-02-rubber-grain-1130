"""母批留出校准与发布门禁的端到端业务测试（仅依赖标准库）。"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.business.algorithm import analyze
from src.business.calibration import calibrate, composition_error
from src.business.demo import demo_rows
from src.business.profile import PROFILE
from src.business.publishing import PublishRejected, apply_publish_transition, enforce_publish_rules
from src.constants.workflow import CalibrationStage
from src.utils.csv_data import parse_csv, render_csv


def load_rows():
    keys = [column["key"] for column in PROFILE["columns"]]
    return parse_csv(render_csv(demo_rows(), keys), PROFILE["columns"])


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_rows()
        cls.reports = {item["substrate"]: item for item in calibrate(cls.rows)[0]}

    def test_demo_has_master_batches_with_multiple_sub_batches(self):
        groups = {}
        for row in self.rows:
            if row["scope"] == "历史归档":
                self.assertTrue(row["master_batch"])
                groups.setdefault(row["master_batch"], []).append(row["sample_id"])
        self.assertTrue(all(len(values) >= 4 for values in groups.values()))

    def test_blind_master_excluded_from_cv_and_neighbor_pool(self):
        for report in self.reports.values():
            # 盲评母批的全部子批都登记为盲评样本
            blind_ids = set(report["blind_samples"])
            self.assertTrue(blind_ids)
            for row in self.rows:
                if row["sample_id"] in blind_ids:
                    self.assertEqual(row["master_batch"], report["blind_master"])

    def test_blind_review_compares_same_samples_against_default(self):
        epdm = self.reports["再生 EPDM"]
        self.assertEqual(epdm["default_neighbors"], 3)
        self.assertLessEqual(epdm["blind_error"], epdm["default_blind_error"])
        self.assertTrue(epdm["blind_passed"])
        sbr = self.reports["再生 SBR"]
        self.assertFalse(sbr["blind_passed"])

    def test_cv_selects_lowest_error_with_smaller_k_tie_break(self):
        for report in self.reports.values():
            errors = report["cv_errors"]
            best = min(errors, key=lambda item: (item["cv_error"], item["neighbors"]))
            self.assertEqual(best["neighbors"], report["chosen_neighbors"])

    def test_missing_master_batch_rejected(self):
        broken = [dict(row) for row in self.rows]
        broken[1]["master_batch"] = None
        with self.assertRaises(ValueError):
            calibrate(broken)[0]

    def test_substrate_with_too_few_masters_is_skipped_with_warning(self):
        thinned = [row for row in self.rows
                   if row["scope"] != "历史归档"
                   or row["substrate"] != "再生 SBR"
                   or row["master_batch"] in {"MB-SBR-01", "MB-SBR-02"}]
        reports, warnings = calibrate(thinned)
        substrates = {report["substrate"] for report in reports}
        self.assertIn("再生 EPDM", substrates)
        self.assertNotIn("再生 SBR", substrates)
        self.assertTrue(any("再生 SBR" in message for message in warnings))

    def test_grouped_holdout_is_stricter_than_row_holdout(self):
        """同桶不整体留出会显著低估误差，证明按母批留出的必要性。"""
        from src.business.calibration import _fold_error, qualified_archive
        groups = qualified_archive(self.rows)["再生 EPDM"]
        masters = sorted(groups)
        flat = [item for group in groups.values() for item in group]
        wrong = sum(_fold_error(flat[:i] + flat[i + 1:], [held], 3)
                    for i, held in enumerate(flat)) / len(flat)
        cv_masters = [master for master in masters if master != self.reports["再生 EPDM"]["blind_master"]]
        right_folds = []
        for held_master in cv_masters:
            pool = [item for master in cv_masters if master != held_master for item in groups[master]]
            right_folds.append(_fold_error(pool, groups[held_master], 3))
        right = sum(right_folds) / len(right_folds)
        self.assertLess(wrong, right)


class RecommendationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_rows()
        reports, warnings = calibrate(cls.rows)
        cls.neighbor_map = {}
        cls.meta = {}
        for report in reports:
            if report["blind_passed"]:
                cls.neighbor_map[report["substrate"]] = report["chosen_neighbors"]
                cls.meta[report["substrate"]] = {
                    "calibration_id": "cal-1", "dataset_id": "ds-1",
                    "blind_master": report["blind_master"],
                    "blind_error": report["blind_error"],
                    "default_blind_error": report["default_blind_error"],
                }

    def test_fallback_uses_default_neighbors_without_published_version(self):
        result = analyze(self.rows, 3)
        self.assertTrue(all(row["neighbor_source"] == "fallback" for row in result["rows"]))
        self.assertTrue(all(row["neighbor_count"] == 3 for row in result["rows"]))

    def test_published_calibration_overrides_per_substrate(self):
        result = analyze(self.rows, 3, self.neighbor_map, self.meta)
        for row in result["rows"]:
            if row["substrate"] in self.neighbor_map:
                self.assertEqual(row["neighbor_source"], "published_calibration")
                self.assertEqual(row["neighbor_count"], self.neighbor_map[row["substrate"]])
                self.assertEqual(row["archive_dataset_id"], "ds-1")
                self.assertIsNotNone(row["blind_error"])
            else:
                self.assertEqual(row["neighbor_source"], "fallback")
                self.assertIsNone(row["archive_dataset_id"])

    def test_export_columns_cover_traceability(self):
        result = analyze(self.rows, 3, self.neighbor_map, self.meta)
        keys = {column["key"] for column in PROFILE["result_columns"]}
        self.assertTrue(keys.issubset(result["rows"][0]))
        self.assertIn("archive_dataset_id", keys)
        self.assertIn("blind_error", keys)
        self.assertIn("neighbor_count", keys)


class PublishingGateTests(unittest.TestCase):
    def _item(self, **overrides):
        data = dict(
            id="cal-new", dataset_id="ds-latest", substrate="再生 EPDM",
            status=CalibrationStage.CANDIDATE.value, publish_key=None,
            blind_error=2.1, default_blind_error=3.4,
            chosen_neighbors=4, publisher=None, published_at=None,
        )
        data.update(overrides)
        return SimpleNamespace(**data)

    def test_candidate_passes_and_replaces_previous(self):
        item = self._item()
        previous = self._item(id="cal-old", status=CalibrationStage.PUBLISHED.value,
                              publish_key="再生 EPDM", publisher="reviewer@demo.local",
                              published_at=datetime(2026, 1, 1))
        enforce_publish_rules(item, "ds-latest")
        apply_publish_transition(item, previous, "reviewer@demo.local", datetime(2026, 11, 26))
        self.assertEqual(item.status, CalibrationStage.PUBLISHED.value)
        self.assertEqual(item.publish_key, "再生 EPDM")
        self.assertEqual(previous.status, CalibrationStage.CANDIDATE.value)
        self.assertIsNone(previous.publish_key)

    def test_blind_regression_blocks_and_keeps_old_version(self):
        item = self._item(blind_error=4.0, default_blind_error=3.2)
        previous = self._item(id="cal-old", status=CalibrationStage.PUBLISHED.value,
                              publish_key="再生 EPDM")
        with self.assertRaises(PublishRejected):
            enforce_publish_rules(item, "ds-latest")
        self.assertEqual(previous.status, CalibrationStage.PUBLISHED.value)

    def test_rejected_status_cannot_be_published(self):
        item = self._item(status=CalibrationStage.REJECTED.value)
        with self.assertRaises(PublishRejected):
            enforce_publish_rules(item, "ds-latest")

    def test_stale_archive_blocked(self):
        item = self._item(dataset_id="ds-old")
        with self.assertRaises(PublishRejected):
            enforce_publish_rules(item, "ds-latest")

    def test_already_published_is_idempotent(self):
        item = self._item(status=CalibrationStage.PUBLISHED.value,
                          publish_key="再生 EPDM", publisher="r@demo.local")
        enforce_publish_rules(item, "ds-latest")
        apply_publish_transition(item, None, "r@demo.local", datetime(2026, 11, 26))
        self.assertEqual(item.publisher, "r@demo.local")


class CompositionErrorTests(unittest.TestCase):
    def test_error_is_mean_percentage_point_gap(self):
        self.assertAlmostEqual(composition_error((0.5, 0.25, 0.25, 0.0),
                                                 (0.4, 0.25, 0.25, 0.1)), 5.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
