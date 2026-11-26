from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class Calibration(Base):
    """分基材的近邻数校准版本。

    每个基材至多有一个 published 版本。publish_key 仅在发布时写入基材名，
    其余状态为 NULL；依赖唯一索引允许多个 NULL 的特性保证并发发布只有一个胜出，
    验收失败的版本保持 failed，已发布旧版继续服务。
    """

    __tablename__ = "calibrations"
    __table_args__ = (
        UniqueConstraint("dataset_id", "substrate", name="one_calibration_per_dataset_substrate"),
        UniqueConstraint("substrate", "publish_key", name="one_published_per_substrate"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    substrate: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    publish_key: Mapped[str | None] = mapped_column(String(60))
    chosen_neighbors: Mapped[int]
    default_neighbors: Mapped[int]
    blind_master: Mapped[str] = mapped_column(String(60))
    blind_samples: Mapped[list] = mapped_column(JSON)
    cv_errors: Mapped[list] = mapped_column(JSON)
    blind_error: Mapped[float]
    default_blind_error: Mapped[float]
    master_count: Mapped[int]
    qualified_count: Mapped[int]
    actor: Mapped[str] = mapped_column(String(160))
    publisher: Mapped[str | None] = mapped_column(String(160))
    published_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
