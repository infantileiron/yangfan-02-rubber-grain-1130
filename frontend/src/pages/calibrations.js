import { api } from '../api/workspace.js';
import { table } from '../components/common/table.js';
import { empty, heading } from '../components/common/heading.js';
import { bindForm, notice } from '../hooks/forms.js';
import { calibrationStages } from '../constants/enums.js';
import { escapeHtml as e, shortId, timeText } from '../utils/format.js';

const listColumns = [
  { key: 'substrate', label: '基材' },
  { key: 'status', label: '校准状态' },
  { key: 'dataset_id', label: '称重档案' },
  { key: 'chosen_neighbors', label: '选定近邻数' },
  { key: 'default_neighbors', label: '默认近邻数' },
  { key: 'blind_master', label: '盲评母批' },
  { key: 'blind_error', label: '盲评误差（百分点）' },
  { key: 'default_blind_error', label: '默认近邻盲评误差' },
  { key: 'created_at', label: '创建时间' },
];

export async function calibrationsPage(profile, account) {
  const [items, datasets] = await Promise.all([api.calibrations(), api.datasets()]);
  const rule = profile.calibration.rule;
  const canCalibrate = account.role === 'analyst' && datasets.length > 0;
  const canPublish = account.role === 'reviewer';
  const form = canCalibrate ? `<form id="calibration-form">
    <label>称重档案<select name="dataset_id">${datasets.map(row =>
      `<option value="${row.id}">${e(row.name)} · ${row.count} 行 · ${e(row.checksum.slice(0, 8))}</option>`).join('')}</select></label>
    <p class="muted">分基材按母批留出交叉验证选近邻数，并自动留一个母批做盲评。</p>
    <div class="form-error" data-error role="alert"></div>
    <button type="submit">创建校准</button></form>` :
    '<p class="muted">分析员可选择称重档案创建校准。</p>';

  const detail = items.length ? table(listColumns, items, (row, column, value) => {
    if (column.key === 'status') return `<span class="status s-${e(row.status)}">${e(calibrationStages[row.status] ?? value)}</span>`;
    if (column.key === 'dataset_id') return `<a href="#datasets/${row.dataset_id}">${e(shortId(value))}</a>`;
    if (column.key === 'created_at') return e(timeText(value));
    return e(value);
  }) : empty('还没有校准版本', '导入含母批号的称重档案后，创建分基材近邻数校准。');

  const cards = items.map(item => `<article class="cal-card">
      <header><strong>${e(item.substrate)}</strong>
        <span class="status s-${e(item.status)}">${e(calibrationStages[item.status] ?? item.status)}</span></header>
      <dl class="meta">
        <dt>称重档案</dt><dd><a href="#datasets/${item.dataset_id}">${e(shortId(item.dataset_id))}</a></dd>
        <dt>盲评母批</dt><dd>${e(item.blind_master)}（${item.blind_samples.length} 个子批整体退出）</dd>
        <dt>选定 / 默认近邻数</dt><dd>${item.chosen_neighbors} / ${item.default_neighbors}</dd>
        <dt>盲评误差</dt><dd>${e(item.blind_error)} 对 ${e(item.default_blind_error)} 个百分点
          ${item.blind_passed === false ? '<strong class="warn">未通过</strong>' : ''}</dd>
        <dt>合格母批 / 合格批次</dt><dd>${item.master_count} / ${item.qualified_count}</dd>
      </dl>
      <h4>各近邻数交叉验证误差（四色配比百分点）</h4>
      <ol class="cv-list">${item.cv_errors.map(point =>
        `<li class="${point.neighbors === item.chosen_neighbors ? 'chosen' : ''}">
          ${point.neighbors} 近邻：${e(point.cv_error)}${point.neighbors === item.chosen_neighbors ? '（选定）' : ''}</li>`).join('')}</ol>
      ${canPublish && item.status === 'candidate' ?
        `<button type="button" class="publish-btn" data-id="${item.id}">发布该版本</button>` : ''}
      ${item.status === 'published' ? `<p class="muted">发布人：${e(item.publisher)} · ${e(timeText(item.published_at))}</p>` : ''}
      ${item.status === 'rejected' ? '<p class="muted warn">盲评相对默认近邻不退步，保留旧版推荐。</p>' : ''}
    </article>`).join('');

  return {
    html: heading(profile.labels.calibrations, profile.algorithm) +
      `<div class="board"><aside class="side"><h2>校准设置</h2>${form}
        <details class="details" open><summary>验收与发布口径</summary><p class="muted">${e(rule)}</p>
        <p class="muted">${e(profile.calibration.error_metric)}</p></details></aside>
      <section class="work"><div class="work-head"><h2>校准版本</h2></div>
      ${detail}
      <h3>分基材明细</h3>
      <div class="cal-grid">${cards || empty('暂无校准明细', '创建校准后在此查看交叉验证与盲评结果。')}</div>
      </section></div>`,
    mount(root, refresh) {
      bindForm(root, 'calibration-form', async data => {
        const created = await api.calibrate({ dataset_id: data.get('dataset_id') });
        const passed = created.filter(item => item.status === 'candidate').length;
        const rejected = created.length - passed;
        notice(`校准完成：${passed} 个基材盲评通过待发布，${rejected} 个未通过并保留旧版。`);
        refresh();
      });
      root.querySelectorAll('.publish-btn').forEach(button => {
        button.onclick = async () => {
          button.disabled = true;
          try {
            await api.publishCalibration(button.dataset.id);
            notice('校准版本已发布，新计算单将采用该近邻数。');
            refresh();
          } catch (error) {
            notice(error.message, 'error');
            button.disabled = false;
          }
        };
      });
    },
  };
}
