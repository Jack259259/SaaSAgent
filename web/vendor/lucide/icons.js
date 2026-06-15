// icons.js — 内联 Lucide 图标(ISC 许可,见 ../README.md)。
// 仅取开源 SVG 路径数据并内联,不引公网;返回的是自有 SVG 字符串(非用户内容,可安全 x-html)。

const PATHS = {
  menu: '<line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
};

/**
 * 返回内联 SVG 字符串(24x24,currentColor 描边)。
 * @param {string} name 图标名(menu | sun | moon)
 * @returns {string}
 */
export function icon(name) {
  const p = PATHS[name] || '';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
}
