(function () {
  'use strict';

  const scanner = window.SupplyScanner;
  const sample = {
    name: 'checkout-service', sample: true,
    packages: [
      ['lodash', '4.17.20', true], ['minimist', '1.2.5', true], ['axios', '0.21.1', true],
      ['react', '18.2.0', true], ['express', '4.18.2', true], ['chalk', '5.3.0', false],
      ['debug', '4.3.4', false], ['semver', '7.5.4', false], ['glob', '8.1.0', false], ['ws', '8.13.0', false],
    ].map(([name, version, direct]) => ({ name, version, ecosystem: 'npm', direct, dev: false, license: null })),
  };
  const state = { project: sample, findings: [], scanState: 'unscanned', scannedAt: null, view: 'overview', error: '', progress: '' };
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  }

  function icon(name) { return `<i data-lucide="${name}"></i>`; }
  function refreshIcons() { window.lucide?.createIcons(); }
  function count(severity) { return state.findings.filter(item => item.severity === severity).length; }
  function badge(severity) { return `<span class="severity severity-${severity.toLowerCase()}"><span class="severity-dot"></span>${severity}</span>`; }

  function setView(view) {
    state.view = view;
    $$('.view').forEach(element => element.classList.toggle('active', element.id === `${view}-view`));
    $$('.side-link').forEach(element => element.classList.toggle('active', element.dataset.view === view));
    const headings = { overview: ['Supply chain overview', 'Track the packages in your build and the advisories that matter.'], findings: ['Vulnerability findings', 'Review affected packages and the advisories behind each result.'], inventory: ['Package inventory', 'A complete view of the components in this project.'], sbom: ['Bill of materials', 'Export a portable record of your software components.'] };
    $('#page-title').textContent = headings[view][0];
    $('#page-subtitle').textContent = headings[view][1];
    $('#breadcrumb-view').textContent = view.toUpperCase();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function emptyState(iconName, title, description) {
    return `<div class="empty-state">${icon(iconName)}<h3>${title}</h3><p>${description}</p></div>`;
  }

  function renderMetrics() {
    const total = state.project.packages.length;
    const scanned = state.scanState === 'complete';
    const cards = [
      { label: 'TOTAL COMPONENTS', value: total, icon: 'boxes', detail: 'Unique package versions', accent: 'neutral' },
      { label: 'CRITICAL + HIGH', value: scanned ? count('CRITICAL') + count('HIGH') : '—', icon: 'shield-alert', detail: scanned ? 'Prioritize these findings' : 'Awaiting scan', accent: 'red' },
      { label: 'KNOWN ADVISORIES', value: scanned ? state.findings.length : '—', icon: 'scan-search', detail: scanned ? 'Affected package matches' : 'Awaiting scan', accent: 'yellow' },
      { label: 'DIRECT PACKAGES', value: state.project.packages.filter(item => item.direct).length, icon: 'git-branch', detail: 'Declared at the root', accent: 'green' },
    ];
    $('#metrics').innerHTML = cards.map(card => `<div class="metric metric-${card.accent}"><div class="metric-top"><span>${card.label}</span>${icon(card.icon)}</div><strong>${card.value}</strong><p>${card.detail}</p></div>`).join('');
  }

  function renderOverview() {
    $('#project-name').textContent = state.project.name;
    $('#project-meta').textContent = `${state.project.packages.length} components  ·  ${[...new Set(state.project.packages.map(item => item.ecosystem))].join(' + ') || 'No supported packages'}`;
    $('#project-tag').textContent = state.project.sample ? 'SAMPLE INVENTORY' : 'IMPORTED FILE';
    $('#project-tag').classList.toggle('tag-imported', !state.project.sample);
    renderMetrics();
    const priority = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
    const top = [...state.findings].sort((a, b) => priority[a.severity] - priority[b.severity]).slice(0, 4);
    $('#overview-findings').innerHTML = state.scanState === 'complete'
      ? top.length ? `<div class="top-findings">${top.map((item, index) => `<button class="top-finding" data-finding="${state.findings.indexOf(item)}"><span class="finding-rank">${String(index + 1).padStart(2, '0')}</span><span class="top-finding-info"><strong>${escapeHtml(item.package.name)}</strong><small>${escapeHtml(item.id)} · v${escapeHtml(item.package.version)}</small></span>${badge(item.severity)}${icon('arrow-up-right')}</button>`).join('')}</div>` : emptyState('shield-check', 'No known advisories', 'OSV returned no matches for the imported package versions.')
      : emptyState('scan-search', state.scanState === 'scanning' ? 'Scanning packages' : 'No scan results yet', state.scanState === 'scanning' ? escapeHtml(state.progress) : 'Run an OSV scan to check this inventory.');

    const direct = state.project.packages.filter(item => item.direct).length;
    const dev = state.project.packages.filter(item => item.dev).length;
    const transitive = state.project.packages.length - direct;
    const total = state.project.packages.length || 1;
    $('#composition').innerHTML = `<div class="composition-total"><strong>${state.project.packages.length}</strong><span>IDENTIFIED COMPONENTS</span></div><div class="composition-bar" aria-label="${direct} direct and ${transitive} transitive packages"><span style="width:${100 * direct / total}%"></span></div><div class="legend-row"><div><span class="legend-dot direct-dot"></span>Direct dependencies</div><strong>${direct}</strong></div><div class="legend-row"><div><span class="legend-dot transitive-dot"></span>Transitive dependencies</div><strong>${transitive}</strong></div><div class="legend-row"><div><span class="legend-dot dev-dot"></span>Dev-only packages</div><strong>${dev}</strong></div><p class="composition-note">Dependency depth is inferred from the imported manifest when available.</p>`;
  }

  function renderFindings() {
    const query = $('#finding-search').value.trim().toLowerCase();
    const severity = $('#severity-filter').value;
    const rows = state.findings.filter(item => (severity === 'ALL' || item.severity === severity) && `${item.id} ${item.package.name} ${item.summary} ${item.aliases.join(' ')}`.toLowerCase().includes(query));
    $('#findings-heading').textContent = `Findings ${state.scanState === 'complete' ? `(${state.findings.length})` : ''}`;
    if (state.scanState !== 'complete') {
      $('#findings-table').innerHTML = emptyState('scan-search', state.scanState === 'scanning' ? 'Scan in progress' : 'No scan results yet', state.scanState === 'failed' ? 'The last OSV request failed. Retry the scan to see results.' : 'Run an OSV scan to check the inventory for known vulnerabilities.');
      return;
    }
    if (!rows.length) {
      $('#findings-table').innerHTML = emptyState('list-filter', state.findings.length ? 'No matching findings' : 'No known advisories', state.findings.length ? 'Try another search or severity filter.' : 'OSV returned no matches for these package versions.');
      return;
    }
    $('#findings-table').innerHTML = `<table><thead><tr><th>ADVISORY</th><th>PACKAGE</th><th>SEVERITY</th><th>FIX AVAILABLE</th><th></th></tr></thead><tbody>${rows.map(item => `<tr data-finding="${state.findings.indexOf(item)}" tabindex="0" role="button" aria-label="View advisory ${escapeHtml(item.id)}"><td class="advisory-cell"><strong>${escapeHtml(item.id)}</strong><span>${escapeHtml(item.summary)}</span></td><td><strong>${escapeHtml(item.package.name)}</strong><small>v${escapeHtml(item.package.version)}</small></td><td>${badge(item.severity)}</td><td>${item.fixed.length ? escapeHtml(item.fixed.join(', ')) : '<span class="muted">Not specified</span>'}</td><td>${icon('arrow-up-right')}</td></tr>`).join('')}</tbody></table>`;
    refreshIcons();
  }

  function renderInventory() {
    const query = $('#inventory-search').value.trim().toLowerCase();
    const rows = state.project.packages.filter(item => `${item.name} ${item.version} ${item.ecosystem}`.toLowerCase().includes(query));
    $('#inventory-heading').textContent = `Package inventory (${state.project.packages.length})`;
    $('#inventory-table').innerHTML = rows.length
      ? `<table><thead><tr><th>COMPONENT</th><th>VERSION</th><th>ECOSYSTEM</th><th>RELATION</th><th>ADVISORIES</th></tr></thead><tbody>${rows.map(item => { const matches = state.findings.filter(finding => finding.package === item).length; return `<tr><td class="package-cell"><span class="pkg-icon">${escapeHtml(item.name.slice(0, 1).toUpperCase())}</span><strong>${escapeHtml(item.name)}</strong></td><td class="mono">${escapeHtml(item.version)}</td><td>${escapeHtml(item.ecosystem)}</td><td><span class="relation">${item.direct ? 'DIRECT' : 'TRANSITIVE'}</span></td><td>${state.scanState === 'complete' ? matches ? `<strong class="risk-count">${matches} found</strong>` : '<span class="muted">None found</span>' : '<span class="muted">Not scanned</span>'}</td></tr>`; }).join('')}</tbody></table>`
      : emptyState('search-x', 'No packages found', 'Try another search, or import a different manifest.');
    refreshIcons();
  }

  function render() {
    const scanButton = $('#scan-button');
    scanButton.disabled = state.scanState === 'scanning' || !state.project.packages.length;
    scanButton.querySelector('span').textContent = state.scanState === 'scanning' ? 'Scanning...' : state.scanState === 'complete' ? 'Scan again' : 'Run OSV scan';
    $('#top-status').innerHTML = `<span class="status-pip"></span> ${state.scanState === 'complete' ? 'SCAN COMPLETE' : state.scanState === 'scanning' ? 'SCANNING' : state.scanState === 'failed' ? 'SCAN FAILED' : 'NOT SCANNED'}`;
    $('#top-status').className = `top-status status-${state.scanState}`;
    $('#nav-finding-count').textContent = state.scanState === 'complete' ? state.findings.length : '0';
    $('#notice').className = `notice ${state.error ? 'notice-error' : state.progress ? 'notice-progress' : ''}`;
    $('#notice').textContent = state.error || state.progress;
    renderOverview(); renderFindings(); renderInventory();
    $('#sbom-project').textContent = state.project.name;
    $('#sbom-count').textContent = state.project.packages.length;
    $('#sbom-ecosystems').textContent = [...new Set(state.project.packages.map(item => item.ecosystem))].join(', ') || 'None';
    $('#download-report').disabled = state.scanState !== 'complete';
    refreshIcons();
  }

  function showFinding(index) {
    const item = state.findings[index];
    if (!item) return;
    $('#detail-content').innerHTML = `<div class="drawer-top"><span class="label-mini">ADVISORY DETAIL</span><button id="close-detail" class="icon-button" aria-label="Close advisory details">${icon('x')}</button></div><div class="drawer-body">${badge(item.severity)}<h2>${escapeHtml(item.id)}</h2><p class="drawer-summary">${escapeHtml(item.summary)}</p><div class="drawer-facts"><div><span>AFFECTED COMPONENT</span><strong>${escapeHtml(item.package.name)} <span class="muted">v${escapeHtml(item.package.version)}</span></strong></div><div><span>ECOSYSTEM</span><strong>${escapeHtml(item.package.ecosystem)}</strong></div><div><span>FIXED VERSION${item.fixed.length > 1 ? 'S' : ''}</span><strong>${item.fixed.length ? escapeHtml(item.fixed.join(', ')) : 'Not specified by OSV'}</strong></div>${item.published ? `<div><span>PUBLISHED</span><strong>${escapeHtml(item.published.slice(0, 10))}</strong></div>` : ''}</div>${item.aliases.length ? `<div class="drawer-section"><h3>Other identifiers</h3><p>${escapeHtml(item.aliases.join(', '))}</p></div>` : ''}${item.details ? `<div class="drawer-section"><h3>Description</h3><p>${escapeHtml(item.details)}</p></div>` : ''}<a class="button button-primary drawer-link" href="${item.url}" target="_blank" rel="noopener noreferrer">View on OSV ${icon('arrow-up-right')}</a></div>`;
    $('#detail-backdrop').hidden = false;
    $('#detail-panel').hidden = false;
    document.body.classList.add('drawer-open');
    refreshIcons();
    $('#close-detail').focus();
  }

  function closeFinding() {
    $('#detail-backdrop').hidden = true;
    $('#detail-panel').hidden = true;
    document.body.classList.remove('drawer-open');
  }

  function download(name, data) {
    const link = document.createElement('a');
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function filename(suffix) { return `${state.project.name.toLowerCase().replace(/[^a-z0-9._-]+/g, '-') || 'project'}-${suffix}.json`; }

  async function importFile(file) {
    if (!file) return;
    try {
      const project = scanner.parseDocument(await file.text());
      if (!project.packages.length) throw new Error('No supported npm or PyPI components with versions were found.');
      state.project = { ...project, sample: false };
      state.findings = []; state.scanState = 'unscanned'; state.scannedAt = null; state.error = ''; state.progress = '';
      $('#finding-search').value = ''; $('#inventory-search').value = ''; $('#severity-filter').value = 'ALL';
      closeFinding(); setView('overview'); render();
    } catch (error) {
      state.error = `Could not import ${file.name}: ${error.message}`;
      state.progress = ''; render();
    }
    $('#file-input').value = '';
  }

  async function startScan() {
    if (state.scanState === 'scanning' || !state.project.packages.length) return;
    state.scanState = 'scanning'; state.error = ''; state.progress = 'Connecting to OSV...'; state.findings = []; render();
    const project = state.project;
    try {
      const findings = await scanner.scan(project, ({ checked, total }) => { state.progress = `Checking ${checked} of ${total} packages with OSV...`; render(); });
      if (state.project !== project) return;
      state.findings = findings; state.scanState = 'complete'; state.scannedAt = new Date().toISOString(); state.progress = ''; render();
    } catch (error) {
      if (state.project !== project) return;
      state.scanState = 'failed'; state.findings = []; state.progress = '';
      state.error = `Scan incomplete: ${error.message} Check your connection and retry. No clean result is reported.`;
      render();
    }
  }

  $$('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  $('#open-import').addEventListener('click', () => $('#file-input').click());
  $('#banner-import').addEventListener('click', () => $('#file-input').click());
  $('#file-input').addEventListener('change', event => importFile(event.target.files[0]));
  $('#scan-button').addEventListener('click', startScan);
  $('#finding-search').addEventListener('input', renderFindings);
  $('#severity-filter').addEventListener('change', renderFindings);
  $('#inventory-search').addEventListener('input', renderInventory);
  $('#download-bom').addEventListener('click', () => download(filename('sbom'), scanner.makeBom(state.project)));
  $('#download-report').addEventListener('click', () => { if (state.scanState === 'complete') download(filename('osv-report'), { project: state.project.name, scannedAt: state.scannedAt, source: 'OSV', packagesChecked: state.project.packages.length, findings: state.findings }); });
  document.addEventListener('click', event => { const target = event.target.closest('[data-finding]'); if (target) showFinding(Number(target.dataset.finding)); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeFinding(); if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('tr[data-finding]')) { event.preventDefault(); showFinding(Number(event.target.dataset.finding)); } });
  $('#detail-backdrop').addEventListener('click', closeFinding);
  let dragDepth = 0;
  window.addEventListener('dragenter', event => { if (!event.dataTransfer?.types.includes('Files')) return; event.preventDefault(); dragDepth++; $('#drop-overlay').classList.add('visible'); });
  window.addEventListener('dragover', event => { if (event.dataTransfer?.types.includes('Files')) event.preventDefault(); });
  window.addEventListener('dragleave', event => { if (!event.dataTransfer?.types.includes('Files')) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $('#drop-overlay').classList.remove('visible'); });
  window.addEventListener('drop', event => { event.preventDefault(); dragDepth = 0; $('#drop-overlay').classList.remove('visible'); importFile(event.dataTransfer?.files[0]); });
  render();
})();