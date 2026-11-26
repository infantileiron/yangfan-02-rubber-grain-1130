from enum import Enum


class Role(str, Enum):
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Stage(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CalibrationStage(str, Enum):
    CANDIDATE = "candidate"   # 盲评通过，等待发布
    PUBLISHED = "published"   # 已发布，推荐服务取用
    REJECTED = "rejected"     # 盲评不退步，保留记录但不参与推荐


class Decision(str, Enum):
    APPROVE = "approve"
    HOLD = "hold"
