(function () {
  'use strict';

  function parsePackageLock(input) {
    const lock = JSON.parse(input);
    if (!lock.packages || typeof lock.packages !== 'object') {
      throw new Error('Expected an npm package-lock.json with a packages section (lockfile v2 or v3).');
    }
    const packages = new Map();
    const root = lock.packages[''] || {};
    for (const [path, entry] of Object.entries(lock.packages)) {
      if (!path || !path.includes('node_modules/') || !entry?.version) continue;
      const name = path.slice(path.lastIndexOf('node_modules/') + 'node_modules/'.length);
      const key = `${name}@${entry.version}`;
      if (!packages.has(key)) {
        packages.set(key, {
          name,
          version: String(entry.version),
          ecosystem: 'npm',
          direct: Boolean(root.dependencies?.[name] || root.devDependencies?.[name] || root.optionalDependencies?.[name]),
          dev: Boolean(root.devDependencies?.[name] && !root.dependencies?.[name]),
          license: entry.license || null,
        });
      }
    }
    return { name: lock.name || root.name || 'Imported project', packages: [...packages.values()] };
  }

  function parseCycloneDx(bom) {
    if (!Array.isArray(bom.components)) throw new Error('CycloneDX SBOM has no components array.');
    const rootDependencies = new Set(bom.dependencies?.find(item => item.ref === bom.metadata?.component?.['bom-ref'])?.dependsOn || []);
    const packages = bom.components.filter(item => item.type === 'library' || item.type === 'framework').map(item => {
      const purl = item.purl || '';
      const npm = purl.startsWith('pkg:npm/');
      const ecosystem = npm ? 'npm' : purl.startsWith('pkg:pypi/') ? 'PyPI' : null;
      if (!ecosystem || !item.name || !item.version) return null;
      return {
        name: item.name,
        version: String(item.version),
        ecosystem,
        direct: Boolean(item['bom-ref'] && rootDependencies.has(item['bom-ref'])),
        dev: item.scope === 'excluded',
        license: item.licenses?.map(value => value.license?.id || value.license?.name || value.expression).filter(Boolean).join(', ') || null,
      };
    }).filter(Boolean);
    return { name: bom.metadata?.component?.name || 'Imported SBOM', packages: unique(packages) };
  }

  function parseSpdx(bom) {
    if (!Array.isArray(bom.packages)) throw new Error('SPDX SBOM has no packages array.');
    const directIds = new Set((bom.relationships || []).filter(item => item.relationshipType === 'DEPENDS_ON' && item.spdxElementId === bom.documentDescribes?.[0]).map(item => item.relatedSpdxElement));
    const packages = bom.packages.map(item => {
      const purl = item.externalRefs?.find(ref => ref.referenceType === 'purl')?.referenceLocator || '';
      const ecosystem = purl.startsWith('pkg:npm/') ? 'npm' : purl.startsWith('pkg:pypi/') ? 'PyPI' : null;
      if (!ecosystem || !item.name || !item.versionInfo) return null;
      return { name: item.name, version: String(item.versionInfo), ecosystem, direct: directIds.has(item.SPDXID), dev: false, license: item.licenseConcluded && item.licenseConcluded !== 'NOASSERTION' ? item.licenseConcluded : null };
    }).filter(Boolean);
    return { name: bom.name || 'Imported SBOM', packages: unique(packages) };
  }

  function unique(packages) {
    return [...new Map(packages.map(item => [`${item.ecosystem}:${item.name}@${item.version}`, item])).values()];
  }

  function parseDocument(text) {
    const data = JSON.parse(text);
    if (data.bomFormat === 'CycloneDX') return parseCycloneDx(data);
    if (data.spdxVersion?.startsWith('SPDX-')) return parseSpdx(data);
    return parsePackageLock(text);
  }

  function purlFor(pkg) {
    const name = pkg.ecosystem === 'npm' ? pkg.name.replace(/^@/, '%40') : pkg.name;
    return `pkg:${pkg.ecosystem === 'npm' ? 'npm' : 'pypi'}/${name}@${encodeURIComponent(pkg.version)}`;
  }

  function makeBom(project) {
    return {
      bomFormat: 'CycloneDX', specVersion: '1.5', serialNumber: `urn:uuid:${crypto.randomUUID()}`, version: 1,
      metadata: { timestamp: new Date().toISOString(), tools: [{ vendor: 'Northstar', name: 'Sentryline', version: '1.0.0' }], component: { type: 'application', name: project.name } },
      components: project.packages.map(pkg => ({
        type: 'library', name: pkg.name, version: pkg.version, purl: purlFor(pkg),
        ...(pkg.license ? { licenses: [{ license: { name: pkg.license } }] } : {}),
      })),
    };
  }

  function severityOf(vuln) {
    const sources = [vuln.database_specific?.severity, ...(vuln.affected || []).map(item => item.ecosystem_specific?.severity)];
    for (const value of sources) {
      if (typeof value === 'string' && /^(CRITICAL|HIGH|MEDIUM|MODERATE|LOW)$/i.test(value)) {
        return value.toUpperCase() === 'MODERATE' ? 'MEDIUM' : value.toUpperCase();
      }
    }
    for (const entry of vuln.severity || []) {
      const score = Number(entry.score);
      if (Number.isFinite(score) && score >= 0 && score <= 10) {
        return score >= 9 ? 'CRITICAL' : score >= 7 ? 'HIGH' : score >= 4 ? 'MEDIUM' : 'LOW';
      }
    }
    return 'UNKNOWN';
  }

  function fixedVersion(vuln, pkg) {
    const matches = (vuln.affected || []).filter(item => item.package?.name === pkg.name && item.package?.ecosystem?.toLowerCase() === pkg.ecosystem.toLowerCase());
    return [...new Set(matches.flatMap(item => (item.ranges || []).flatMap(range => (range.events || []).map(event => event.fixed).filter(Boolean))))];
  }

  async function scan(project, onProgress) {
    const packages = project.packages;
    const batchSize = 100;
    const hits = new Map();
    for (let offset = 0; offset < packages.length; offset += batchSize) {
      const slice = packages.slice(offset, offset + batchSize);
      const response = await fetch('https://api.osv.dev/v1/querybatch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ queries: slice.map(pkg => ({ package: { name: pkg.name, ecosystem: pkg.ecosystem }, version: pkg.version })) }),
      });
      if (!response.ok) throw new Error(`OSV batch request failed (HTTP ${response.status}).`);
      const data = await response.json();
      if (!Array.isArray(data.results) || data.results.length !== slice.length) throw new Error('OSV returned an incomplete batch.');
      data.results.forEach((result, index) => {
        for (const vuln of result.vulns || []) {
          const id = vuln.id;
          if (!id) continue;
          if (!hits.has(id)) hits.set(id, new Set());
          hits.get(id).add(offset + index);
        }
      });
      onProgress?.({ checked: Math.min(offset + batchSize, packages.length), total: packages.length });
    }

    const ids = [...hits.keys()];
    const details = new Map();
    let cursor = 0;
    async function worker() {
      while (cursor < ids.length) {
        const id = ids[cursor++];
        const response = await fetch(`https://api.osv.dev/v1/vulns/${encodeURIComponent(id)}`);
        if (!response.ok) throw new Error(`OSV advisory request failed (HTTP ${response.status}).`);
        details.set(id, await response.json());
      }
    }
    await Promise.all(Array.from({ length: Math.min(6, ids.length) }, () => worker()));
    return ids.flatMap(id => [...hits.get(id)].map(index => {
      const vuln = details.get(id);
      const pkg = packages[index];
      return {
        id, package: pkg, severity: severityOf(vuln), summary: vuln.summary || 'No advisory summary provided.',
        details: vuln.details || '', aliases: vuln.aliases || [], fixed: fixedVersion(vuln, pkg),
        url: `https://osv.dev/vulnerability/${encodeURIComponent(id)}`,
        published: vuln.published || null,
      };
    }));
  }

  window.SupplyScanner = { parsePackageLock, parseDocument, parseCycloneDx, parseSpdx, makeBom, scan, severityOf, purlFor };
})();