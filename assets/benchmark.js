/* Published benchmark results; all statistics retain their original seed values. */
(() => {
  const $ = id => document.getElementById(id);
  const metricNames = {att: 'ATT (s)', awt: 'AWT (s)', aql: 'AQL'};
  const metricNotes = {
    att: 'ATT includes completed trips and elapsed travel time for vehicles still in the network.',
    awt: 'AWT is the mean accumulated stopping time of observed vehicles.',
    aql: 'AQL is the mean network queue per simulation sample.'
  };
  const fmt = value => value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const number = entry => entry ? `<span class="bench-number">${fmt(entry.mean)} <small>± ${fmt(entry.sd)}</small></span>` : '<span class="bench-missing">—</span>';
  let data;
  let order = {key: 'cojevlight', direction: 1};
  const group = (model, flow, mode) => data.aggregates.find(g => g.model === model && g.flow === flow && g.mode === mode);
  const entry = (model, flow, mode, metric) => {
    const aggregate = group(model, flow, mode);
    return aggregate ? aggregate.metrics[metric] : null;
  };
  function render() {
    if (!data) return;
    const flow = $('bench-flow').value, metric = $('bench-metric').value;
    const rows = data.models.filter(m => m.kind === 'native' || m.kind === 'api' || m.kind === 'visual').map(m => {
      const local = entry(m.id, flow, 'jevlight', metric);
      const co = entry(m.id, flow, 'cojevlight', metric);
      const vla = entry(m.id, flow, 'vlalight', metric);
      const delta = local && co && local.mean > 0 ? (co.mean - local.mean) / local.mean * 100 : null;
      return {m, local, co, vla, delta};
    });
    const sortValue = r => {
      if (order.key === 'delta') return r.delta;
      const value = r[order.key];
      return value ? value.mean : null;
    };
    rows.sort((a, b) => {
      if (order.key === 'model') return order.direction * a.m.name.localeCompare(b.m.name);
      const av = sortValue(a), bv = sortValue(b);
      return av === null && bv === null ? a.m.name.localeCompare(b.m.name) : av === null ? 1 : bv === null ? -1 : order.direction * (av - bv) || a.m.name.localeCompare(b.m.name);
    });
    $('bench-table').querySelector('tbody').innerHTML = rows.map(r => `<tr data-model="${r.m.id}">
      <td class="bench-model">${r.m.name}</td>
      <td>${number(r.local)}</td>
      <td>${number(r.co)}</td>
      <td>${number(r.vla)}</td>
      <td class="bench-delta ${r.delta !== null && r.delta < 0 ? 'improved' : r.delta > 0 ? 'increased' : ''}">${r.delta === null ? '—' : (r.delta < 0 ? '−' : r.delta > 0 ? '+' : '') + Math.abs(r.delta).toFixed(1) + '%'}</td>
    </tr>`).join('');
    document.querySelectorAll('#bench-table [data-sort]').forEach(button => {
      const active = button.dataset.sort === order.key;
      const label = {model: 'Model', jevlight: 'JevLight', cojevlight: 'CoJevLight', vlalight: 'VLALight', delta: 'Co change'}[button.dataset.sort];
      button.closest('th').setAttribute('aria-sort', active ? order.direction === 1 ? 'ascending' : 'descending' : 'none');
      button.querySelector('.sort-arrow').textContent = active ? order.direction === 1 ? '↑' : '↓' : '↕';
      button.setAttribute('aria-label', `${label}: sort ${active && order.direction === 1 ? 'descending' : 'ascending'}`);
    });
    const selected = data.flows.find(f => f.id === flow);
    $('bench-caption').textContent = `${selected.name}: ${metricNames[metric]}, mean and sample standard deviation across three seeds`;
    $('bench-context').textContent = `${selected.name} · ${selected.intersections} intersections · ${metricNames[metric]} · VLALight rows are rendered-camera agents`;
    $('bench-metric-note').textContent = metricNotes[metric];
    const refValue = (id, mode) => number(entry(id, flow, mode, metric));
    $('bench-references').innerHTML = `<article class="bench-reference"><h3>Max Pressure</h3><div class="ref-values"><div><span>${metricNames[metric]}</span>${refValue('maxpressure', 'maxpressure')}</div></div></article>`;
  }
  document.querySelectorAll('#bench-table [data-sort]').forEach(button => {
    button.addEventListener('click', () => {
      const key = button.dataset.sort;
      order = {key, direction: order.key === key ? -order.direction : 1};
      render();
    });
  });
  fetch('assets/benchmark.json').then(response => {
    if (!response.ok) throw new Error('Benchmark data could not be loaded.');
    return response.json();
  }).then(value => {
    data = value;
    $('bench-flow').innerHTML = data.flows.map(f => `<option value="${f.id}">${f.name}</option>`).join('');
    $('bench-flow').disabled = false;
    for (const id of ['bench-flow', 'bench-metric']) $(id).addEventListener('change', render);
    render();
  }).catch(error => {
    $('bench-context').textContent = 'Results are unavailable. Please reload the page.';
    $('bench-table').querySelector('tbody').innerHTML = '<tr><td colspan="5" class="bench-status">Results could not be loaded.</td></tr>';
    console.error(error);
  });
})();
