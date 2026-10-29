/* Composite index charts: the per-mode ranking and the score-vs-compute plane
   with its Pareto frontier. Renders plain SVG from window.JEV_COMPOSITE, so
   the page also works from file://. */
(() => {
  const data = window.JEV_COMPOSITE;
  if (!data) return;

  const NS = 'http://www.w3.org/2000/svg';
  const section = document.getElementById('index');
  if (!section) return;
  let barHost = null;
  let scatterHost = null;
  let legend = null;
  const tip = document.getElementById('ix-tooltip');

  function refreshHosts() {
    barHost = document.getElementById('ix-bar');
    scatterHost = document.getElementById('ix-scatter');
    legend = document.getElementById('ix-legend');
  }

  const state = { barMode: 'cojevlight', scatterMode: 'both', active: null };
  const registry = new Map();          // config id -> [elements]
  const fmt = (v, digits = 1) =>
    v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const int = v => (v == null ? '—' : v.toLocaleString('en-US'));
  const modeLabel = id => (id === 'cojevlight' ? 'CoJevLight' : 'JevLight');

  function el(tag, attrs = {}, text) {
    const node = document.createElementNS(NS, tag);
    for (const key in attrs) if (attrs[key] != null) node.setAttribute(key, attrs[key]);
    if (text != null) node.textContent = text;
    return node;
  }
  function html(tag, attrs = {}, text) {
    const node = document.createElement(tag);
    for (const key in attrs) if (attrs[key] != null) node.setAttribute(key, attrs[key]);
    if (text != null) node.textContent = text;
    return node;
  }
  function svgRoot(width, height, cls) {
    return el('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', class: cls });
  }
  function register(id, node) {
    if (!registry.has(id)) registry.set(id, []);
    registry.get(id).push(node);
  }
  function setActive(id) {
    if (state.active === id) return;
    state.active = id;
    for (const [key, nodes] of registry) {
      const on = key === id;
      for (const node of nodes) node.classList.toggle('is-active', on);
      if (on) for (const node of nodes) node.parentNode?.appendChild(node);
    }
    for (const node of document.querySelectorAll('[data-config]')) {
      node.classList.toggle('dim', id != null && node.dataset.config !== id);
    }
  }

  // ---------------------------------------------------------------- tooltip
  function showTip(event, markup) {
    tip.innerHTML = markup;
    tip.classList.add('on');
    moveTip(event);
  }
  function moveTip(event) {
    const pad = 14;
    const rect = tip.getBoundingClientRect();
    let x = event.clientX + pad;
    let y = event.clientY + pad;
    if (x + rect.width > window.innerWidth - 8) x = event.clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight - 8) y = event.clientY - rect.height - pad;
    tip.style.transform = `translate(${Math.max(8, x)}px, ${Math.max(8, y)}px)`;
  }
  function hideTip() { tip.classList.remove('on'); }

  function tipFor(config) {
    const cost = config.cost;
    const rows = [
      `<div><dt>Index</dt><dd>${fmt(config.score)}</dd></div>`,
      `<div><dt>Rank</dt><dd>${config.rank} / ${data.configs.length}</dd></div>`
    ];
    if (config.hosted) {
      rows.push('<div><dt>Compute</dt><dd>hosted API</dd></div>');
    } else if (cost.gpu_seconds) {
      rows.push(`<div><dt>Compute / task</dt><dd>${int(cost.gpu_seconds)} GPU·s</dd></div>`);
      rows.push(`<div><dt>Answering / task</dt><dd>${int(cost.serving_seconds)} s</dd></div>`);
      if (cost.gpus) rows.push(`<div><dt>GPUs held</dt><dd>${cost.gpus}</dd></div>`);
    }
    if (cost.tokens_per_decision) {
      rows.push(`<div><dt>Tokens / decision</dt><dd>${int(cost.tokens_per_decision)}</dd></div>`);
    }
    return `<b>${config.name}</b><span class="ix-tip-mode">${config.family_label} · `
      + `${modeLabel(config.mode)}</span><dl>${rows.join('')}</dl>`
      + (config.pareto ? '<span class="ix-tip-flag">cost Pareto frontier</span>' : '');
  }

  // ------------------------------------------------------------------- bars
  const BAR = { w: 1240, row: 31, top: 40, label: 300, bar: 720, value: 96, right: 16, bottom: 62 };

  function renderBars() {
    if (!barHost) return;
    barHost.innerHTML = '';
    const configs = data.configs.filter(c => c.mode === state.barMode);
    const height = BAR.top + configs.length * BAR.row + BAR.bottom;
    const svg = svgRoot(BAR.w, height, 'ix-svg ix-svg-bars');
    const x0 = BAR.label;
    const x1 = x0 + BAR.bar;
    const x = v => x0 + (v / 100) * BAR.bar;
    const valueX = x1 + 16 + BAR.value - 24;

    for (let v = 0; v <= 100; v += 20) {
      const gx = x(v);
      svg.appendChild(el('line', {
        x1: gx, x2: gx, y1: BAR.top - 14, y2: height - BAR.bottom + 6,
        class: v === 0 ? 'ix-axis' : 'ix-grid'
      }));
      svg.appendChild(el('text', {
        x: gx, y: height - BAR.bottom + 22, class: 'ix-tick', 'text-anchor': 'middle'
      }, v));
    }
    svg.appendChild(el('text', {
      x: x(0), y: BAR.top - 22, class: 'ix-panel-axis-label', 'text-anchor': 'start'
    }, 'COMPOSITE INDEX'));
    svg.appendChild(el('text', {
      x: valueX, y: BAR.top - 22, class: 'ix-panel-axis-label', 'text-anchor': 'end'
    }, 'SCORE'));

    const barH = 13;
    configs.forEach((config, index) => {
      const cy = BAR.top + index * BAR.row + BAR.row / 2;
      const width = Math.max(2, x(config.score) - x0);
      const group = el('g', { class: 'ix-bar-group', 'data-config': config.id, tabindex: '0' });

      group.appendChild(el('rect', {
        x: x0, y: cy - barH / 2, width: BAR.bar, height: barH, rx: 3, class: 'ix-bar-track'
      }));
      group.appendChild(el('text', {
        x: 22, y: cy + 4, class: 'ix-bar-rank', 'text-anchor': 'start'
      }, String(index + 1).padStart(2, '0')));
      group.appendChild(el('text', {
        x: x0 - 16, y: cy + 4.2, class: 'ix-bar-label', 'text-anchor': 'end'
      }, config.name));
      group.appendChild(el('rect', {
        x: x0, y: cy - barH / 2, width, height: barH, rx: 3,
        fill: config.color, class: 'ix-bar'
      }));
      group.appendChild(el('text', {
        x: valueX, y: cy + 4.2, class: 'ix-bar-value', 'text-anchor': 'end'
      }, fmt(config.score)));

      group.addEventListener('mouseenter', event => { setActive(config.id); showTip(event, tipFor(config)); });
      group.addEventListener('mousemove', moveTip);
      group.addEventListener('mouseleave', () => { setActive(null); hideTip(); });
      group.addEventListener('focus', () => setActive(config.id));
      group.addEventListener('blur', () => setActive(null));
      svg.appendChild(group);
      register(config.id, group);
    });

    if (data.baseline) {
      const bx = x(data.baseline.score);
      svg.appendChild(el('line', {
        x1: bx, x2: bx, y1: BAR.top - 14, y2: height - BAR.bottom + 6, class: 'ix-baseline'
      }));
      svg.appendChild(el('text', {
        x: bx, y: height - BAR.bottom + 44, class: 'ix-baseline-label', 'text-anchor': 'middle'
      }, `MaxPressure baseline ${fmt(data.baseline.score)}`));
    }
    barHost.appendChild(svg);
  }

  // ---------------------------------------------------------------- scatter
  const SC = { w: 1240, h: 570, l: 66, r: 30, t: 34, b: 64 };

  function frontier(points) {
    const ordered = [...points].sort((a, b) => a.cost.gpu_seconds - b.cost.gpu_seconds || b.score - a.score);
    const out = [];
    let best = -Infinity;
    for (const point of ordered) {
      if (point.score > best) { out.push(point); best = point.score; }
    }
    return out;
  }

  function ticksFor(lo, hi) {
    const candidates = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
    return candidates.filter(v => v >= lo && v <= hi);
  }

  function scatterPoints() {
    return data.configs.filter(c => !c.hosted && c.cost.gpu_seconds
      && (state.scatterMode === 'both' || c.mode === state.scatterMode));
  }

  function pointLabel(config) {
    return state.scatterMode === 'both' && config.mode === 'cojevlight'
      ? `${config.name} (Co)` : config.name;
  }

  function renderScatter() {
    if (!scatterHost) return;
    scatterHost.innerHTML = '';
    const points = scatterPoints();
    const both = state.scatterMode === 'both';
    const outer = html('div', { class: 'ix-plot-wrap' });
    const svg = svgRoot(SC.w, SC.h, 'ix-svg ix-svg-scatter');
    const innerW = SC.w - SC.l - SC.r;
    const innerH = SC.h - SC.t - SC.b;
    const y = v => SC.t + (1 - v / 100) * innerH;

    const costs = points.map(p => p.cost.gpu_seconds);
    const xMin = Math.min(...costs) / 1.35;
    const xMax = Math.max(...costs) * 1.28;
    const x = v => SC.l + (Math.log10(v) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin)) * innerW;

    for (let v = 0; v <= 100; v += 20) {
      svg.appendChild(el('line', { x1: SC.l, x2: SC.w - SC.r, y1: y(v), y2: y(v), class: v === 0 ? 'ix-axis' : 'ix-grid' }));
      svg.appendChild(el('text', { x: SC.l - 14, y: y(v) + 4, class: 'ix-tick', 'text-anchor': 'end' }, v));
    }
    for (const tick of ticksFor(xMin, xMax)) {
      const gx = x(tick);
      const major = String(tick)[0] === '1';
      svg.appendChild(el('line', {
        x1: gx, x2: gx, y1: SC.t, y2: SC.t + innerH,
        class: major ? 'ix-grid' : 'ix-grid ix-grid-faint'
      }));
      svg.appendChild(el('text', {
        x: gx, y: SC.h - SC.b + 25, class: 'ix-tick', 'text-anchor': 'middle'
      }, tick >= 1000 ? `${tick / 1000}k` : tick));
    }
    svg.appendChild(el('line', { x1: SC.l, x2: SC.l, y1: SC.t, y2: SC.t + innerH, class: 'ix-axis' }));

    svg.appendChild(el('text', {
      x: 20, y: SC.t + innerH / 2, class: 'ix-axis-title',
      transform: `rotate(-90 20 ${SC.t + innerH / 2})`, 'text-anchor': 'middle'
    }, 'Composite index'));
    svg.appendChild(el('text', {
      x: SC.l + innerW / 2, y: SC.h - 12, class: 'ix-axis-title', 'text-anchor': 'middle'
    }, 'Compute per task · GPU-seconds, log scale'));

    const sortedCost = [...costs].sort((a, b) => a - b);
    const sortedScore = points.map(p => p.score).sort((a, b) => a - b);
    const medianCost = sortedCost[Math.floor(sortedCost.length / 2)];
    const medianScore = sortedScore[Math.floor(sortedScore.length / 2)];
    svg.appendChild(el('rect', {
      x: SC.l, y: y(100), width: x(medianCost) - SC.l, height: y(medianScore) - y(100),
      class: 'ix-quadrant'
    }));
    svg.appendChild(el('text', { x: SC.l + 14, y: y(100) + 19, class: 'ix-quadrant-label' }, 'cheaper · better'));
    svg.appendChild(el('line', {
      x1: x(medianCost), x2: x(medianCost), y1: SC.t, y2: SC.t + innerH, class: 'ix-quadrant-edge'
    }));
    svg.appendChild(el('line', {
      x1: SC.l, x2: SC.w - SC.r, y1: y(medianScore), y2: y(medianScore), class: 'ix-quadrant-edge'
    }));

    const front = frontier(points);
    const frontIds = new Set(front.map(p => p.id));
    if (front.length > 1) {
      const d = front.map((p, i) => `${i ? 'L' : 'M'}${x(p.cost.gpu_seconds).toFixed(1)},${y(p.score).toFixed(1)}`).join(' ');
      svg.appendChild(el('path', { d, class: 'ix-frontier' }));
    }

    // Markers first, so labels can avoid them.
    for (const point of [...points].sort((a, b) => b.score - a.score)) {
      const px = x(point.cost.gpu_seconds);
      const py = y(point.score);
      const isFront = frontIds.has(point.id);
      const group = el('g', { class: 'ix-point-group', 'data-config': point.id, tabindex: '0' });
      if (isFront) group.appendChild(el('circle', { cx: px, cy: py, r: 12, class: 'ix-point-halo' }));
      if (both && point.mode === 'cojevlight') {
        group.appendChild(el('circle', {
          cx: px, cy: py, r: (isFront ? 7.2 : 5.2) + 3.2,
          fill: 'none', stroke: point.color, 'stroke-width': 1.2, opacity: 0.55
        }));
      }
      group.appendChild(el('circle', {
        cx: px, cy: py, r: isFront ? 7.2 : 5.2, fill: point.color, class: 'ix-point'
      }));
      group.addEventListener('mouseenter', event => { setActive(point.id); showTip(event, tipFor(point)); });
      group.addEventListener('mousemove', moveTip);
      group.addEventListener('mouseleave', () => { setActive(null); hideTip(); });
      group.addEventListener('focus', () => setActive(point.id));
      group.addEventListener('blur', () => setActive(null));
      svg.appendChild(group);
      register(point.id, group);
    }

    // Labels: frontier first, then the strongest. Slots are scored by overlap
    // with placed labels and other markers, so clusters push labels outwards.
    const priority = [...points].sort((a, b) => {
      const fa = frontIds.has(a.id) ? 0 : 1;
      const fb = frontIds.has(b.id) ? 0 : 1;
      return fa - fb || b.score - a.score;
    }).slice(0, both ? 11 : 9);
    const boxes = [];
    const markers = points.map(point => ({
      id: point.id,
      x1: x(point.cost.gpu_seconds) - 9, x2: x(point.cost.gpu_seconds) + 9,
      y1: y(point.score) - 9, y2: y(point.score) + 9
    }));
    const overlapArea = (a, b) => {
      const w = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
      const h = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
      return w > 0 && h > 0 ? w * h : 0;
    };
    function slotCost(box, ownId) {
      let penalty = 0;
      if (box.x1 < SC.l + 2) penalty += (SC.l + 2 - box.x1) * 30;
      if (box.x2 > SC.w - SC.r - 2) penalty += (box.x2 - (SC.w - SC.r - 2)) * 30;
      if (box.y1 < SC.t + 2) penalty += (SC.t + 2 - box.y1) * 30;
      if (box.y2 > SC.t + innerH - 2) penalty += (box.y2 - (SC.t + innerH - 2)) * 30;
      for (const other of boxes) penalty += overlapArea(box, other) * 4;
      for (const marker of markers) {
        if (marker.id !== ownId) penalty += overlapArea(box, marker) * 3;
      }
      return penalty;
    }

    for (const point of priority) {
      const px = x(point.cost.gpu_seconds);
      const py = y(point.score);
      const text = pointLabel(point);
      const w = text.length * 6.5 + 8;
      const h = 14;
      const slots = [];
      for (const gap of [15, 28, 42, 58]) {
        for (const dir of [1, -1]) {
          slots.push({
            x: px + dir * gap, y: py + 4, anchor: dir > 0 ? 'start' : 'end',
            box: { x1: px + dir * gap - (dir > 0 ? 2 : w), x2: px + dir * gap + (dir > 0 ? w : 2), y1: py - 9, y2: py + 5 }
          });
        }
      }
      for (const dy of [-15, 19, -29, 33, -43, 47]) {
        slots.push({
          x: px, y: py + dy, anchor: 'middle',
          box: { x1: px - w / 2, x2: px + w / 2, y1: py + dy - h, y2: py + dy + 1 }
        });
      }
      let best = slots[0];
      let bestCost = Infinity;
      for (const slot of slots) {
        const value = slotCost(slot.box, point.id);
        if (value < bestCost) { bestCost = value; best = slot; }
        if (value === 0) break;
      }
      if (bestCost > 400 && !frontIds.has(point.id)) continue;
      boxes.push(best.box);
      const lx = best.x;
      const ly = best.y;
      if (Math.abs(lx - px) > 12 || Math.abs(ly - py) > 10) {
        svg.appendChild(el('line', {
          x1: px + (lx > px + 12 ? 8 : lx < px - 12 ? -8 : 0),
          y1: py + (ly > py + 10 ? 7 : ly < py - 10 ? -7 : 0),
          x2: lx + (best.anchor === 'start' ? -2 : best.anchor === 'end' ? 2 : 0),
          y2: ly - 4, class: 'ix-label-leader'
        }));
      }
      const bgX = best.anchor === 'start' ? lx - 3 : best.anchor === 'end' ? lx - w + 3 : lx - w / 2;
      svg.appendChild(el('rect', {
        x: bgX, y: ly - 11, width: w - 6, height: 14, rx: 3, class: 'ix-label-bg'
      }));
      svg.appendChild(el('text', {
        x: lx, y: ly, class: 'ix-point-label', 'text-anchor': best.anchor
      }, text));
    }

    outer.appendChild(svg);

    const notes = [];
    if (both) {
      notes.push('Both modes are shown: a plain name is JevLight, “(Co)” is CoJevLight — the same model under '
        + 'the two observation scopes, drawn with a second ring.');
    }
    const hosted = data.configs.filter(c => c.hosted);
    if (hosted.length) {
      notes.push(`${hosted.map(c => c.name).join(', ')} ${hosted.length > 1 ? 'are hosted APIs' : 'is a hosted API'}: `
        + 'compute is not ours to measure, so it is ranked but not placed on this plane.');
    }
    const top = [...points].sort((a, b) => b.score - a.score)[0];
    if (top) {
      notes.push(`Hollow rings mark the frontier; ${top.name}${both && top.mode === 'cojevlight' ? ' (Co)' : ''} `
        + `leads this view at ${fmt(top.score)}.`);
    }
    for (const text of notes) outer.appendChild(html('p', { class: 'ix-plot-note' }, text));
    scatterHost.appendChild(outer);
  }

  // ---------------------------------------------------------------- legend
  function renderLegend() {
    if (!legend) return;
    const families = new Map();
    for (const config of scatterPoints()) {
      if (!families.has(config.family)) families.set(config.family, config);
    }
    legend.innerHTML = [...families.values()].map(config =>
      `<span class="ix-legend-item"><i style="background:${config.color}"></i>${config.family_label}</span>`).join('');
  }

  // ----------------------------------------------------------------- method
  function fillPlaceholders() {
    const values = {
      cells: String(data.flows.length * data.metrics.length),
      scenes: String(data.flows.length),
      configurations: String(data.configs.length / data.modes.length),
      runs: int(data.source.telemetry_runs)
    };
    // Edit text nodes in place: rewriting section.innerHTML would drop the
    // .reveal observers bound by the page and leave the copy invisible.
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const filled = node.nodeValue.replace(/\{(\w+)\}/g, (match, key) =>
        Object.prototype.hasOwnProperty.call(values, key) ? values[key] : match);
      if (filled !== node.nodeValue) node.nodeValue = filled;
    }
    refreshHosts();
  }

  // ----------------------------------------------------------------- wiring
  function renderAll() {
    refreshHosts();
    syncToggles();
    registry.clear();
    renderBars();
    renderScatter();
    renderLegend();
    setActive(null);
  }

  // Delegated, because fillPlaceholders() rewrites the section's markup.
  section.addEventListener('click', event => {
    const button = event.target.closest('.ix-toggle button[data-mode]');
    if (!button || !section.contains(button)) return;
    const toggle = button.closest('.ix-toggle');
    const key = toggle.dataset.scope === 'scatter' ? 'scatterMode' : 'barMode';
    if (state[key] === button.dataset.mode) return;
    state[key] = button.dataset.mode;
    syncToggles();
    registry.clear();
    if (toggle.dataset.scope === 'scatter') { renderScatter(); renderLegend(); } else { renderBars(); }
    setActive(null);
  });

  function syncToggles() {
    for (const toggle of section.querySelectorAll('.ix-toggle')) {
      const key = toggle.dataset.scope === 'scatter' ? 'scatterMode' : 'barMode';
      for (const button of toggle.querySelectorAll('button[data-mode]')) {
        const on = button.dataset.mode === state[key];
        button.setAttribute('aria-pressed', String(on));
        button.classList.toggle('on', on);
      }
    }
  }

  fillPlaceholders();
  renderAll();
  window.addEventListener('resize', () => { if (tip && tip.classList.contains('on')) hideTip(); });
})();
