export const roles = { analyst: '分析员', reviewer: '复核员', viewer: '观察员' };
export const stages = { queued: '排队中', running: '计算中', succeeded: '已完成', failed: '失败' };
export const decisions = { approve: '签发', hold: '暂缓' };
export const auditActions = {
  dataset_imported: '导入数据',
  run_queued: '提交计算',
  run_succeeded: '完成计算',
  run_failed: '计算失败',
  review_approve: '签发交接',
  review_hold: '暂缓交接',
  calibration_created: '创建校准',
  calibration_published: '发布校准',
  calibration_rejected: '校准验收失败',
  calibration_skipped: '基材跳过校准',
};

export const calibrationStages = {
  candidate: '待发布（盲评通过）',
  published: '已发布',
  rejected: '盲评未通过',
};

export const neighborSources = {
  published_calibration: '已发布校准',
  fallback: '旧版默认口径',
};
