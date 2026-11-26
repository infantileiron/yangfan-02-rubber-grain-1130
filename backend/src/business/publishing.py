"""发布门禁的纯业务规则，不依赖 ORM 或 Web 框架，便于独立测试。"""

from src.constants.workflow import CalibrationStage


class PublishRejected(ValueError):
    """发布验收失败，线上旧版保持不变。"""


def enforce_publish_rules(item, latest_dataset_id: str) -> None:
    """发布前核验：状态须为候选、盲评不退步、档案须为该基材最新档案。"""
    if item.status == CalibrationStage.PUBLISHED.value:
        return
    if item.status != CalibrationStage.CANDIDATE.value:
        raise PublishRejected("盲评未通过的校准版本不能发布，线上继续保留旧版推荐。")
    if item.blind_error > item.default_blind_error:
        raise PublishRejected("发布前复验发现盲评误差高于默认近邻，验收失败并保留旧版。")
    if latest_dataset_id != item.dataset_id:
        raise PublishRejected("称重档案已不是最新档案，请用最新档案重新校准后再发布。")


def apply_publish_transition(item, previous, publisher: str, now) -> None:
    """已通过核验后的原子切换：旧版回退候选，新版置为发布。"""
    if item.status == CalibrationStage.PUBLISHED.value:
        return
    if previous is not None:
        previous.status = CalibrationStage.CANDIDATE.value
        previous.publish_key = None
        previous.publisher = None
        previous.published_at = None
    item.status = CalibrationStage.PUBLISHED.value
    item.publish_key = item.substrate
    item.publisher = publisher
    item.published_at = now
