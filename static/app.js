const $ = (id) => document.getElementById(id);
let monitors = [];
let selectedId = null;
let editingId = null;
let reportRange = '24h';
let detailVersion = 0;
let toastTimer;

function notice(message) {
  $('toast').textContent = message;
  $('toast').classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 3500);
}

async function api(path, options) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

function formatTime(value) {
  if (!value) return '尚未检查';
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatBucket(bucket, range) {
  if (range === '24h') return new Date(bucket.start).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const options = { month: '2-digit', day: '2-digit' };
  return `${new Date(bucket.start).toLocaleString('zh-CN', options)}–${new Date(bucket.end).toLocaleString('zh-CN', options)}`;
}

function metric(value, suffix = '') { return value === null ? '暂无数据' : `${value}${suffix}`; }

function statusFor(monitor) {
  return monitor.paused ? ['paused', '已暂停'] : monitor.up === null ? ['pending', '等待检查'] : monitor.up ? ['up', '运行正常'] : ['down', '服务异常'];
}

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = value;
  return node;
}

function button(label, handler, extraClass = '') {
  const node = element('button', `small-button ${extraClass}`, label);
  node.type = 'button';
  node.addEventListener('click', handler);
  return node;
}

function renderRow(monitor) {
  const row = element('div', 'monitor-row');
  const main = element('div', 'monitor-main');
  const icon = element('div', 'service-icon', monitor.name.trim().charAt(0).toUpperCase());
  const info = element('div');
  info.style.minWidth = '0';
  info.append(element('div', 'service-name', monitor.name), element('div', 'service-url', monitor.url));
  main.append(icon, info);
  row.append(main);

  const [state, label] = statusFor(monitor);
  const statusCell = element('div');
  statusCell.append(element('span', `status ${state}`, label));
  row.append(statusCell);
  row.append(element('div', 'cell-value response-cell', monitor.last_response_ms === null ? '—' : `${monitor.last_response_ms} ms`));
  row.append(element('div', 'cell-value interval-cell', `${monitor.interval} 秒`));
  const actions = element('div', 'row-actions');
  actions.append(button('详情', () => showDetail(monitor.id)), button('检查', () => runCheck(monitor.id)));
  row.append(actions);
  return row;
}

function render() {
  $('count-total').textContent = monitors.length;
  $('count-up').textContent = monitors.filter(m => !m.paused && m.up === true).length;
  $('count-down').textContent = monitors.filter(m => !m.paused && m.up === false).length;
  $('count-pending').textContent = monitors.filter(m => m.paused || m.up === null).length;
  $('monitor-count').textContent = `${monitors.length} 项`;
  const list = $('monitor-list');
  list.replaceChildren();
  if (!monitors.length) {
    const empty = element('div', 'empty');
    empty.append(element('div', 'empty-art', '◉'), element('h3', '', '还没有监控项'), element('p', '', '添加一个网站地址，开始追踪服务状态。'));
    list.append(empty);
  } else {
    monitors.forEach(monitor => list.append(renderRow(monitor)));
  }
}

async function refresh() {
  try {
    const data = await api('/api/monitors');
    monitors = data.monitors;
    render();
    $('updated').textContent = `更新于 ${new Date(data.server_time).toLocaleTimeString('zh-CN')}`;
    if (selectedId !== null) await showDetail(selectedId, false);
  } catch (error) {
    $('updated').textContent = '连接失败';
    notice(`无法加载监控：${error.message}`);
  }
}

async function runCheck(id) {
  try {
    notice('正在检查服务…');
    const result = await api(`/api/monitors/${id}/check`, { method: 'POST', body: '{}' });
    await refresh();
    notice(result.up ? '检查完成：服务运行正常' : `检查完成：${result.error || '服务异常'}`);
  } catch (error) { notice(error.message); }
}

async function showDetail(id, scroll = true) {
  const monitor = monitors.find(item => item.id === id);
  if (!monitor) { selectedId = null; $('detail').classList.add('hidden'); return; }
  if (selectedId !== id) reportRange = '24h';
  selectedId = id;
  const version = ++detailVersion;
  const [data, stats, report] = await Promise.all([
    api(`/api/monitors/${id}/history`),
    api(`/api/monitors/${id}/statistics`),
    api(`/api/monitors/${id}/report?range=${reportRange}`),
  ]);
  if (version !== detailVersion || selectedId !== id) return;
  $('detail-title').textContent = `${monitor.name} · 检查记录`;
  const body = $('detail-body');
  body.replaceChildren();
  const inner = element('div', 'detail-inner');
  const meta = element('div', 'detail-meta');
  meta.append(element('span', '', monitor.url), element('span', '', `检查间隔 ${monitor.interval} 秒`), element('span', '', `上次检查 ${formatTime(monitor.last_checked)}`));
  if (monitor.paused) meta.append(element('span', 'paused-note', '自动检查已暂停'));
  inner.append(meta, renderReport(id, report), element('p', 'history-title', '最近检查状态'));
  const bars = element('div', 'history-bars');
  bars.setAttribute('aria-label', '最近检查状态图');
  data.history.slice(0, 40).reverse().forEach(item => {
    const bar = element('span', `history-bar ${item.up ? 'up' : 'down'}`);
    bar.title = `${formatTime(item.checked_at)} · ${item.up ? '正常' : '异常'}`;
    bars.append(bar);
  });
  if (!data.history.length) bars.append(element('span', 'history-bar'));
  inner.append(bars);
  const history = element('div', 'history-list');
  data.history.slice(0, 10).forEach(item => {
    const line = element('div', 'history-item');
    line.append(element('span', `status ${item.up ? 'up' : 'down'}`, item.up ? '正常' : '异常'), element('strong', '', item.error || `HTTP ${item.status_code}`), element('span', 'time', formatTime(item.checked_at)), element('span', '', `${item.response_ms} ms`));
    history.append(line);
  });
  if (!data.history.length) history.append(element('p', '', '尚无检查记录'));
  inner.append(history, element('p', 'history-title incident-title', '近 24 小时异常时段'));
  const incidents = element('div', 'incident-list');
  stats.incidents.forEach(item => incidents.append(element('div', 'incident-item', `${formatTime(item.start)} — ${item.end ? formatTime(item.end) : '仍在异常中'}`)));
  if (!stats.incidents.length) incidents.append(element('p', 'metric-note', '近 24 小时没有异常记录'));
  inner.append(incidents);
  const actions = element('div', 'history-actions');
  actions.append(button('立即检查', () => runCheck(id)), button('编辑', () => openEdit(id)), button(monitor.paused ? '恢复自动检查' : '暂停自动检查', () => togglePaused(id, !monitor.paused)), button('删除监控', () => deleteMonitor(id), 'danger'));
  inner.append(actions);
  body.append(inner);
  $('detail').classList.remove('hidden');
  if (scroll) $('detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderReport(id, report) {
  const section = element('section', 'report-section');
  section.setAttribute('aria-label', '监控报表');
  const head = element('div', 'report-head');
  head.append(element('h3', '', '运行报表'));
  const controls = element('div', 'report-controls');
  for (const [range, label] of [['24h', '近 24 小时'], ['7d', '近 7 天']]) {
    const control = button(label, () => { reportRange = range; showDetail(id, false).catch(error => notice(error.message)); });
    control.setAttribute('aria-pressed', String(report.range === range));
    controls.append(control);
  }
  const exportLink = element('a', 'small-button export-link', '导出 CSV');
  exportLink.href = `/api/monitors/${id}/report.csv?range=${report.range}`;
  exportLink.setAttribute('download', `pulse-monitor-${id}-${report.range}.csv`);
  controls.append(exportLink);
  head.append(controls);
  section.append(head);
  const summary = element('div', 'report-summary');
  for (const [label, value] of [
    ['检查可用率', metric(report.availability, '%')],
    ['成功 / 总检查', `${report.successes} / ${report.checks}`],
    ['失败检查', String(report.failures)],
    ['成功检查平均响应', metric(report.average_response_ms, ' ms')],
  ]) {
    const card = element('div', 'report-metric');
    card.append(element('span', '', label), element('strong', '', value));
    summary.append(card);
  }
  section.append(summary, element('p', 'metric-note', '可用率按检查次数计算；空白时段没有检查记录。时间标签按本地时间显示。'));
  section.append(reportChart(report, 'availability', '检查可用率', '%'));
  section.append(reportChart(report, 'average_response_ms', '平均响应时间（成功检查）', ' ms'));
  const details = element('details', 'report-table-wrap');
  details.append(element('summary', '', '查看各时段数据'));
  const table = element('table', 'report-table');
  const header = element('tr');
  for (const name of ['时段开始', '检查', '成功', '失败', '可用率', '平均响应']) header.append(element('th', '', name));
  table.append(header);
  for (const bucket of report.buckets) {
    const row = element('tr');
    for (const value of [formatTime(bucket.start), bucket.checks, bucket.successes, bucket.failures,
      metric(bucket.availability, '%'), metric(bucket.average_response_ms, ' ms')]) row.append(element('td', '', String(value)));
    table.append(row);
  }
  const scroll = element('div', 'report-table-scroll');
  scroll.append(table);
  details.append(scroll);
  section.append(details);
  return section;
}

function reportChart(report, key, title, unit) {
  const wrapper = element('div', 'report-chart');
  wrapper.append(element('h4', '', title));
  const plot = element('div', 'report-plot');
  plot.classList.add(report.range === '24h' ? 'hourly' : 'daily');
  const values = report.buckets.map(bucket => bucket[key]).filter(value => value !== null);
  const max = key === 'availability' ? 100 : Math.max(1, ...values);
  report.buckets.forEach((bucket, index) => {
    const column = element('div', 'report-column');
    const value = bucket[key];
    const bar = element('div', `report-bar ${value === null ? 'missing' : key === 'availability' ? 'availability' : 'latency'}`);
    bar.style.height = value === null ? '3px' : `${Math.max(3, 100 * value / max)}%`;
    const description = `${formatTime(bucket.start)} 至 ${formatTime(bucket.end)}：${metric(value, unit)}，${bucket.checks} 次检查`;
    bar.title = description;
    bar.setAttribute('aria-label', description);
    bar.tabIndex = 0;
    const label = report.range === '24h' && index % 3 !== 0 && index !== report.buckets.length - 1 ? '' : formatBucket(bucket, report.range);
    column.append(bar, element('span', 'report-xlabel', label));
    plot.append(column);
  });
  wrapper.append(plot);
  return wrapper;
}

async function deleteMonitor(id) {
  const monitor = monitors.find(item => item.id === id);
  if (!window.confirm(`确定删除「${monitor.name}」及其检查记录吗？`)) return;
  try {
    await api(`/api/monitors/${id}`, { method: 'DELETE' });
    selectedId = null;
    $('detail').classList.add('hidden');
    await refresh();
    notice('监控已删除');
  } catch (error) { notice(error.message); }
}

async function togglePaused(id, paused) {
  try {
    await api(`/api/monitors/${id}`, { method: 'PATCH', body: JSON.stringify({ paused }) });
    await refresh();
    notice(paused ? '已暂停自动检查；仍可手动检查' : '已恢复自动检查');
  } catch (error) { notice(error.message); }
}

function openEdit(id) {
  const monitor = monitors.find(item => item.id === id);
  if (!monitor) return;
  editingId = id;
  $('modal-eyebrow').textContent = 'EDIT MONITOR';
  $('modal-title').textContent = '编辑监控';
  $('submit-monitor').textContent = '保存修改';
  $('form-hint').textContent = '修改地址会清除当前状态并重新检查，历史记录会保留。';
  $('name').value = monitor.name;
  $('url').value = monitor.url;
  $('interval').value = monitor.interval;
  $('modal').classList.remove('hidden');
  $('name').focus();
}

function openAdd() {
  editingId = null;
  $('add-form').reset();
  $('modal-eyebrow').textContent = 'NEW MONITOR';
  $('modal-title').textContent = '添加监控';
  $('submit-monitor').textContent = '创建监控';
  $('form-hint').textContent = '支持 HTTP 和 HTTPS。添加后会自动开始第一次检查。';
  $('modal').classList.remove('hidden');
  $('name').focus();
}

function closeModal() { $('modal').classList.add('hidden'); $('form-error').textContent = ''; }
$('open-add').addEventListener('click', openAdd);
$('close-add').addEventListener('click', closeModal);
$('cancel-add').addEventListener('click', closeModal);
$('close-detail').addEventListener('click', () => { selectedId = null; $('detail').classList.add('hidden'); });
$('modal').addEventListener('click', event => { if (event.target === $('modal')) closeModal(); });
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeModal(); });
$('add-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.target;
  const data = Object.fromEntries(new FormData(form));
  data.interval = Number(data.interval);
  $('form-error').textContent = '';
  try {
    const wasEditing = editingId !== null;
    await api(wasEditing ? `/api/monitors/${editingId}` : '/api/monitors', { method: wasEditing ? 'PATCH' : 'POST', body: JSON.stringify(data) });
    form.reset();
    closeModal();
    await refresh();
    notice(wasEditing ? '监控已更新' : '监控已创建，首次检查即将开始');
  } catch (error) { $('form-error').textContent = error.message; }
});
refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 10000);
