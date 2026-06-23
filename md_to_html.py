"""简单 Markdown → HTML 转换器（纯 Python，无外部依赖）
支持：h1-h3, bold, italic, list, link, blockquote, code, paragraph
"""
import re


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_to_html(md_text: str) -> str:
    """将 Markdown 文本转为 HTML 片段"""
    lines = md_text.split("\n")
    html_lines = []
    in_list = False
    in_ol = False
    i = 0

    while i < len(lines):
        line = lines[i]

        # 空行
        if not line.strip():
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            i += 1
            continue

        # 标题
        m_h1 = re.match(r"^#\s+(.+)$", line)
        m_h2 = re.match(r"^##\s+(.+)$", line)
        m_h3 = re.match(r"^###\s+(.+)$", line)
        if m_h1:
            if in_list:
                html_lines.append("</ul>"); in_list = False
            if in_ol:
                html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<h1>{_process_inline(m_h1.group(1))}</h1>")
            i += 1; continue
        if m_h2:
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<h2>{_process_inline(m_h2.group(1))}</h2>")
            i += 1; continue
        if m_h3:
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<h3>{_process_inline(m_h3.group(1))}</h3>")
            i += 1; continue

        # 无序列表
        m_ul = re.match(r"^-\s+(.+)$", line)
        if m_ul:
            if not in_list:
                if in_ol: html_lines.append("</ol>"); in_ol = False
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_process_inline(m_ul.group(1))}</li>")
            i += 1; continue

        # 有序列表
        m_ol = re.match(r"^\d+\.\s+(.+)$", line)
        if m_ol:
            if not in_ol:
                if in_list: html_lines.append("</ul>"); in_list = False
                html_lines.append("<ol>")
                in_ol = True
            html_lines.append(f"<li>{_process_inline(m_ol.group(1))}</li>")
            i += 1; continue

        # 引用块
        m_quote = re.match(r"^>\s*(.*)$", line)
        if m_quote:
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<blockquote>{_process_inline(m_quote.group(1))}</blockquote>")
            i += 1; continue

        # 水平线
        if re.match(r"^---+\s*$", line) or re.match(r"^\*{3,}\s*$", line):
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append("<hr>")
            i += 1; continue

        # 普通段落
        if in_list: html_lines.append("</ul>"); in_list = False
        if in_ol: html_lines.append("</ol>"); in_ol = False
        html_lines.append(f"<p>{_process_inline(line)}</p>")
        i += 1

    if in_list:
        html_lines.append("</ul>")
    if in_ol:
        html_lines.append("</ol>")

    return "\n".join(html_lines)


def _process_inline(text: str) -> str:
    """处理行内格式：bold, italic, code, link"""
    text = _escape_html(text)

    # 链接 [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # 粗体 **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # 斜体 *text*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

    # 行内代码 `code`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    return text


def md_to_full_html(md_text: str, title: str = "热回收技术小报") -> str:
    """生成完整 HTML 文档（适合直接打开或打印为 PDF）"""
    body = md_to_html(md_text)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
    body {{
        max-width: 800px; margin: 40px auto; padding: 20px 40px;
        font-family: "SimSun", "Songti SC", "STSong", serif;
        font-size: 16px; line-height: 1.9; color: #3F3A36;
        background: #FFF6EC;
    }}
    h1 {{
        font-size: 28px; color: #FF8D65; border-bottom: 3px solid #FF8D65;
        padding-bottom: 10px; margin-top: 0;
    }}
    h2 {{
        font-size: 22px; color: #3F3A36; border-left: 4px solid #FF8D65;
        padding-left: 14px; margin-top: 28px;
    }}
    h3 {{ font-size: 18px; color: #7A5C4B; margin-top: 20px; }}
    p {{ margin: 8px 0; }}
    ul, ol {{ padding-left: 24px; }}
    li {{ margin: 4px 0; }}
    strong {{ color: #FF8D65; }}
    blockquote {{
        border-left: 3px solid #FFC4AF; padding-left: 16px;
        color: #7A5C4B; font-style: italic; margin: 16px 0;
    }}
    code {{
        background: #FFC4AF; padding: 2px 6px; border-radius: 4px;
        font-size: 14px;
    }}
    a {{ color: #FF8D65; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    hr {{ border: none; border-top: 1px solid #FFC4AF; margin: 20px 0; }}
    @media print {{
        body {{ background: #fff; }}
    }}
</style>
</head>
<body>
{body}
</body>
</html>"""
