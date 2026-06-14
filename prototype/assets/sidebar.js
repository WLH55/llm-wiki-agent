/**
 * 共享 Sidebar 组件
 * 在所有 HTML 页面（除 index.html）中通过 <div id="sidebar"></div> + <script src="assets/sidebar.js"></script> 引入
 * 激活态根据当前页面 URL 自动判断
 */

const NAV_ITEMS = [
  { num: '01', label: '对话', href: 'chat.html' },
  { num: '02', label: '文档', href: 'documents.html' },
  { num: '03', label: '图谱', href: 'index.html' },
  { num: '04', label: '搜索', href: 'search.html' },
];

const HISTORY_ITEMS = [
  { title: 'IAP 退款流程', time: '12:34', active: true },
  { title: '投放策略优化', time: '昨天', active: false },
  { title: '钉钉多维表格', time: '昨天', active: false },
  { title: '支付系统异常', time: '3 天前', active: false },
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

  const navHtml = NAV_ITEMS.map(item => `
    <a href="${item.href}"
       class="sidebar__nav-item ${currentPage === item.href ? 'sidebar__nav-item--active' : ''}">
      <span class="sidebar__nav-num">${item.num}</span>
      <span class="sidebar__nav-label">${item.label}</span>
    </a>
  `).join('');

  const historyHtml = HISTORY_ITEMS.map(item => `
    <div class="sidebar__history-item ${item.active ? 'sidebar__history-item--active' : ''}">
      ${item.title}
    </div>
  `).join('');

  container.innerHTML = `
    <nav class="sidebar__nav">${navHtml}</nav>
    <div class="sidebar__section-title">最近对话</div>
    <div class="sidebar__history">${historyHtml}</div>
  `;
}

// 自动渲染
document.addEventListener('DOMContentLoaded', () => renderSidebar());
