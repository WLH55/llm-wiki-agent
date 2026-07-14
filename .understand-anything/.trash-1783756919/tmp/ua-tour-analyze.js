#!/usr/bin/env node
/**
 * Tour Builder — Phase 1: Graph Topology Analysis
 *
 * Usage: node ua-tour-analyze.js <input.json> <output.json>
 *
 * Input format:
 *   { fileNodes: [...], layers: [...], edges: [...] }
 *
 * Note: the input file uses the key "fileNodes" (not "nodes") but the array
 * contains heterogeneous node types (file, service, document, config, table,
 * schema). We normalize internally to "nodes".
 */

'use strict';

const fs = require('fs');

function fail(msg) {
  console.error('[tour-analyze] FATAL: ' + msg);
  process.exit(1);
}

function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    fail('Usage: node ua-tour-analyze.js <input.json> <output.json>');
  }
  const inputPath = args[0];
  const outputPath = args[1];

  let raw;
  try {
    raw = fs.readFileSync(inputPath, 'utf8');
  } catch (e) {
    fail('Cannot read input file: ' + inputPath + ' — ' + e.message);
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    fail('Cannot parse input JSON: ' + e.message);
  }

  // Normalize: accept both "nodes" and "fileNodes"
  const nodes = Array.isArray(data.nodes) ? data.nodes : (Array.isArray(data.fileNodes) ? data.fileNodes : []);
  const edges = Array.isArray(data.edges) ? data.edges : [];
  const layers = Array.isArray(data.layers) ? data.layers : [];

  if (nodes.length === 0) {
    fail('No nodes found in input (checked both "nodes" and "fileNodes").');
  }

  // ---- Build lookups ----
  const nodeById = new Map();
  for (const n of nodes) {
    nodeById.set(n.id, n);
  }

  // ---- A. Fan-In ranking ----
  const fanIn = new Map();
  for (const n of nodes) fanIn.set(n.id, 0);
  for (const e of edges) {
    if (fanIn.has(e.target)) fanIn.set(e.target, fanIn.get(e.target) + 1);
  }
  const fanInRanking = nodes
    .map(n => ({ id: n.id, fanIn: fanIn.get(n.id) || 0, name: n.name }))
    .sort((a, b) => b.fanIn - a.fanIn)
    .slice(0, 20);

  // ---- B. Fan-Out ranking ----
  const fanOut = new Map();
  for (const n of nodes) fanOut.set(n.id, 0);
  for (const e of edges) {
    if (fanOut.has(e.source)) fanOut.set(e.source, fanOut.get(e.source) + 1);
  }
  const fanOutRanking = nodes
    .map(n => ({ id: n.id, fanOut: fanOut.get(n.id) || 0, name: n.name }))
    .sort((a, b) => b.fanOut - a.fanOut)
    .slice(0, 20);

  // ---- C. Entry Point Candidates ----
  const entryPointFilenames = new Set([
    'index.ts', 'index.js', 'main.ts', 'main.js', 'app.ts', 'app.js',
    'server.ts', 'server.js', 'mod.rs', 'main.go', 'main.py', 'main.rs',
    'manage.py', 'app.py', 'wsgi.py', 'asgi.py', 'run.py', '__main__.py',
    'Application.java', 'Main.java', 'Program.cs', 'config.ru', 'index.php',
    'App.swift', 'Application.kt', 'main.cpp', 'main.c',
  ]);

  // Fan-out threshold for top 10%
  const fanOutValues = nodes.map(n => fanOut.get(n.id) || 0).sort((a, b) => b - a);
  const top10PctIdx = Math.max(0, Math.floor(fanOutValues.length * 0.1));
  const fanOutTop10Threshold = fanOutValues[top10PctIdx] || 0;

  // Fan-in bottom 25%
  const fanInValues = nodes.map(n => fanIn.get(n.id) || 0).sort((a, b) => a - b);
  const bottom25PctIdx = Math.floor(fanInValues.length * 0.25);
  const fanInBottom25Threshold = fanInValues[bottom25PctIdx] || 0;

  function pathDepth(filePath) {
    if (!filePath) return 99;
    const norm = filePath.replace(/\\/g, '/');
    const parts = norm.split('/').filter(Boolean);
    return parts.length;
  }

  function scoreEntry(n) {
    let score = 0;
    const isDoc = n.type === 'document';
    const isCode = n.type === 'file' || n.type === 'service' || n.type === 'config';

    if (isCode) {
      if (n.name && entryPointFilenames.has(n.name)) score += 3;
      const depth = pathDepth(n.filePath);
      // Root or one level deep (e.g. src/index.ts -> depth 2; root main.py -> depth 1)
      if (depth <= 2) score += 1;
      if ((fanOut.get(n.id) || 0) >= fanOutTop10Threshold && fanOutTop10Threshold > 0) score += 1;
      if ((fanIn.get(n.id) || 0) <= fanInBottom25Threshold) score += 1;
    } else if (isDoc) {
      if (n.name === 'README.md' && pathDepth(n.filePath) === 1) score += 5;
      else if (n.name && n.name.toLowerCase().endsWith('.md') && pathDepth(n.filePath) === 1) score += 2;
    }
    return score;
  }

  const entryPointCandidates = nodes
    .map(n => ({
      id: n.id,
      score: scoreEntry(n),
      name: n.name,
      type: n.type,
      summary: n.summary || '',
    }))
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 8);

  // ---- D. BFS Traversal from top CODE entry point ----
  // Build adjacency list of "forward dependency" edges: imports, calls
  // (also include depends_on, configures, triggers, inherits for completeness
  //  of code flow, but NOT documents/deploys/migrates which are cross-type)
  const forwardEdgeTypes = new Set(['imports', 'calls', 'depends_on', 'configures', 'triggers', 'inherits', 'exports']);
  const adj = new Map();
  for (const n of nodes) adj.set(n.id, []);
  for (const e of edges) {
    if (forwardEdgeTypes.has(e.type)) {
      if (adj.has(e.source) && adj.has(e.target)) {
        adj.get(e.source).push(e.target);
      }
    }
  }

  // Pick BFS start: highest-scoring code entry point (type file/service/config)
  const codeCandidates = entryPointCandidates.filter(c => c.type === 'file' || c.type === 'service' || c.type === 'config');
  const bfsStart = codeCandidates.length > 0 ? codeCandidates[0].id : null;

  const bfsTraversal = {
    startNode: bfsStart,
    order: [],
    depthMap: {},
    byDepth: {},
  };

  if (bfsStart) {
    const visited = new Set();
    const queue = [{ id: bfsStart, depth: 0 }];
    visited.add(bfsStart);
    while (queue.length > 0) {
      const { id, depth } = queue.shift();
      bfsTraversal.order.push(id);
      bfsTraversal.depthMap[id] = depth;
      if (!bfsTraversal.byDepth[depth]) bfsTraversal.byDepth[depth] = [];
      bfsTraversal.byDepth[depth].push(id);
      const neighbors = adj.get(id) || [];
      // Sort neighbors by fan-in desc for deterministic, importance-ordered traversal
      const sorted = neighbors
        .filter(t => !visited.has(t))
        .sort((a, b) => (fanIn.get(b) || 0) - (fanIn.get(a) || 0));
      for (const t of sorted) {
        visited.add(t);
        queue.push({ id: t, depth: depth + 1 });
      }
    }
  }

  // ---- E. Non-Code File Inventory ----
  const documentation = [];
  const infrastructure = [];
  const dataSchemas = [];
  const configFiles = [];

  for (const n of nodes) {
    const entry = { id: n.id, name: n.name, type: n.type, summary: n.summary || '' };
    if (n.type === 'document') documentation.push(entry);
    else if (n.type === 'service' || n.type === 'pipeline' || n.type === 'resource') infrastructure.push(entry);
    else if (n.type === 'table' || n.type === 'schema' || n.type === 'endpoint') dataSchemas.push(entry);
    else if (n.type === 'config') configFiles.push(entry);
  }

  const nonCodeFiles = {
    documentation,
    infrastructure,
    data: dataSchemas,
    config: configFiles,
  };

  // ---- F. Tightly Coupled Clusters ----
  // Build edge-pair counter (directional)
  const pairKey = (a, b) => a + '||' + b;
  const directionalEdges = new Set();
  for (const e of edges) {
    if (adj.has(e.source) && adj.has(e.target)) {
      directionalEdges.add(pairKey(e.source, e.target));
    }
  }

  // Find bidirectional pairs
  const clusterMap = new Map(); // nodeId -> clusterId
  const clusters = []; // array of Sets
  let nextClusterId = 0;

  function getCluster(id) {
    return clusterMap.get(id);
  }

  function mergeClusters(c1, c2) {
    if (c1 === c2) return c1;
    // Merge c2 into c1
    const members = clusters[c2];
    for (const m of members) {
      clusters[c1].add(m);
      clusterMap.set(m, c1);
    }
    clusters[c2] = null;
    return c1;
  }

  function ensureCluster(id) {
    if (clusterMap.has(id)) return clusterMap.get(id);
    const cid = nextClusterId++;
    clusters[cid] = new Set([id]);
    clusterMap.set(id, cid);
    return cid;
  }

  // Step 1: union bidirectional pairs
  for (const e of edges) {
    if (!adj.has(e.source) || !adj.has(e.target)) continue;
    const forward = pairKey(e.source, e.target);
    const reverse = pairKey(e.target, e.source);
    if (directionalEdges.has(forward) && directionalEdges.has(reverse)) {
      const c1 = ensureCluster(e.source);
      const c2 = ensureCluster(e.target);
      if (c1 !== c2) mergeClusters(c1, c2);
    }
  }

  // Step 2: expand — add nodes that connect to >=2 members of an existing cluster
  // Iterate a few rounds until stable
  let changed = true;
  let rounds = 0;
  while (changed && rounds < 5) {
    changed = false;
    rounds++;
    for (let cid = 0; cid < clusters.length; cid++) {
      const cluster = clusters[cid];
      if (!cluster || cluster.size === 0) continue;
      if (cluster.size >= 5) continue; // cap
      // Find candidate neighbors of all cluster members
      const candidateCounts = new Map();
      for (const member of cluster) {
        // outgoing
        for (const t of (adj.get(member) || [])) {
          if (!cluster.has(t)) {
            candidateCounts.set(t, (candidateCounts.get(t) || 0) + 1);
          }
        }
        // incoming (also count reverse edges for coupling)
        // We didn't build reverse adjacency; skip for simplicity
      }
      for (const [cand, count] of candidateCounts) {
        if (count >= 2) {
          cluster.add(cand);
          clusterMap.set(cand, cid);
          changed = true;
          if (cluster.size >= 5) break;
        }
      }
    }
  }

  // Count internal edges per cluster
  const clusterResults = [];
  for (let cid = 0; cid < clusters.length; cid++) {
    const cluster = clusters[cid];
    if (!cluster || cluster.size < 2) continue;
    const memberList = Array.from(cluster);
    let edgeCount = 0;
    for (const a of memberList) {
      for (const b of memberList) {
        if (a === b) continue;
        if (directionalEdges.has(pairKey(a, b))) edgeCount++;
      }
    }
    clusterResults.push({ nodes: memberList, edgeCount });
  }
  clusterResults.sort((a, b) => b.edgeCount - a.edgeCount);
  const topClusters = clusterResults.slice(0, 10);

  // ---- G. Layer List ----
  const layerOut = {
    count: layers.length,
    list: layers.map(l => ({ id: l.id, name: l.name, description: l.description })),
  };

  // ---- H. Node Summary Index ----
  const nodeSummaryIndex = {};
  for (const n of nodes) {
    nodeSummaryIndex[n.id] = {
      name: n.name,
      type: n.type,
      summary: n.summary || '',
      filePath: n.filePath || '',
    };
  }

  // ---- Compose output ----
  const output = {
    scriptCompleted: true,
    entryPointCandidates,
    fanInRanking,
    fanOutRanking,
    bfsTraversal,
    nonCodeFiles,
    clusters: topClusters,
    layers: layerOut,
    nodeSummaryIndex,
    totalNodes: nodes.length,
    totalEdges: edges.length,
  };

  try {
    fs.writeFileSync(outputPath, JSON.stringify(output, null, 2), 'utf8');
  } catch (e) {
    fail('Cannot write output file: ' + outputPath + ' — ' + e.message);
  }

  console.log('[tour-analyze] OK: ' + nodes.length + ' nodes, ' + edges.length + ' edges, ' +
    entryPointCandidates.length + ' entry candidates, ' + clusterResults.length + ' clusters.');
  process.exit(0);
}

main();
