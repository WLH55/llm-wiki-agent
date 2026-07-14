#!/usr/bin/env node
/**
 * Layer Assignment - Phase 2
 * Assigns every file node to exactly one of 8 Chinese-named layers.
 */
'use strict';
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('D:/AI/知识库设计/llm_wiki3.0/.understand-anything/intermediate/arch-input.json', 'utf8'));
const fileNodes = data.fileNodes;

const layers = {
  'layer:api': { id: 'layer:api', name: 'API 接口层', description: '', nodeIds: [] },
  'layer:service': { id: 'layer:service', name: '业务服务层', description: '', nodeIds: [] },
  'layer:data': { id: 'layer:data', name: '数据模型与迁移层', description: '', nodeIds: [] },
  'layer:infrastructure': { id: 'layer:infrastructure', name: '异步任务与基础设施层', description: '', nodeIds: [] },
  'layer:frontend': { id: 'layer:frontend', name: '前端 UI 层', description: '', nodeIds: [] },
  'layer:config': { id: 'layer:config', name: '配置与容器编排层', description: '', nodeIds: [] },
  'layer:documentation': { id: 'layer:documentation', name: '项目文档层', description: '', nodeIds: [] },
  'layer:test': { id: 'layer:test', name: '测试套件层', description: '', nodeIds: [] }
};

function pathOf(id) {
  const node = fileNodes.find(n => n.id === id);
  return node ? node.filePath.replace(/\\/g, '/') : '';
}

fileNodes.forEach(node => {
  const p = node.filePath.replace(/\\/g, '/');
  const id = node.id;

  // --- 测试套件层 (highest priority: any test file) ---
  if (p.includes('/tests/') || p.includes('/__tests__/') ||
      /\.(test|spec)\./.test(p) || /^test_/.test(node.name) ||
      node.name === 'conftest.py') {
    layers['layer:test'].nodeIds.push(id);
    return;
  }

  // --- 项目文档层 (any markdown/html doc, ADRs, specs, CONTEXT) ---
  if (node.type === 'document' || /\.(md|rst|html)$/.test(p) ||
      p.includes('/mydocs/') || p.includes('/docs/') ||
      p.includes('/adr/') || p.includes('/specs/') ||
      node.name === 'CONTEXT.md' || node.name === 'README.md') {
    layers['layer:documentation'].nodeIds.push(id);
    return;
  }

  // --- 前端 UI 层 ---
  if (p.startsWith('frontend/')) {
    // config files in frontend go to config layer
    if (node.type === 'config' || /\.(toml|json|js|ts)$/.test(p) &&
        (node.name === 'package.json' || node.name === 'tsconfig.json' ||
         node.name === 'vite.config.ts' || node.name === 'tailwind.config.js' ||
         node.name === 'postcss.config.js')) {
      layers['layer:config'].nodeIds.push(id);
      return;
    }
    layers['layer:frontend'].nodeIds.push(id);
    return;
  }

  // --- postgres init schema goes to data layer ---
  if (p.startsWith('postgres/')) {
    if (p.endsWith('.sql')) {
      layers['layer:data'].nodeIds.push(id);
    } else {
      layers['layer:config'].nodeIds.push(id); // postgres Dockerfile -> config/infra
    }
    return;
  }

  // --- root-level infra/compose/config ---
  if (node.type === 'service' || node.name.startsWith('Dockerfile') ||
      node.name.startsWith('docker-compose') || node.name === 'Makefile' ||
      node.name === '.env.example') {
    layers['layer:config'].nodeIds.push(id);
    return;
  }

  // --- alembic migration config files ---
  if (p.includes('/alembic/') && (p.endsWith('alembic.ini') || node.name === 'script.py.mako' || node.name === 'env.py')) {
    layers['layer:data'].nodeIds.push(id);
    return;
  }

  // --- alembic migration versions + table nodes ---
  if (p.includes('/alembic/versions/') || node.type === 'table') {
    layers['layer:data'].nodeIds.push(id);
    return;
  }

  // --- backend code files ---
  if (p.startsWith('backend/')) {
    // Schema/SQL definitions
    if (node.type === 'schema' || p.endsWith('.sql')) {
      layers['layer:data'].nodeIds.push(id);
      return;
    }
    // pyproject.toml -> config
    if (node.name === 'pyproject.toml' || node.name === 'alembic.ini') {
      layers['layer:config'].nodeIds.push(id);
      return;
    }
    // API layer: routers + auth/routes + FastAPI entry main.py + deps + schemas (Pydantic DTOs)
    if (p.includes('/routers/') || p.includes('/schemas/') ||
        p === 'backend/app/auth/routes.py' || p === 'backend/app/main.py' ||
        p === 'backend/app/deps.py') {
      layers['layer:api'].nodeIds.push(id);
      return;
    }
    // Service layer: services + auth (business logic: jwt, password, bootstrap)
    if (p.includes('/services/') || p.includes('/auth/')) {
      layers['layer:service'].nodeIds.push(id);
      return;
    }
    // Infrastructure: workers + plugins + database + config/* (cross-cutting concerns)
    if (p.includes('/workers/') || p.includes('/plugins/') ||
        p === 'backend/app/database.py' || p.includes('/config/')) {
      layers['layer:infrastructure'].nodeIds.push(id);
      return;
    }
    // Data model layer: models/*
    if (p.includes('/models/')) {
      layers['layer:data'].nodeIds.push(id);
      return;
    }
    // Fallback for backend __init__ files at top of app
    if (p === 'backend/app/__init__.py') {
      layers['layer:infrastructure'].nodeIds.push(id);
      return;
    }
    // Anything else backend -> infrastructure
    layers['layer:infrastructure'].nodeIds.push(id);
    return;
  }

  // --- .understand-anything metadata -> config ---
  if (p.startsWith('.understand-anything/')) {
    layers['layer:config'].nodeIds.push(id);
    return;
  }

  // Fallback: anything else -> config
  layers['layer:config'].nodeIds.push(id);
});

// Now add descriptions specific to this project
layers['layer:api'].description = 'FastAPI HTTP 入口与请求/响应契约，包括 routers/（document/kb/search 路由）、auth/routes、main.py 应用装配、deps.py 依赖注入以及 schemas/ 下基于 Pydantic 的请求/响应 DTO。';
layers['layer:service'].description = '核心业务逻辑编排：services/（document_service、kb_service、search_service、embedding_service、minio_service）以及 auth/ 模块（jwt_handler、password、bootstrap）负责鉴权与首个管理员初始化。';
layers['layer:data'].description = '数据持久化层：SQLAlchemy ORM 模型（User/KB/Document/Chunk/Source/WikiPage 等）、Alembic 迁移脚本与版本（001_initial）、迁移产生的表节点以及 PostgreSQL 扩展初始化 SQL（pgvector/zhparser）。';
layers['layer:infrastructure'].description = '跨切面基础设施与异步管道：config/（settings、exceptions、schemas、logger、dependencies）、database.py 异步引擎、RQ workers/（chunker、parsers、queue、worker）负责文档解析-分块-嵌入流水线，以及 plugins/chunk_rerank 重排插件。';
layers['layer:frontend'].description = 'React + Vite + TailwindCSS 前端：Search 页面、SearchBox/ResultList 组件、App.tsx 路由装配、api.ts Axios 客户端以及 main.tsx Vite 入口。';
layers['layer:config'].description = '项目级配置与容器编排：根目录 docker-compose.yml（backend/worker/postgres/minio/redis 五服务）、backend/Dockerfile 多阶段构建（frontend-build + python）、postgres/Dockerfile、Makefile、.env.example、前后端构建配置（pyproject.toml、package.json、tsconfig.json、vite.config.ts、tailwind/postcss）以及 alembic.ini。';
layers['layer:documentation'].description = '项目文档与设计资产：mydocs/ 下的 PRD v4.2、知识库/RAG/多租户架构设计、9 篇 ADR（0001-0009）、MVP P1 Batch 1 SDD 规范、Obsidian Wiki 调研对比、TS 指南以及根目录 README.md。';
layers['layer:test'].description = 'pytest 测试套件：tests/ 下覆盖鉴权（test_auth）、知识库（test_kb）、文档（test_document）、检索（test_search）以及 pgvector 半精度向量（test_halfvec）的集成与单元测试，含 conftest.py 公共 fixture。';

// Verify counts
let total = 0;
Object.entries(layers).forEach(([id, l]) => {
  console.log(`${id}: ${l.nodeIds.length} nodes`);
  total += l.nodeIds.length;
});
console.log('TOTAL:', total, '(expected', fileNodes.length, ')');

if (total !== fileNodes.length) {
  console.error('MISMATCH!');
  process.exit(1);
}

// Find any duplicates
const allIds = [];
Object.values(layers).forEach(l => allIds.push(...l.nodeIds));
const dupes = allIds.filter((id, i) => allIds.indexOf(id) !== i);
if (dupes.length) {
  console.error('DUPLICATES:', dupes);
  process.exit(1);
}

// Drop empty layers
const finalLayers = Object.values(layers).filter(l => l.nodeIds.length > 0);
console.log('\nFinal layer count:', finalLayers.length);

const outPath = 'D:/AI/知识库设计/llm_wiki3.0/.understand-anything/intermediate/layers.json';
fs.writeFileSync(outPath, JSON.stringify(finalLayers, null, 2), 'utf8');
console.log('Wrote:', outPath);
