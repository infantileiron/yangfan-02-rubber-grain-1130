"""端到端业务串联：校准结果转发布版本，再驱动推荐与溯源字段。

不触碰数据库和 Web 框架，只验证跨模块的数据契约。
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.business.algorithm import analyze
from src.business.calibration import calibrate
from src.business.demo import demo_rows
from src.business.profile import PROFILE
from src.business.publishing import apply_publish_transition, enforce_publish_rules
from src.constants.workflow import CalibrationStage
from src.utils.csv_data import parse_csv, render_csv


def rows():
    keys = [column["key"] for column in PROFILE["columns"]]
    return parse_csv(render_csv(demo_rows(), keys), PROFILE["columns"])


class EndToEndFlowTests(unittest.TestCase):
    def test_calibration_to_published_recommendation_flow(self):
        data = rows()
        dataset_id = "ds-latest"
        reports, warnings = calibrate(data)
        self.assertEqual(warnings, [])

        # 模拟每个基材的校准版本实体（与 Calibration 模型字段对齐）
        versions = {}
        for report in reports:
            versions[report["substrate"]] = SimpleNamespace(
                id=f"cal-{report['substrate']}",
                dataset_id=dataset_id,
                substrate=report["substrate"],
                status=(CalibrationStage.CANDIDATE.value if report["blind_passed"]
                        else CalibrationStage.REJECTED.value),
                publish_key=None,
                chosen_neighbors=report["chosen_neighbors"],
                default_neighbors=report["default_neighbors"],
                blind_master=report["blind_master"],
                blind_samples=report["blind_samples"],
                cv_errors=report["cv_errors"],
                blind_error=report["blind_error"],
                default_blind_error=report["default_blind_error"],
                master_count=report["master_count"],
                qualified_count=report["qualified_count"],
                publisher=None,
                published_at=None,
            )

        # 复核员逐个发布：未通过的被拒，通过的上线
        published = {}
        for substrate, item in versions.items():
            try:
                enforce_publish_rules(item, dataset_id)
            except Exception:
                self.assertEqual(item.status, CalibrationStage.REJECTED.value)
                continue
            apply_publish_transition(item, published.get(substrate), "reviewer@demo.local", None)
            published[substrate] = item

        self.assertIn("再生 EPDM", published)
        self.assertNotIn("再生 SBR", published)

        # 执行器侧等价的 published_map
        neighbor_map = {item.substrate: item.chosen_neighbors for item in published.values()}
        meta = {
            item.substrate: {
                "calibration_id": item.id,
                "dataset_id": item.dataset_id,
                "blind_master": item.blind_master,
                "blind_error": item.blind_error,
                "default_blind_error": item.default_blind_error,
            }
            for item in published.values()
        }
        result = analyze(data, PROFILE["parameter"]["default"], neighbor_map, meta)

        epdm = [row for row in result["rows"] if row["substrate"] == "再生 EPDM"]
        sbr = [row for row in result["rows"] if row["substrate"] == "再生 SBR"]
        self.assertTrue(all(row["neighbor_source"] == "published_calibration" for row in epdm))
        self.assertTrue(all(row["neighbor_source"] == "fallback" for row in sbr))
        self.assertTrue(all(row["archive_dataset_id"] == dataset_id for row in epdm))
        self.assertTrue(all(row["blind_error"] is not None for row in epdm))
        # 结果说明同时覆盖发布口径与补录兜底口径
        joined = " ".join(result["notes"])
        self.assertIn("已发布母批盲评校准", joined)
        self.assertIn("沿用旧版口径", joined)

    def test_republish_replaces_old_version_atomically(self):
        old = SimpleNamespace(
            id="cal-old", dataset_id="ds-new", substrate="再生 EPDM",
            status=CalibrationStage.PUBLISHED.value, publish_key="再生 EPDM",
            blind_error=2.0, default_blind_error=3.0, chosen_neighbors=4,
            publisher="r@x", published_at="2026-01-01",
        )
        new = SimpleNamespace(
            id="cal-new", dataset_id="ds-new", substrate="再生 EPDM",
            status=CalibrationStage.CANDIDATE.value, publish_key=None,
            blind_error=1.5, default_blind_error=3.0, chosen_neighbors=5,
            publisher=None, published_at=None,
        )
        enforce_publish_rules(new, "ds-new")
        apply_publish_transition(new, old, "r@x", "now")
        self.assertEqual(new.status, CalibrationStage.PUBLISHED.value)
        self.assertEqual(new.publish_key, "再生 EPDM")
        self.assertEqual(old.status, CalibrationStage.CANDIDATE.value)
        self.assertIsNone(old.publish_key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
