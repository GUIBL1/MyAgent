import { marked } from 'marked'

marked.use({
  gfm: true,
  breaks: false,
})

/**
 * 渲染 Markdown 文本为 HTML。
 * 流式场景下文本可能不完整（如未闭合的 code fence），
 * marked 会尽量容错，将未闭合语法当作普通文本处理。
 */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  try {
    return marked.parse(text, { async: false }) as string
  } catch {
    // 解析失败时降级为转义纯文本
    return escapeHtml(text)
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
