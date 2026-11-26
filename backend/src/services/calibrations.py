"""Calibration lifecycle: master-batch grouped CV, blind review and atomic publish."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.business.calibration import calibrate
from src.business.profile import PROFILE
from src.business.publishing import PublishRejected, apply_publish_transition, enforce_publish_rules
from src.config.settings import Session
from src.constants.workflow import CalibrationStage
from src.models.base import utcnow
from src.models.calibration import Calibration
from src.models.dataset import Dataset
from src.schemas.resources import calibration_view
from src.services import datasets
from src.services.audit import record
from src.utils.timeutil import iso


def list_calibrations():
    with Session() as db:
        items = db.scalars(
            select(Calibration).order_by(Calibration.created_at.desc(), Calibration.id.desc())
        )
        return [calibration_view(item) for item in items]


def create_calibration(dataset_id: str, actor: str):
    """对一份称重档案分基材校准；盲评通过的基材进入 candidate，未通过标 rejected。"""
    control = PROFILE["calibration"]
    with Session.begin() as db:
        dataset = datasets.require(db, dataset_id)
        try:
            reports, warnings = calibrate(dataset.rows, control["k_min"], control["k_max"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        for message in warnings:
            record(db, actor, "calibration_skipped", f"{dataset.id}:{message}"[:100])
        created = []
        for report in reports:
            status = (CalibrationStage.CANDIDATE.value if report["blind_passed"]
                      else CalibrationStage.REJECTED.value)
            item = Calibration(
                dataset_id=dataset.id,
                substrate=report["substrate"],
                status=status,
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
                actor=actor,
            )
            db.add(item)
            try:
                with db.begin_nested():
                    db.flush()
            except IntegrityError:
                raise HTTPException(409, f"基材 {report['substrate']} 已基于该档案完成校准，请直接查看或发布既有版本。")
            record(db, actor, "calibration_created", item.id)
            created.append(calibration_view(item))
        return created


def publish_calibration(calibration_id: str, publisher: str):
    """发布前再次核验盲评结论与档案新旧，事务内原子切换；失败时旧版保持发布。"""
    with Session.begin() as db:
        item = db.get(Calibration, calibration_id)
        if item is None:
            raise HTTPException(404, "校准版本不存在。")
        if item.status == CalibrationStage.PUBLISHED.value:
            return calibration_view(item)
        latest = db.scalar(select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id.desc()).limit(1))
        try:
            enforce_publish_rules(item, latest.id if latest else None)
        except PublishRejected as exc:
            message = str(exc)
            if item.status == CalibrationStage.CANDIDATE.value and item.blind_error > item.default_blind_error:
                item.status = CalibrationStage.REJECTED.value
                record(db, publisher, "calibration_rejected", item.id)
            raise HTTPException(422 if "盲评" in message else 409, message) from exc

        previous = db.scalar(
            select(Calibration).where(
                Calibration.substrate == item.substrate,
                Calibration.status == CalibrationStage.PUBLISHED.value,
            ).with_for_update()
        )
        apply_publish_transition(item, previous, publisher, utcnow())
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "该基材已有另一个并发发布的校准版本，本次切换未生效，旧版继续服务。") from exc
        record(db, publisher, "calibration_published", item.id)
        return calibration_view(item)


def published_map(db) -> tuple[dict, list]:
    """供推荐计算取用：返回基材→近邻数 与 溯源快照。"""
    items = db.scalars(
        select(Calibration).where(Calibration.status == CalibrationStage.PUBLISHED.value)
    ).all()
    neighbor_map = {item.substrate: item.chosen_neighbors for item in items}
    snapshot = [
        {
            "calibration_id": item.id,
            "dataset_id": item.dataset_id,
            "substrate": item.substrate,
            "chosen_neighbors": item.chosen_neighbors,
            "default_neighbors": item.default_neighbors,
            "blind_master": item.blind_master,
            "blind_error": item.blind_error,
            "default_blind_error": item.default_blind_error,
            "publisher": item.publisher,
            "published_at": iso(item.published_at),
        }
        for item in items
    ]
    meta = {
        item.substrate: {
            "calibration_id": item.id,
            "dataset_id": item.dataset_id,
            "blind_master": item.blind_master,
            "blind_error": item.blind_error,
            "default_blind_error": item.default_blind_error,
        }
        for item in items
    }
    return neighbor_map, meta, snapshot
