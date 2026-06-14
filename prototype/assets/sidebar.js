/**
 * 共享 Sidebar 组件
 * 在所有 HTML 页面（除 index.html）中通过 <div id="sidebar"></div> + <script src="assets/sidebar.js"></script> 引入
 * 激活态根据当前页面 URL 自动判断
 *
 * 自定义配置（可选）：
 *   window.SIDEBAR_CONFIG = {
 *     historyItems: [{ id, title, time, active }],
 *     historyLabel: '最近对话' | '最近浏览' | '搜索历史',
 *     onHistoryClick: (item) => { ... },
 *     onHistoryDelete: (item) => { ... },
 *   };
 */

const NAV_ITEMS = [
  { num: '01', label: '对话', href: 'chat.html' },
  { num: '02', label: '文档', href: 'documents.html' },
  { num: '03', label: '图谱', href: 'index.html' },
  { num: '04', label: '搜索', href: 'search.html' },
];

const DEFAULT_HISTORY = [
  { id: 'c1', title: 'IAP 退款流程', time: '12:34', active: true  },
  { id: 'c2', title: '投放策略优化', time: '昨天', active: false },
  { id: 'c3', title: '钉钉多维表格', time: '昨天', active: false },
  { id: 'c4', title: '支付系统异常', time: '3 天前', active: false },
];

/**
 * 获取当前页面文件名
 * @returns {string} 当前页面文件名（如 chat.html），首页返回 index.html
 */
function getCurrentPage() {
  const path = window.location.pathname;
  const filename = path.substring(path.lastIndexOf('/') + 1);
  return filename || 'index.html';
}

/**
 * 渲染 Sidebar 到指定容器
 * @param {string} targetId 容器元素 ID，默认 'sidebar'
 */
function renderSidebar(targetId = 'sidebar') {
  const container = document.getElementById(targetId);
  if (!container) return;

  const currentPage = getCurrentPage();
  const config = window.SIDEBAR_CONFIG || {};
  const historyItems = config.historyItems || DEFAULT_HISTORY;
  const historyLabel = config.historyLabel || '最近对话';

  const navHtml = NAV_ITEMS.map(item => `
    <a href="${item.href}"
       class="sidebar__nav-item ${currentPage === item.href ? 'sidebar__nav-item--active' : ''}">
      <span class="sidebar__nav-num">${item.num}</span>
      <span class="sidebar__nav-label">${item.label}</span>
    </a>
  `).join('');

  const historyHtml = historyItems.map((item, idx) => `
    <div class="sidebar__history-item ${item.active ? 'sidebar__history-item--active' : ''}"
         data-id="${item.id || idx}"
         data-idx="${idx}">
      <span class="sidebar__history-title">${item.title}</span>
      ${item.active ? '' : `<span class="sidebar__history-time">${item.time || ''}</span>`}
      ${config.onHistoryDelete ? `<button class="sidebar__history-delete" data-action="delete" title="删除">×</button>` : ''}
    </div>
  `).join('');

  container.innerHTML = `
    <nav class="sidebar__nav">${navHtml}</nav>
    <div class="sidebar__section-title">${historyLabel}</div>
    <div class="sidebar__history">${historyHtml}</div>
  `;

  // 绑定点击事件
  if (config.onHistoryClick || config.onHistoryDelete) {
    container.querySelectorAll('.sidebar__history-item').forEach(el => {
      el.addEventListener('click', (e) => {
        // 删除按钮点击
        if (e.target.dataset.action === 'delete' && config.onHistoryDelete) {
          e.stopPropagation();
          const id = el.dataset.id;
          const idx = parseInt(el.dataset.idx, 10);
          config.onHistoryDelete(historyItems[idx], idx);
          return;
        }
        // 普通点击
        if (config.onHistoryClick) {
          const idx = parseInt(el.dataset.idx, 10);
          config.onHistoryClick(historyItems[idx], idx);
        }
      });
    });
  }
}

// 自动渲染
document.addEventListener('DOMContentLoaded', () => renderSidebar());
