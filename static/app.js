const $ = (id) => document.getElementById(id);
let monitors = [];
let selectedId = null;
let editingId = null;
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
  selectedId = id;
  const [data, stats] = await Promise.all([
    api(`/api/monitors/${id}/history`),
    api(`/api/monitors/${id}/statistics`),
  ]);
  $('detail-title').textContent = `${monitor.name} · 检查记录`;
  const body = $('detail-body');
  body.replaceChildren();
  const inner = element('div', 'detail-inner');
  const meta = element('div', 'detail-meta');
  meta.append(element('span', '', monitor.url), element('span', '', `检查间隔 ${monitor.interval} 秒`), element('span', '', `上次检查 ${formatTime(monitor.last_checked)}`));
  if (monitor.paused) meta.append(element('span', 'paused-note', '自动检查已暂停'));
  inner.append(meta);
  const metrics = element('div', 'detail-metrics');
  metrics.append(element('div', '', `近 24 小时检查可用率：${stats.availability_24h === null ? '暂无数据' : `${stats.availability_24h}%`}`), element('div', '', `检查次数：${stats.checks_24h}`));
  inner.append(metrics, element('p', 'metric-note', '按检查次数计算；不代表持续在线时长。'), element('p', 'history-title', '最近检查状态'));
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
