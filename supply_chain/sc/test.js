(async function () {
  const tests = [];
  function check(name, condition) { if (!condition) throw new Error(name); tests.push(`PASS ${name}`); }
  try {
    const lock = JSON.stringify({ name: 'checkout', packages: {
      '': { dependencies: { '@acme/core': '^1.0.0' }, devDependencies: { tooling: '^2.0.0' } },
      'node_modules/@acme/core': { version: '1.2.0', license: 'MIT' },
      'node_modules/tooling': { version: '2.1.0' },
      'node_modules/tooling/node_modules/@acme/core': { version: '1.2.0' },
    } });
    const project = SupplyScanner.parseDocument(lock);
    check('lockfile deduplicates nested scoped packages', project.packages.length === 2);
    check('lockfile preserves direct and dev flags', project.packages[0].name === '@acme/core' && project.packages[0].direct && project.packages[1].dev);
    let rejected = false;
    try { SupplyScanner.parseDocument('{}'); } catch (error) { rejected = /packages section/.test(error.message); }
    check('unsupported document is rejected', rejected);

    const bom = SupplyScanner.makeBom(project);
    check('export uses CycloneDX 1.5 and correct purl', bom.specVersion === '1.5' && bom.components[0].purl === 'pkg:npm/%40acme/core@1.2.0');
    const imported = SupplyScanner.parseDocument(JSON.stringify(bom));
    check('CycloneDX roundtrip preserves packages', imported.packages.length === 2 && imported.packages[0].license === 'MIT');

    const spdx = SupplyScanner.parseDocument(JSON.stringify({ spdxVersion: 'SPDX-2.3', name: 'python-app', packages: [
      { name: 'requests', versionInfo: '2.30.0', SPDXID: 'SPDXRef-requests', externalRefs: [{ referenceType: 'purl', referenceLocator: 'pkg:pypi/requests@2.30.0' }] },
    ] }));
    check('SPDX imports supported PyPI components', spdx.packages[0].ecosystem === 'PyPI');

    const originalFetch = window.fetch;
    let requests = 0;
    window.fetch = async (url, options) => {
      requests++;
      if (String(url).endsWith('querybatch')) {
        const query = JSON.parse(options.body).queries[0];
        check('OSV query uses exact package identity', query.package.name === '@acme/core' && query.version === '1.2.0');
        return { ok: true, json: async () => ({ results: [{ vulns: [{ id: 'TEST-2026-1' }] }, { vulns: [] }] }) };
      }
      return { ok: true, json: async () => ({ id: 'TEST-2026-1', summary: 'Test advisory', database_specific: { severity: 'HIGH' }, affected: [{ package: { name: '@acme/core', ecosystem: 'npm' }, ranges: [{ events: [{ fixed: '1.2.1' }] }] }] }) };
    };
    try {
      const findings = await SupplyScanner.scan(project);
      check('OSV resolves advisory details and fix', requests === 2 && findings.length === 1 && findings[0].severity === 'HIGH' && findings[0].fixed[0] === '1.2.1');
      window.fetch = async () => ({ ok: false, status: 503 });
      let failed = false;
      try { await SupplyScanner.scan(project); } catch (error) { failed = /HTTP 503/.test(error.message); }
      check('OSV failure is propagated', failed);
    } finally { window.fetch = originalFetch; }
    document.querySelector('#results').textContent = `ALL PASSED (${tests.length})\n${tests.join('\n')}`;
    document.body.dataset.result = 'passed';
  } catch (error) {
    document.querySelector('#results').textContent = `FAILED: ${error.message}\n${tests.join('\n')}`;
    document.body.dataset.result = 'failed';
  }
})();