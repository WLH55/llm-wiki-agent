/**
 * 设置弹窗 — 全局共享组件
 * 齿轮按钮点击 → 弹出全屏遮罩 + 居中弹窗
 * 左侧导航 4 项，右侧内容区切换显示
 */

/* ============== 导航项定义 ============== */
const SETTINGS_NAV = [
  { id: 'exec-mode',   icon: '☰', label: '配置执行模式' },
  { id: 'mcp-server',  icon: '⛓', label: 'MCP 服务器' },
  { id: 'permissions', icon: '⚿', label: '权限' },
  { id: 'backup',      icon: '↺', label: '备份' },
];

/* ============== 当前状态 ============== */
let activeNavId = 'exec-mode';
let activeExecTab = 'local';    // 'local' | 'byok'
let selectedCli = 'claude-code';

/* ============== CLI 工具列表 ============== */
const CLI_TOOLS = [
  { id: 'claude-code',    icon: '◉', name: 'Claude Code',       version: '2.1.150',  installed: true,  selected: true },
  { id: 'codex-cli',      icon: '❯', name: 'Codex CLI',         version: '0.118.0',  installed: true,  selected: false },
  { id: 'devin',          icon: '✦', name: 'Devin for Terminal', version: '',         installed: false, selected: false },
  { id: 'gemini-cli',     icon: '❯', name: 'Gemini CLI',        version: '',         installed: true,  selected: false },
  { id: 'opencode',       icon: '■', name: 'OpenCode',          version: '1.17.7',   installed: false, selected: false },
  { id: 'hermes',         icon: '♦', name: 'Hermes',            version: '',         installed: false, selected: false },
  { id: 'kimi-cli',       icon: 'K', name: 'Kimi CLI',          version: '',         installed: false, selected: false },
  { id: 'cursor-agent',   icon: '◆', name: 'Cursor Agent',      version: '',         installed: false, selected: false },
  { id: 'qwen-code',      icon: '★', name: 'Qwen Code',         version: '',         installed: false, selected: false },
  { id: 'qoder-cli',      icon: 'a', name: 'Qoder CLI',         version: '',         installed: false, selected: false },
  { id: 'copilot-cli',    icon: '◈', name: 'GitHub Copilot CLI', version: '',        installed: true,  selected: false },
  { id: 'kiro-cli',       icon: '○', name: 'Kiro CLI',          version: '',         installed: false, selected: false },
];

/* ============== MiniAgent 模型配置（两种兼容格式） ============== */
const BYOK_PROVIDERS = [
  { id: 'openai-format',    icon: '◉', name: 'OpenAI 兼容格式',    desc: '支持 OpenAI / DeepSeek / 通义千问等兼容接口', status: '推荐', active: true,  keyPlaceholder: 'sk-...',        urlPlaceholder: 'https://api.openai.com/v1' },
  { id: 'anthropic-format', icon: '◈', name: 'Anthropic 兼容格式', desc: '支持 Anthropic Claude 系列模型',               status: '',     active: false, keyPlaceholder: 'sk-ant-...',    urlPlaceholder: 'https://api.anthropic.com' },
];

/* ============== 其他分区 Mock 内容 ============== */
const SETTINGS_CONTENT = {
  'permissions': {
    title: '权限管理',
    subtitle: '控制知识库对当前用户的可见性。可插拔架构，按需授权。',
    cards: [
      { icon: '📁', name: '工作知识库', version: '37 页', meta: 'IAP / 投放 / 钉钉 / 工作积累', status: '可见', active: true },
      { icon: '📁', name: '技术文档库', version: '124 页', meta: 'API / SDK / 架构设计', status: '可见', active: true },
      { icon: '🔒', name: '产品需求库', version: '56 页', meta: 'PRD / 设计稿 / 评审记录', status: '不可见', active: false },
      { icon: '🔒', name: '财务报表库', version: '89 页', meta: '月度财报 / 成本分析', status: '不可见', active: false },
    ],
    actions: ['申请权限', '刷新列表'],
  },
  'backup': {
    title: '备份与恢复',
    subtitle: '导出知识库数据或从备份文件恢复。支持 Markdown / JSON 格式。',
    cards: [
      { icon: '⬇', name: '导出全部', version: '', meta: '将所有知识库页面导出为 ZIP 压缩包', status: '37 页', active: false },
      { icon: '⬇', name: '导出当前库', version: '', meta: '仅导出当前选中的知识库', status: '37 页', active: false },
      { icon: '⬆', name: '从备份恢复', version: '', meta: '从 ZIP / JSON 文件恢复知识库数据', status: '', active: false },
      { icon: '🕐', name: '备份历史', version: '', meta: '查看最近 5 次自动备份记录', status: '上次: 2 天前', active: false },
    ],
    actions: ['立即备份', '打开备份目录'],
  },
};

/* ============== 渲染左侧导航 ============== */
function renderSettingsNav() {
  return SETTINGS_NAV.map(item => `
    <div class="settings-nav-item ${item.id === activeNavId ? 'settings-nav-item--active' : ''}"
         data-nav-id="${item.id}">
      <span class="settings-nav-item__icon">${item.icon}</span>
      <span>${item.label}</span>
    </div>
  `).join('');
}

/* ============== 渲染执行模式内容（特殊布局） ============== */
function renderExecModeContent() {
  const isLocal = activeExecTab === 'local';

  const tabsHtml = `
    <div class="settings-tabs">
      <button class="settings-tab ${isLocal ? 'settings-tab--active' : ''}" data-exec-tab="local">本机 CLI</button>
      <button class="settings-tab ${!isLocal ? 'settings-tab--active' : ''}" data-exec-tab="byok">本机 MiniAgent</button>
    </div>
  `;

  let bodyHtml = '';

  if (isLocal) {
    // 本机 CLI tab
    const cliCards = CLI_TOOLS.map(cli => {
      const isSel = cli.id === selectedCli;
      return `
        <div class="setting-card ${isSel ? 'setting-card--active' : ''}" data-cli-id="${cli.id}">
          <span class="setting-card__icon">${cli.icon}</span>
          <div class="setting-card__info">
            <div class="setting-card__name">
              ${cli.name}
              ${cli.version ? '<span class="setting-card__version">' + cli.version + '</span>' : ''}
            </div>
            <div class="setting-card__meta" style="color: ${cli.installed ? 'var(--accent)' : 'var(--ink-faint)'};">
              ${cli.installed ? '已安装' : '未安装'}
            </div>
            ${!cli.installed ? '<div class="setting-card__links"><button class="setting-card__link" data-action="install-cli">安装</button><button class="setting-card__link">文档</button></div>' : ''}
          </div>
          <span class="setting-card__dot"></span>
        </div>
      `;
    }).join('');

    bodyHtml = `
      <div class="settings-desc">通过扫描 PATH 自动检测，选择你希望使用的 CLI。</div>
      <div class="settings-card-grid">
        ${cliCards}
      </div>
      <div class="settings-actions">
        <button class="btn btn--ghost" id="btn-test-cli">测试</button>
        <button class="btn btn--ghost" id="btn-rescan-cli">重新扫描</button>
      </div>
    `;
  } else {
    // BYOK tab
    const providerCards = BYOK_PROVIDERS.map(p => `
      <div class="setting-card ${p.active ? 'setting-card--active' : ''}" data-provider-id="${p.id}">
        <span class="setting-card__icon">${p.icon}</span>
        <div class="setting-card__info">
          <div class="setting-card__name">
            ${p.name}
            ${p.status ? '<span class="setting-card__version" style="color: var(--accent);">' + p.status + '</span>' : ''}
          </div>
          <div class="setting-card__meta">${p.desc}</div>
          <input class="setting-card__key-input" type="text" placeholder="Base URL: ${p.urlPlaceholder}" data-provider-url="${p.id}">
          <input class="setting-card__key-input" type="password" placeholder="API Key: ${p.keyPlaceholder}" data-provider-key="${p.id}">
        </div>
        <span class="setting-card__dot"></span>
      </div>
    `).join('');

    bodyHtml = `
      <div class="settings-desc">本机 MiniAgent 是项目自带的 AI 代理，需要配置模型 API Key 才能使用。支持两种兼容格式，API Key 仅保存在当前浏览器中。</div>
      ${providerCards}
      <div class="settings-actions">
        <button class="btn btn--ghost" id="btn-test-byok">验证 Key</button>
        <button class="btn btn--ghost" id="btn-save-byok">保存配置</button>
      </div>
    `;
  }

  return `
    <div class="settings-content__header">
      <div class="settings-content__title">执行模式与模型</div>
      <div class="settings-content__subtitle">在本机 CLI 与本机 MiniAgent 之间选择。API Key 只保存在当前浏览器中。</div>
      <button class="settings-content__close" id="settings-close-btn" title="关闭">✕</button>
    </div>
    <div class="settings-content__body">
      ${tabsHtml}
      ${bodyHtml}
    </div>
  `;
}

/* ============== 渲染 MCP 服务器内容（特殊布局） ============== */
let activeMcpTool = 'claude-code';
const MCP_TOOLS = [
  { id: 'claude-code',  name: 'Claude Code',      format: 'CLI 命令',   active: true },
  { id: 'codex',        name: 'Codex',            format: 'TOML 配置',  active: false },
  { id: 'cursor',       name: 'Cursor',           format: '一键安装',    active: false },
  { id: 'vscode',       name: 'VS Code',          format: 'JSON 配置',  active: false },
  { id: 'zed',          name: 'Zed',              format: 'JSON 配置',  active: false },
  { id: 'windsurf',     name: 'Windsurf',         format: 'JSON 配置',  active: false },
];

function renderMcpServerContent() {
  const toolListHtml = MCP_TOOLS.map(t => `
    <div class="mcp-tool-item ${t.id === activeMcpTool ? 'mcp-tool-item--active' : ''}" data-mcp-tool="${t.id}">
      <span class="mcp-tool-item__icon">${t.id === activeMcpTool ? '▸' : '·'}</span>
      <span class="mcp-tool-item__name">${t.name}</span>
      <span class="mcp-tool-item__format">${t.format}</span>
    </div>
  `).join('');

  const codeExample = `<span class="mcp-code-key">claude</span> mcp add-json <span class="mcp-code-key">--scope</span> user wiki-agent <span class="mcp-code-str">'{
  "command": "wiki-mcp-server",
  "args": ["serve"],
  "env": {
    "WIKI_MCP_KEY": "<span class="mcp-code-str">wk-mcp-a8f3e2d1...</span>",
    "WIKI_DATA_DIR": "./wiki-data"
  }
}'</span>`;

  return `
    <div class="settings-content__header">
      <div class="settings-content__title">MCP 服务器</div>
      <div class="settings-content__subtitle">将知识库注册到 CLI 工具，让开发人员直接在 Claude Code / Cursor / VS Code 中与知识库交互。</div>
      <button class="settings-content__close" id="settings-close-btn" title="关闭">✕</button>
    </div>
    <div class="settings-content__body">

      <div class="mcp-section-title">MCP 访问密钥</div>
      <div class="mcp-key-input-wrap">
        <label>Key</label>
        <input type="password" value="wk-mcp-a8f3e2d1b7c4" id="mcp-key-input" placeholder="MCP 访问密钥">
        <button class="btn btn--ghost" id="mcp-key-copy" style="flex-shrink:0;">复制</button>
        <button class="btn btn--ghost" id="mcp-key-regen" style="flex-shrink:0;">重新生成</button>
      </div>
      <div class="mcp-tip-box">
        <div class="mcp-tip-box__title">此密钥代表知识库读取权限</div>
        开发人员使用此密钥将知识库 MCP 服务注册到 CLI 工具中。密钥控制当前知识库的可见范围，可按需吊销。
      </div>

      <div class="mcp-section-title">注册到 CLI 工具</div>
      <div class="mcp-tool-list" id="mcp-tool-list">
        ${toolListHtml}
      </div>

      <div class="mcp-code-block" id="mcp-code-block">
        <button class="mcp-code-block__copy" id="mcp-copy-btn">复制</button>
${codeExample}
      </div>

      <div class="mcp-tip-box">
        <div class="mcp-tip-box__title">重启客户端以加载新 Server</div>
        大多数编辑器仅在启动时加载 MCP Server。在 Cursor / VS Code / Windsurf 中，可在命令面板运行 <code style="font-family: var(--font-mono); background: var(--bg-dim); padding: 1px 4px; border-radius: 3px;">Developer: Reload Window</code> 无需完全重启。Zed 和 Claude Code 需要退出并重新打开。
      </div>

      <div class="mcp-section-title">你的助手可以做什么</div>
      <ul class="mcp-bullet-list">
        <li>读取或搜索知识库中的任意页面（Markdown / 结构化数据）</li>
        <li>获取知识图谱的实体关系，理解上下文关联</li>
        <li>基于知识库上下文回答开发问题，直接引用来源文档</li>
        <li>默认使用当前知识库，无需重复说明背景信息</li>
      </ul>

    </div>
  `;
}

/* ============== 渲染通用分区内容 ============== */
function renderGenericContent(sectionId) {
  const section = SETTINGS_CONTENT[sectionId];
  if (!section) return '<p style="color: var(--ink-faint);">内容加载中...</p>';

  const cardsHtml = section.cards.map(card => `
    <div class="setting-card ${card.active ? 'setting-card--active' : ''}" data-card-name="${card.name}">
      <span class="setting-card__icon">${card.icon}</span>
      <div class="setting-card__info">
        <div class="setting-card__name">
          ${card.name}
          ${card.version ? '<span class="setting-card__version">' + card.version + '</span>' : ''}
        </div>
        <div class="setting-card__meta">${card.meta}</div>
      </div>
      <span class="setting-card__status ${card.active ? 'setting-card__status--active' : ''}">${card.status}</span>
      <span class="setting-card__dot"></span>
    </div>
  `).join('');

  const actionsHtml = section.actions
    ? `<div class="settings-actions">
        ${section.actions.map(a => '<button class="btn btn--ghost">' + a + '</button>').join('')}
       </div>`
    : '';

  return `
    <div class="settings-content__header">
      <div class="settings-content__title">${section.title}</div>
      <div class="settings-content__subtitle">${section.subtitle}</div>
      <button class="settings-content__close" id="settings-close-btn" title="关闭">✕</button>
    </div>
    <div class="settings-content__body">
      ${cardsHtml}
      ${actionsHtml}
    </div>
  `;
}

/* ============== 渲染右侧内容（路由） ============== */
function renderSettingsContent(sectionId) {
  if (sectionId === 'exec-mode') {
    return renderExecModeContent();
  }
  if (sectionId === 'mcp-server') {
    return renderMcpServerContent();
  }
  return renderGenericContent(sectionId);
}

/* ============== 渲染完整弹窗 ============== */
function renderSettingsModal() {
  return `
    <div class="settings-overlay" id="settings-overlay" aria-hidden="true">
      <div class="settings-modal">
        <div class="settings-sidebar" id="settings-sidebar">
          ${renderSettingsNav()}
        </div>
        <div class="settings-content" id="settings-content">
          ${renderSettingsContent(activeNavId)}
        </div>
      </div>
    </div>
  `;
}

/* ============== 切换右侧内容 ============== */
function switchSettingsContent(sectionId) {
  activeNavId = sectionId;
  document.querySelectorAll('#settings-sidebar .settings-nav-item').forEach(el => {
    el.classList.toggle('settings-nav-item--active', el.dataset.navId === sectionId);
  });
  const contentEl = document.getElementById('settings-content');
  contentEl.innerHTML = renderSettingsContent(sectionId);
  bindSettingsEvents();
}

/* ============== 切换执行模式 tab ============== */
function switchExecTab(tab) {
  activeExecTab = tab;
  const contentEl = document.getElementById('settings-content');
  contentEl.innerHTML = renderSettingsContent('exec-mode');
  bindSettingsEvents();
}

/* ============== 绑定弹窗内事件 ============== */
function bindSettingsEvents() {
  // 关闭按钮
  const closeBtn = document.getElementById('settings-close-btn');
  if (closeBtn) closeBtn.addEventListener('click', closeSettings);

  // Tab 切换（执行模式）
  document.querySelectorAll('.settings-tab[data-exec-tab]').forEach(tab => {
    tab.addEventListener('click', () => switchExecTab(tab.dataset.execTab));
  });

  // MCP 工具列表点击切换
  document.querySelectorAll('[data-mcp-tool]').forEach(item => {
    item.addEventListener('click', () => {
      activeMcpTool = item.dataset.mcpTool;
      const contentEl = document.getElementById('settings-content');
      contentEl.innerHTML = renderMcpServerContent();
      bindSettingsEvents();
    });
  });

  // MCP 代码复制按钮
  const mcpCopyBtn = document.getElementById('mcp-copy-btn');
  if (mcpCopyBtn) {
    mcpCopyBtn.addEventListener('click', () => {
      const codeBlock = document.getElementById('mcp-code-block');
      const text = codeBlock.innerText.replace('复制', '').trim();
      mcpCopyBtn.textContent = '✓ 已复制';
      setTimeout(() => { mcpCopyBtn.textContent = '复制'; }, 1500);
    });
  }

  // MCP Key 复制
  const mcpKeyCopy = document.getElementById('mcp-key-copy');
  if (mcpKeyCopy) {
    mcpKeyCopy.addEventListener('click', () => {
      const input = document.getElementById('mcp-key-input');
      mcpKeyCopy.textContent = '✓ 已复制';
      setTimeout(() => { mcpKeyCopy.textContent = '复制'; }, 1500);
    });
  }

  // MCP Key 重新生成
  const mcpKeyRegen = document.getElementById('mcp-key-regen');
  if (mcpKeyRegen) {
    mcpKeyRegen.addEventListener('click', () => {
      const input = document.getElementById('mcp-key-input');
      mcpKeyRegen.textContent = '生成中...';
      mcpKeyRegen.disabled = true;
      setTimeout(() => {
        input.value = 'wk-mcp-' + Math.random().toString(36).substring(2, 14);
        mcpKeyRegen.textContent = '重新生成';
        mcpKeyRegen.disabled = false;
      }, 800);
    });
  }

  // CLI 卡片选中
  document.querySelectorAll('[data-cli-id]').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.setting-card__link')) return; // 忽略链接点击
      selectedCli = card.dataset.cliId;
      document.querySelectorAll('[data-cli-id]').forEach(c => c.classList.remove('setting-card--active'));
      card.classList.add('setting-card--active');
    });
  });

  // 安装链接
  document.querySelectorAll('[data-action="install-cli"]').forEach(link => {
    link.addEventListener('click', (e) => {
      e.stopPropagation();
      const orig = link.textContent;
      link.textContent = '安装中...';
      setTimeout(() => {
        link.textContent = '✓ 已安装';
        const meta = link.closest('.setting-card__info').querySelector('.setting-card__meta');
        if (meta) { meta.textContent = '已安装'; meta.style.color = 'var(--accent)'; }
      }, 1500);
    });
  });

  // BYOK 提供商卡片选中
  document.querySelectorAll('[data-provider-id]').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.setting-card__key-input')) return; // 忽略输入框点击
      document.querySelectorAll('[data-provider-id]').forEach(c => c.classList.remove('setting-card--active'));
      card.classList.add('setting-card--active');
    });
  });

  // 通用卡片点击（MCP / 权限 / 备份）
  document.querySelectorAll('#settings-content .setting-card[data-card-name]').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('#settings-content .setting-card').forEach(c => {
        c.classList.remove('setting-card--active');
        const s = c.querySelector('.setting-card__status');
        if (s) s.classList.remove('setting-card__status--active');
      });
      card.classList.add('setting-card--active');
      const s = card.querySelector('.setting-card__status');
      if (s) s.classList.add('setting-card__status--active');
    });
  });

  // 操作按钮
  document.querySelectorAll('#settings-content .settings-actions .btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const origText = btn.textContent;
      btn.textContent = '处理中...';
      btn.disabled = true;
      setTimeout(() => {
        btn.textContent = '✓ 完成';
        setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 1200);
      }, 1000);
    });
  });
}

/* ============== 打开/关闭弹窗 ============== */
function openSettings() {
  const overlay = document.getElementById('settings-overlay');
  if (!overlay) return;
  overlay.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeSettings() {
  const overlay = document.getElementById('settings-overlay');
  if (!overlay) return;
  overlay.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

/* ============== 初始化 ============== */
function initSettings() {
  document.body.insertAdjacentHTML('beforeend', renderSettingsModal());

  const overlay = document.getElementById('settings-overlay');
  const sidebar = document.getElementById('settings-sidebar');
  const btn = document.getElementById('settings-btn');

  if (!overlay || !btn) return;

  btn.addEventListener('click', (e) => { e.stopPropagation(); openSettings(); });

  sidebar.addEventListener('click', (e) => {
    const navItem = e.target.closest('.settings-nav-item');
    if (navItem && navItem.dataset.navId) switchSettingsContent(navItem.dataset.navId);
  });

  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeSettings(); });

  bindSettingsEvents();

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.getAttribute('aria-hidden') === 'false') closeSettings();
  });
}

document.addEventListener('DOMContentLoaded', initSettings);
