#!/usr/bin/env node
/**
 * Architecture Analyzer - Phase 1 Structural Analysis
 * Computes directory groups, node type groups, import adjacency, density, patterns.
 */
'use strict';

const fs = require('fs');
const path = require('path');

function main() {
  const inputPath = process.argv[2];
  const outputPath = process.argv[3];
  if (!inputPath || !outputPath) {
    console.error('Usage: node ua-arch-analyze.js <input.json> <output.json>');
    process.exit(1);
  }

  const raw = fs.readFileSync(inputPath, 'utf8');
  const data = JSON.parse(raw);
  const fileNodes = data.fileNodes || [];
  const importEdges = data.importEdges || [];
  const allEdges = data.allEdges || [];

  // --- A. Directory Grouping ---
  // Compute common prefix
  const paths = fileNodes.map(n => n.filePath.replace(/\\/g, '/'));
  const commonPrefix = computeCommonPathPrefix(paths);

  const directoryGroups = {};
  const fileToGroup = {};
  fileNodes.forEach(node => {
    const p = node.filePath.replace(/\\/g, '/');
    let rel = commonPrefix ? p.slice(commonPrefix.length) : p;
    rel = rel.replace(/^\/+/, '');
    let group;
    if (rel.includes('/')) {
      group = rel.split('/')[0];
    } else {
      group = '<root>';
    }
    if (!directoryGroups[group]) directoryGroups[group] = [];
    directoryGroups[group].push(node.id);
    fileToGroup[node.id] = group;
  });

  // --- B. Node Type Grouping ---
  const nodeTypeGroups = {};
  fileNodes.forEach(node => {
    if (!nodeTypeGroups[node.type]) nodeTypeGroups[node.type] = [];
    nodeTypeGroups[node.type].push(node.id);
  });

  // --- C. Import Adjacency Matrix ---
  const fanOut = {};
  const fanIn = {};
  fileNodes.forEach(n => { fanOut[n.id] = 0; fanIn[n.id] = 0; });
  importEdges.forEach(e => {
    if (fanOut[e.source] !== undefined) fanOut[e.source]++;
    if (fanIn[e.target] !== undefined) fanIn[e.target]++;
  });

  // --- D. Cross-Category Dependency Analysis ---
  const typeOf = {};
  fileNodes.forEach(n => { typeOf[n.id] = n.type; });
  const crossCategoryMap = {};
  allEdges.forEach(e => {
    const sType = typeOf[e.source];
    const tType = typeOf[e.target];
    if (!sType || !tType) return;
    if (sType === 'file' && tType === 'file' && e.type === 'imports') return; // pure code import
    const key = `${sType}|${tType}|${e.type}`;
    crossCategoryMap[key] = (crossCategoryMap[key] || 0) + 1;
  });
  const crossCategoryEdges = Object.entries(crossCategoryMap).map(([k, count]) => {
    const [fromType, toType, edgeType] = k.split('|');
    return { fromType, toType, edgeType, count };
  }).sort((a, b) => b.count - a.count);

  // --- E. Inter-Group Import Frequency ---
  const interGroupMap = {};
  importEdges.forEach(e => {
    const gFrom = fileToGroup[e.source];
    const gTo = fileToGroup[e.target];
    if (!gFrom || !gTo || gFrom === gTo) return;
    const key = `${gFrom}|${gTo}`;
    interGroupMap[key] = (interGroupMap[key] || 0) + 1;
  });
  const interGroupImports = Object.entries(interGroupMap).map(([k, count]) => {
    const [from, to] = k.split('|');
    return { from, to, count };
  }).sort((a, b) => b.count - a.count);

  // --- F. Intra-Group Import Density ---
  const intraGroupDensity = {};
  Object.keys(directoryGroups).forEach(g => {
    intraGroupDensity[g] = { internalEdges: 0, totalEdges: 0, density: 0 };
  });
  importEdges.forEach(e => {
    const gFrom = fileToGroup[e.source];
    const gTo = fileToGroup[e.target];
    if (gFrom && gFrom === gTo) {
      intraGroupDensity[gFrom].internalEdges++;
    }
    if (gFrom) intraGroupDensity[gFrom].totalEdges++;
    if (gTo && gTo !== gFrom) intraGroupDensity[gTo].totalEdges++;
  });
  Object.keys(intraGroupDensity).forEach(g => {
    const d = intraGroupDensity[g];
    d.density = d.totalEdges > 0 ? +(d.internalEdges / d.totalEdges).toFixed(3) : 0;
  });

  // --- G. Directory Pattern Matching ---
  const patternMatches = {};
  Object.keys(directoryGroups).forEach(g => {
    patternMatches[g] = matchDirectoryPattern(g);
  });
  // File-level pattern overrides
  fileNodes.forEach(node => {
    const fp = matchFilePattern(node.filePath, node.name, fileToGroup[node.id]);
    if (fp) node._filePattern = fp;
  });

  // --- H. Deployment Topology ---
  const allFilePaths = fileNodes.map(n => n.filePath.replace(/\\/g, '/'));
  const deploymentTopology = detectDeployment(allFilePaths);

  // --- I. Data Pipeline ---
  const dataPipeline = detectDataPipeline(fileNodes, allEdges);

  // --- J. Documentation Coverage ---
  const docCoverage = computeDocCoverage(fileNodes, directoryGroups, fileToGroup);

  // --- K. Dependency Direction ---
  const pairDir = {};
  interGroupImports.forEach(({ from, to, count }) => {
    const key = [from, to].sort().join('|');
    if (!pairDir[key]) pairDir[key] = { a: from < to ? from : to, b: from < to ? to : from, ab: 0, ba: 0 };
    if (from < to) pairDir[key].ab += count; else pairDir[key].ba += count;
  });
  const dependencyDirection = [];
  Object.values(pairDir).forEach(p => {
    if (p.ab > p.ba) dependencyDirection.push({ dependent: p.a, dependsOn: p.b, dominant: p.ab });
    else if (p.ba > p.ab) dependencyDirection.push({ dependent: p.b, dependsOn: p.a, dominant: p.ba });
  });
  dependencyDirection.sort((a, b) => b.dominant - a.dominant);

  // --- File Stats ---
  const filesPerGroup = {};
  Object.entries(directoryGroups).forEach(([g, ids]) => { filesPerGroup[g] = ids.length; });
  const nodeTypeCounts = {};
  Object.entries(nodeTypeGroups).forEach(([t, ids]) => { nodeTypeCounts[t] = ids.length; });

  const result = {
    scriptCompleted: true,
    commonPrefix,
    directoryGroups,
    nodeTypeGroups,
    crossCategoryEdges,
    interGroupImports,
    intraGroupDensity,
    patternMatches,
    deploymentTopology,
    dataPipeline,
    docCoverage,
    dependencyDirection,
    fileStats: {
      totalFileNodes: fileNodes.length,
      filesPerGroup,
      nodeTypeCounts
    },
    fileFanIn: topN(fanIn, 15),
    fileFanOut: topN(fanOut, 15)
  };

  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
  console.log('OK: wrote', outputPath);
  console.log('  groups:', Object.keys(directoryGroups).length);
  console.log('  file nodes:', fileNodes.length);
  console.log('  import edges:', importEdges.length);
  console.log('  all edges:', allEdges.length);
}

function computeCommonPathPrefix(paths) {
  if (!paths.length) return '';
  const split = paths.map(p => p.replace(/\\/g, '/').split('/'));
  // Find common directory prefix (not file)
  let prefix = [];
  for (let i = 0; i < split[0].length - 1; i++) {
    const seg = split[0][i];
    if (split.every(s => s[i] === seg)) prefix.push(seg);
    else break;
  }
  // Only use prefix if it covers > 50% of files
  const candidate = prefix.join('/') + '/';
  const covered = paths.filter(p => p.startsWith(candidate)).length;
  if (covered / paths.length > 0.5 && prefix.length > 0) return candidate;
  return '';
}

function matchDirectoryPattern(dirName) {
  const d = dirName.toLowerCase();
  const map = {
    'routes': 'api', 'routers': 'api', 'api': 'api', 'controllers': 'api',
    'endpoints': 'api', 'handlers': 'api', 'serializers': 'api', 'blueprints': 'api',
    'services': 'service', 'core': 'service', 'lib': 'service', 'domain': 'service',
    'logic': 'service', 'internal': 'service', 'signals': 'service', 'composables': 'service',
    'mailers': 'service', 'jobs': 'service', 'channels': 'service',
    'models': 'data', 'db': 'data', 'data': 'data', 'persistence': 'data',
    'repository': 'data', 'entities': 'data', 'entity': 'data', 'migrations': 'data',
    'sql': 'data', 'database': 'data', 'schema': 'data', 'alembic': 'data',
    'components': 'ui', 'views': 'ui', 'pages': 'ui', 'ui': 'ui',
    'layouts': 'ui', 'screens': 'ui', 'src': 'ui',
    'middleware': 'middleware', 'plugins': 'middleware', 'interceptors': 'middleware',
    'guards': 'middleware',
    'utils': 'utility', 'helpers': 'utility', 'common': 'utility',
    'shared': 'utility', 'tools': 'utility', 'pkg': 'utility', 'templatetags': 'utility',
    'config': 'config', 'constants': 'config', 'env': 'config', 'settings': 'config',
    'management': 'config', 'commands': 'config',
    '__tests__': 'test', 'test': 'test', 'tests': 'test', 'spec': 'test', 'specs': 'test',
    'types': 'types', 'interfaces': 'types', 'schemas': 'types', 'contracts': 'types',
    'dtos': 'types', 'dto': 'types', 'request': 'types', 'response': 'types',
    'hooks': 'hooks',
    'store': 'state', 'state': 'state', 'reducers': 'state', 'actions': 'state', 'slices': 'state',
    'assets': 'assets', 'static': 'assets', 'public': 'assets',
    'workers': 'service', 'auth': 'service',
    'cmd': 'entry', 'bin': 'entry',
    'docs': 'documentation', 'documentation': 'documentation', 'wiki': 'documentation',
    'mydocs': 'documentation', 'context': 'documentation', 'specs': 'documentation',
    'deploy': 'infrastructure', 'deployment': 'infrastructure', 'infra': 'infrastructure',
    'infrastructure': 'infrastructure', 'k8s': 'infrastructure', 'kubernetes': 'infrastructure',
    'helm': 'infrastructure', 'charts': 'infrastructure', 'terraform': 'infrastructure',
    'docker': 'infrastructure', 'postgres': 'infrastructure',
    '.github': 'ci-cd', '.gitlab': 'ci-cd', '.circleci': 'ci-cd',
    'frontend': 'ui', 'backend': 'service', 'app': 'service'
  };
  return map[d] || null;
}

function matchFilePattern(filePath, name, group) {
  const p = filePath.replace(/\\/g, '/');
  const lower = name.toLowerCase();
  if (/\.(test|spec)\./.test(name) || /^test_.*\.py$/.test(name) ||
      /_test\.go$/.test(name) || /Test\.java$/.test(name) ||
      /_spec\.rb$/.test(name) || /Test\.php$/.test(name) || /Tests\.cs$/.test(name)) return 'test';
  if (/\.d\.ts$/.test(name)) return 'types';
  if (/\.(graphql|gql|proto)$/.test(name)) return 'types';
  if (/\.(sql)$/.test(name)) return 'data';
  if (/\.(md|rst)$/.test(name)) return 'documentation';
  if (/^Dockerfile/i.test(name) || /^docker-compose/i.test(name)) return 'infrastructure';
  if (/\.(tf|tfvars)$/.test(name)) return 'infrastructure';
  if (/^Makefile$/i.test(name)) return 'infrastructure';
  if (p.includes('.github/workflows/') || p.includes('.gitlab-ci.yml') || /Jenkinsfile/i.test(name)) return 'ci-cd';
  if (['package.json','tsconfig.json','Cargo.toml','go.mod','Gemfile','pom.xml','build.gradle',
       'composer.json','pyproject.toml','alembic.ini','vite.config.ts','vite.config.js',
       'tailwind.config.js','postcss.config.js','requirements.txt','.env.example'].includes(name)) return 'config';
  if (['wsgi.py','asgi.py'].includes(name)) return 'config';
  if (name === 'manage.py') return 'entry';
  if (name === 'main.rs' || name === 'lib.rs') return 'entry';
  if (name === 'Application.java' || name === 'Program.cs') return 'entry';
  if (name === 'config.ru') return 'entry';
  if ((name === 'main.tsx' || name === 'main.ts' || name === 'App.tsx') && group === 'src') return 'entry';
  if (name === '__init__.py') return 'entry';
  if (name === 'index.ts' || name === 'index.js') return 'entry';
  if (name === 'main.go' && p.includes('cmd/')) return 'entry';
  if (name === 'main.py' && group === 'app') return 'entry';
  return null;
}

function detectDeployment(paths) {
  const lower = paths.map(p => p.toLowerCase());
  const hasDockerfile = lower.some(p => /(^|\/)dockerfile/.test(p));
  const hasCompose = lower.some(p => /docker-compose/i.test(p));
  const hasK8s = lower.some(p => /(^|\/)(k8s|kubernetes|helm|charts)\//.test(p) || /\.(yaml|yml)$/i.test(p) && p.includes('deploy'));
  const hasTerraform = lower.some(p => /\.tf$/i.test(p) || /terraform/i.test(p));
  const hasCI = lower.some(p => p.includes('.github/workflows') || p.includes('.gitlab-ci') || /jenkinsfile/i.test(p) || p.includes('.circleci'));
  const infraFiles = paths.filter(p => {
    const lp = p.toLowerCase();
    return /(^|\/)dockerfile/.test(lp) || /docker-compose/i.test(lp) ||
           /\.tf$/i.test(lp) || lp.includes('.github/workflows') ||
           lp.includes('.gitlab-ci') || /jenkinsfile/i.test(lp) || /(^|\/)makefile$/i.test(lp) ||
           lp.includes('postgres/');
  });
  return { hasDockerfile, hasCompose, hasK8s, hasTerraform, hasCI, infraFiles };
}

function detectDataPipeline(fileNodes, allEdges) {
  const schemaFiles = [];
  const migrationFiles = [];
  const dataModelFiles = [];
  const apiHandlerFiles = [];
  fileNodes.forEach(n => {
    const p = n.filePath.replace(/\\/g, '/').toLowerCase();
    if (p.endsWith('.sql') || /\.(graphql|gql|proto|prisma)$/.test(p)) schemaFiles.push(n.filePath);
    if (p.includes('migrations/') || p.includes('alembic/versions/')) migrationFiles.push(n.filePath);
    if (p.includes('/models/') && p.endsWith('.py')) dataModelFiles.push(n.filePath);
    if (p.includes('/routers/') || p.includes('/routes/') || p.includes('/api/')) apiHandlerFiles.push(n.filePath);
  });
  return { schemaFiles, migrationFiles, dataModelFiles, apiHandlerFiles };
}

function computeDocCoverage(fileNodes, directoryGroups, fileToGroup) {
  const groupsWithDocs = new Set();
  const docGroups = new Set();
  fileNodes.forEach(n => {
    if (n.type === 'document') {
      const g = fileToGroup[n.id];
      if (g) { groupsWithDocs.add(g); docGroups.add(g); }
    }
  });
  const total = Object.keys(directoryGroups).length;
  return {
    groupsWithDocs: groupsWithDocs.size,
    totalGroups: total,
    coverageRatio: total > 0 ? +(groupsWithDocs.size / total).toFixed(2) : 0,
    undocumentedGroups: Object.keys(directoryGroups).filter(g => !groupsWithDocs.has(g))
  };
}

function topN(obj, n) {
  return Object.entries(obj)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .reduce((acc, [k, v]) => { acc[k] = v; return acc; }, {});
}

try {
  main();
  process.exit(0);
} catch (err) {
  console.error('FATAL:', err.stack || err.message);
  process.exit(1);
}
