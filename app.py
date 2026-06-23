"""
暖通空调中的热回收技术检索智能体 — Streamlit 前端
流程：关键词理解 → Bing/百度搜索 → 相关性筛选 → 正文读取 → 总结小报 → 展示
信息架构：语言 → Hero → 核心检索 → 推荐关键词 → 结果概览 → 结果+小报分栏 → 课程定位 → 检索流程 → 知识卡 → 调试 → 页脚
设计风格：橘子汽水 — 温暖、清爽、柔和，检索框为页面视觉核心
"""
import re
import html as _html
import urllib.parse
import streamlit as st
from search_engine import extract_keywords, expand_keywords, expand_query, multi_query_search, search_bing, search_baidu, enrich_results_with_content
from ranker import pre_filter_and_score, post_read_filter_and_score, get_domain_category
from summarizer import generate_summary
from md_to_html import md_to_full_html


def _clean_snippet(text: str, max_len: int = 300) -> str:
    """清洗摘要/正文：去 HTML 标签、去代码块、转义、截断"""
    if not text:
        return ""
    # 1) 去掉 Markdown 代码块 ```
    text = re.sub(r"```[\s\S]*?```", "", text)
    # 2) 去掉行内代码 `code`
    text = re.sub(r"`[^`]+`", "", text)
    # 3) 去掉以 4空格/Tab 开头的代码行
    text = "\n".join(line for line in text.split("\n") if not re.match(r"^\s{4,}", line) and not line.startswith("\t"))
    # 4) 去掉所有 HTML/XML 标签
    text = re.sub(r"<[^>]*>", "", text)
    # 5) 还原 HTML 实体
    text = _html.unescape(text)
    # 6) 清理多余空白
    text = re.sub(r"\s+", " ", text).strip()
    # 7) 截断
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text

st.set_page_config(
    page_title="暖通空调中的热回收技术检索智能体",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "lang" not in st.session_state:
    st.session_state.lang = "zh"

# ======================== CSS ========================
st.markdown("""
<style>
    /* ===== 全局强制字体与字号 ===== */
    .stApp {
        font-family: "SimSun", "Songti SC", "STSong", serif !important;
        font-size: 20px !important;
        background: #FFEBD5 !important;
    }
    * { font-family: "SimSun", "Songti SC", "STSong", serif !important; }
    .main > .block-container { padding: 0 2rem 2.5rem !important; max-width: 1320px; margin: 0 auto; }

    /* ===== Hero ===== */
    .hero-section {
        background: linear-gradient(160deg, #FFEBD5 0%, #FFC4AF 60%, #FFB89A 100%);
        border-radius: 28px; padding: 32px 44px; margin: 8px 0 24px;
        display: flex; flex-wrap: wrap; gap: 28px;
        align-items: center; justify-content: space-between;
    }
    .hero-left { flex: 1; min-width: 300px; }
    .hero-title {
        font-size: 72px !important; line-height: 1.12 !important;
        font-weight: 900 !important; color: #FF8D65 !important;
        margin: 0 0 10px !important; letter-spacing: 1px;
    }
    .hero-subtitle {
        font-size: 28px !important; line-height: 1.6 !important;
        color: #7A5C4B !important; margin: 0 0 20px !important;
    }
    .hero-tags { display: flex; gap: 12px; flex-wrap: wrap; }
    .hero-tag {
        font-size: 18px; font-weight: 600; padding: 10px 24px; border-radius: 30px;
        border: 1.5px solid #FFC4AF;
    }
    .hero-tag:nth-child(1) { background: #8FDBE0; color: #3F3A36; border-color: #6BC4C9; }
    .hero-tag:nth-child(2) { background: #FFF6EC; color: #3F3A36; }
    .hero-tag:nth-child(3) { background: #FFC4AF; color: #3F3A36; }
    .hero-right { flex-shrink: 0; }
    .status-card {
        background: #FFFFFF; border-radius: 18px; padding: 18px 26px;
        border: 1.5px solid #FFC4AF;
        box-shadow: 0 4px 18px rgba(255,141,101,0.10);
    }
    .status-card-title { font-size: 16px; font-weight: 700; color: #FF8D65; margin-bottom: 12px; text-align: center; letter-spacing: 1px; }
    .status-card-item { font-size: 15px; color: #3F3A36; padding: 5px 0; border-bottom: 1px dotted #FFC4AF; text-align: center; }
    .status-card-item:last-child { border-bottom: none; }

    /* ===== 核心搜索面板 ===== */
    .search-panel {
        background: #FFF6EC;
        padding: 28px 40px !important;
        border-radius: 28px !important;
        margin: 0 auto 24px;
        box-shadow: 0 16px 40px rgba(255,141,101,0.22);
        border: 2px solid rgba(255,141,101,0.35);
        max-width: 1000px;
        overflow: visible !important;
        box-sizing: border-box !important;
    }
    .search-title {
        font-size: 42px !important; line-height: 1.3 !important;
        font-weight: 900 !important; color: #FF8D65 !important;
        margin: 0 0 8px !important; text-align: center;
    }
    .search-desc {
        font-size: 21px !important; line-height: 1.6 !important;
        font-weight: 500 !important; color: #7A5C4B !important;
        text-align: center; margin: 0 0 22px !important;
    }

    /* ===== 主搜索输入框（强制覆盖 Streamlit，避免文字裁切） ===== */
    .stTextInput div[data-baseweb="input"] {
        overflow: visible !important;
        min-height: 64px !important;
        height: auto !important;
    }
    .stTextInput input,
    div[data-baseweb="input"] input {
        font-size: 26px !important;
        height: auto !important;
        min-height: 56px !important;
        line-height: normal !important;
        padding: 12px 20px !important;
        border-radius: 16px !important;
        border: 2px solid #FF8D65 !important;
        box-sizing: border-box !important;
        font-family: "SimSun", "Songti SC", "STSong", serif !important;
        background: #FFFFFF !important; color: #3F3A36 !important;
        transition: box-shadow 0.25s ease, border-color 0.25s ease !important;
    }
    .stTextInput input::placeholder,
    div[data-baseweb="input"] input::placeholder {
        font-size: 24px !important; color: #B07A63 !important;
        line-height: normal !important;
    }
    .stTextInput input:focus,
    div[data-baseweb="input"] input:focus {
        border-color: #FF8D65 !important;
        border-width: 2px !important;
        box-shadow: 0 0 0 4px rgba(255, 141, 101, 0.22) !important;
    }
    .stTextInput label {
        font-size: 16px !important; color: #7A5C4B !important; font-weight: 600 !important;
    }

    /* ===== 主搜索按钮（强制覆盖） ===== */
    .stButton > button {
        height: auto !important; min-height: 64px !important;
        font-size: 26px !important; line-height: normal !important;
        font-weight: 900 !important;
        border-radius: 999px !important;
        padding: 12px 24px !important;
        white-space: nowrap !important;
        box-sizing: border-box !important;
        font-family: "SimSun", "Songti SC", "STSong", serif !important;
        background: linear-gradient(135deg, #FF8D65, #FFC4AF) !important;
        color: #fff !important; border: none !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 6px 22px rgba(255,141,101,0.35) !important;
        letter-spacing: 0.5px;
    }
    .stButton > button p {
        font-size: 26px !important; line-height: normal !important;
        font-weight: 900 !important;
    }
    .stButton > button:hover {
        transform: scale(1.05);
        box-shadow: 0 10px 32px rgba(255,141,101,0.45) !important;
    }

    /* ===== 参数行 ===== */
    .stNumberInput label,
    .stNumberInput label p {
        font-size: 24px !important;
        font-weight: 800 !important;
        color: #3F3A36 !important;
        font-family: "SimSun", "Songti SC", "STSong", serif !important;
    }
    .stNumberInput input,
    div[data-baseweb="input"] input[type="number"] {
        font-size: 24px !important;
        height: 56px !important; min-height: 56px !important;
        padding: 8px 16px !important;
        border-radius: 14px !important;
        font-family: "SimSun", "Songti SC", "STSong", serif !important;
        border: 1.5px solid #FFC4AF !important;
        background: #FFFFFF !important; color: #3F3A36 !important;
    }
    .stNumberInput input:focus,
    div[data-baseweb="input"] input[type="number"]:focus {
        border-color: #FF8D65 !important;
        box-shadow: 0 0 0 3px rgba(255,141,101,0.10) !important;
    }

    /* ===== 模块标题 ===== */
    .section-title {
        font-size: 34px !important; font-weight: 900 !important;
        color: #3F3A36 !important; margin: 0 0 18px 0;
        padding-bottom: 10px; border-bottom: 3px solid #FF8D65;
    }

    /* ===== 推荐关键词 ===== */
    .keyword-tag {
        font-size: 18px !important; font-weight: 600;
        display: inline-block; padding: 11px 22px; border-radius: 25px;
        border: none; margin: 6px 10px 6px 0;
        transition: all 0.2s ease; background: #FFF6EC; color: #3F3A36;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        cursor: pointer;
    }
    .keyword-tag:hover {
        transform: translateY(-2px) scale(1.03);
        filter: brightness(1.06);
        box-shadow: 0 4px 14px rgba(0,0,0,0.10);
    }
    .keyword-tag:active {
        transform: translateY(1px) scale(0.98);
        filter: brightness(0.97);
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }

    /* ===== 关键词扩展面板标签 ===== */
    .kw-tag-original {
        display: inline-block; padding: 4px 16px; border-radius: 12px;
        font-size: 19px; font-weight: 700; background: #FF8D65; color: #fff;
        margin: 2px 4px;
    }
    .kw-tag-zh {
        display: inline-block; padding: 4px 12px; border-radius: 10px;
        font-size: 17px; background: #FFC4AF; color: #3F3A36; margin: 2px 4px;
    }
    .kw-tag-en {
        display: inline-block; padding: 4px 12px; border-radius: 10px;
        font-size: 17px; background: #8FDBE0; color: #3F3A36; margin: 2px 4px;
    }
    .kw-tag-academic {
        display: inline-block; padding: 4px 12px; border-radius: 10px;
        font-size: 17px; background: #FFF6EC; color: #3F3A36;
        border: 1px solid #FF8D65; margin: 2px 4px;
    }

    /* ===== 结果概览 ===== */
    .metric-row { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .metric-card {
        flex: 1; min-width: 150px; background: #FFF6EC; border-radius: 18px;
        padding: 22px 26px; border: 1.5px solid #FFC4AF;
        box-shadow: 0 2px 8px rgba(122,92,75,0.06);
    }
    .metric-card-label { font-size: 16px; color: #7A5C4B; margin-bottom: 8px; font-weight: 600; }
    .metric-card-value { font-size: 32px; font-weight: 800; color: #FF8D65; }

    /* ===== 结果 + 小报 分栏布局 ===== */
    .results-layout { display: flex; gap: 24px; flex-wrap: wrap; }
    .results-left { flex: 6; min-width: 380px; }
    .results-right { flex: 4; min-width: 320px; }

    /* ===== 小报 ===== */
    .report-section {
        background: #FFF6EC; border-left: 5px solid #FF8D65;
        border-radius: 22px; padding: 24px; margin-bottom: 24px; overflow: hidden;
    }
    .report-section-title {
        font-size: 38px !important; font-weight: 900 !important;
        color: #FF8D65 !important; line-height: 1.3 !important;
        margin: 0 0 18px !important;
        font-family: "SimSun", "Songti SC", "STSong", serif !important;
    }
    .report-title-row {
        display: flex; align-items: center; justify-content: flex-start;
        gap: 16px; margin-bottom: 18px; flex-wrap: wrap;
    }
    .report-title-row .report-section-title { margin: 0 !important; }
    .report-export-btn {
        margin-left: auto !important;
    }
    .report-export-btn .stDownloadButton button {
        font-size: 18px !important; font-weight: 700 !important;
        padding: 10px 22px !important; border-radius: 12px !important;
        background: #FF8D65 !important; color: #fff !important;
        border: none !important; cursor: pointer !important;
        font-family: "SimSun", "Songti SC", "STSong", serif !important;
        transition: all 0.2s ease !important;
    }
    .report-export-btn .stDownloadButton button:hover {
        background: #E07850 !important;
    }
    .report-body {
        font-size: 20px !important; line-height: 1.8 !important;
        background: #FFFFFF; border-radius: 14px; padding: 22px 26px;
        color: #3F3A36; max-height: 70vh; overflow-y: auto;
    }
    .report-body h1 { font-size: 24px; font-weight: 900; color: #FF8D65; border-bottom: 2px solid #FFC4AF; padding-bottom: 8px; margin: 0 0 14px; }
    .report-body h2 { font-size: 22px; font-weight: 900; color: #3F3A36; margin: 20px 0 10px; padding-left: 14px; border-left: 4px solid #FF8D65; }
    .report-body h3 { font-size: 20px; color: #7A5C4B; margin: 16px 0 8px; }
    .report-body p, .report-body li { font-size: 21px; color: #3F3A36; line-height: 1.9; }
    .report-body strong { color: #FF8D65; }
    .report-body blockquote { border-left: 3px solid #FFC4AF; padding-left: 18px; color: #7A5C4B; font-size: 18px; margin: 18px 0 0; font-style: italic; }

    /* ===== 结果卡片 ===== */
    .result-card {
        background: #FFFFFF; border: 1px solid #FFC4AF; border-radius: 18px;
        padding: 20px 24px; margin-bottom: 14px;
        border-left: 5px solid #FF8D65;
        box-shadow: 0 2px 8px rgba(122,92,75,0.05);
        transition: all 0.25s ease;
    }
    .result-card:hover { box-shadow: 0 10px 28px rgba(255,141,101,0.18); transform: translateY(-2px); }
    .result-index {
        display: inline-block; background: #FF8D65; color: #fff;
        font-size: 17px; font-weight: 700; padding: 5px 14px;
        border-radius: 12px; margin-right: 12px; min-width: 36px; text-align: center;
    }
    .result-title,
    .result-title a {
        font-size: 28px !important; font-weight: 900 !important;
        line-height: 1.4 !important; margin-bottom: 10px;
    }
    .result-title a { color: #3F3A36; text-decoration: none; transition: color 0.15s; }
    .result-title a:hover { color: #FF8D65; text-decoration: underline; }
    .result-meta { font-size: 16px; color: #7A5C4B; margin-bottom: 12px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
    .result-domain { color: #8FDBE0; font-weight: 600; background: #E6F9FA; padding: 4px 12px; border-radius: 8px; font-size: 16px; }
    .source-badge { display: inline-block; padding: 4px 12px; border-radius: 8px; font-size: 15px; font-weight: 600; background: #FFC4AF; color: #3F3A36; }
    .result-snippet {
        font-size: 20px !important; line-height: 1.8 !important;
        color: #3F3A36; margin-bottom: 14px;
        display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden;
    }
    .result-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
    .score-badge { display: inline-block; background: #8FDBE0; color: #3F3A36; font-size: 17px; font-weight: 700; padding: 5px 16px; border-radius: 20px; }
    .open-link a { font-size: 20px; color: #FF8D65; text-decoration: none; font-weight: 700; }
    .open-link a:hover { text-decoration: underline; }

    /* ===== 正文摘录 ===== */
    .content-detail { font-size: 20px !important; line-height: 1.8 !important; background: #FFF6EC; border: 1px solid #FFC4AF; border-radius: 12px; padding: 16px 20px; margin-top: 14px; color: #5A4A3E; }
    .content-detail-label { font-size: 16px; font-weight: 700; color: #FF8D65; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px; }

    /* ===== 信息卡片 ===== */
    .info-card {
        font-size: 20px !important; line-height: 1.8 !important;
        background: #FFFFFF; border-radius: 18px; padding: 24px 28px;
        border: 1.5px solid #FFC4AF; box-shadow: 0 2px 10px rgba(122,92,75,0.06); color: #3F3A36;
    }
    .info-card-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px; }
    .info-card-item { flex: 1; min-width: 200px; background: #FFF6EC; border-radius: 16px; padding: 22px 24px; border: 1.5px solid #FFC4AF; text-align: center; }
    .info-card-item-title { font-size: 20px; font-weight: 700; color: #FF8D65; margin-bottom: 8px; }
    .info-card-item-desc { font-size: 17px; color: #7A5C4B; line-height: 1.7; }

    /* ===== 流程 ===== */
    .flow-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 28px; }
    .flow-card {
        font-size: 20px !important; line-height: 1.8 !important;
        flex: 1; min-width: 140px; border-radius: 16px; padding: 22px 16px;
        text-align: center; border: 1.5px solid rgba(122,92,75,0.1);
        box-shadow: 0 2px 8px rgba(122,92,75,0.05);
    }
    .flow-card:nth-child(5n+1) { background: #FFC4AF; color: #3F3A36; }
    .flow-card:nth-child(5n+2) { background: #8FDBE0; color: #3F3A36; }
    .flow-card:nth-child(5n+3) { background: #FFF6EC; color: #3F3A36; border-color: #FFC4AF; }
    .flow-card:nth-child(5n+4) { background: #FFC4AF; color: #3F3A36; }
    .flow-card:nth-child(5n+0) { background: #8FDBE0; color: #3F3A36; }
    .flow-card-num { font-size: 38px; font-weight: 800; opacity: 0.45; margin-bottom: 6px; }
    .flow-card-label { font-size: 20px; font-weight: 700; }
    .flow-card-desc { font-size: 16px; margin-top: 6px; opacity: 0.7; }

    /* ===== 知识卡 ===== */
    .knowledge-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px; }
    .knowledge-card {
        font-size: 20px !important; line-height: 1.8 !important;
        flex: 1; min-width: 220px; background: #FFFFFF; border-radius: 18px;
        padding: 22px 24px; border: 1.5px solid #FFC4AF;
        box-shadow: 0 2px 8px rgba(122,92,75,0.05);
    }
    .knowledge-card-title { font-size: 20px; font-weight: 700; color: #FF8D65; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 2px solid #FFC4AF; }
    .knowledge-card-desc { font-size: 17px; color: #5A4A3E; line-height: 1.8; }

    /* ===== 页脚 ===== */
    .footer { text-align: center; font-size: 16px; color: #7A5C4B; padding: 24px 0 12px; margin-top: 32px; border-top: 1px solid #FFC4AF; }

    /* ===== 杂项 / Streamlit 原生控件覆盖 ===== */
    hr { border-color: #FFC4AF !important; margin: 24px 0 !important; }
    .stSpinner > div { border-top-color: #FF8D65 !important; }
    section[data-testid="stExpander"] { background: #FFF6EC; border: 1px solid #FFC4AF; border-radius: 16px !important; margin-top: 24px; }
    section[data-testid="stExpander"] summary { font-size: 20px !important; color: #7A5C4B !important; }
    .empty-state { text-align: center; padding: 60px 20px; }
    .empty-state .icon { font-size: 64px; margin-bottom: 20px; }
    .empty-state .text { font-size: 24px; color: #7A5C4B; }
    .stInfo > div { background: #FFF6EC !important; border: 1px solid #FFC4AF !important; color: #3F3A36 !important; font-size: 20px !important; border-radius: 14px !important; }
    .stError > div { background: #FFF6EC !important; border: 1px solid #ff6b6b !important; color: #3F3A36 !important; border-radius: 14px !important; font-size: 20px !important; }
    .stSelectbox label { font-size: 18px !important; color: #7A5C4B !important; }
    .result-area-notice { font-size: 20px; color: #7A5C4B; margin-bottom: 20px; line-height: 1.8; }
</style>
""", unsafe_allow_html=True)


# ======================== 多语言 ========================
L = {
    "zh": {
        "search_panel_title": "🔎 开始检索热回收技术资料",
        "search_panel_desc": "输入关键词后，系统将自动检索相关资料，并调用 DeepSeek API 生成技术小报。",
        "search_placeholder": "例如：全热交换器",
        "search_btn": "开始检索并生成小报",
        "search_n": "搜索候选数量",
        "read_k": "读取网页数量",
        "search_n_help": "搜索引擎返回的候选结果条数",
        "read_k_help": "从候选结果中读取并提取正文的网页数量",
        "spinner": "正在联网搜索、提取正文、生成小报……",
        "no_results": "搜索引擎未返回结果，请尝试更换关键词或稍后重试。",
        "search_error": "搜索异常",
        "result_notice": "系统已根据关键词检索资料，并优先展示高相关性结果。",
        "metric_kw": "当前关键词", "metric_results": "检索结果数量",
        "metric_pages": "读取网页数量", "metric_report": "小报状态",
        "metric_yes": "✅ 已生成", "metric_no": "❌ 未生成",
        "report_empty": "暂无小报，请先输入关键词并执行检索。",
        "report_title": "热回收技术小报总结",
        "results_title": "搜索结果",
        "rec_kw_title": "💡 可直接尝试的检索关键词",
        "debug_title": "调试信息", "debug_engine": "搜索引擎",
        "debug_kw_hits": "关键词命中情况", "debug_kw_hit_line": "在全量结果中共命中",
        "debug_rank_basis": "排序依据", "debug_excluded": "排除的无效结果",
        "debug_quality": "正文质量过滤", "debug_quality_none": "无",
        "source_label": "打开来源 →", "content_label": "页面正文摘录",
        "empty_text": "输入关键词，开始热回收技术研究",
    },
    "en": {
        "search_panel_title": "🔎 Start Searching Heat Recovery Materials",
        "search_panel_desc": "Enter keywords and the system will automatically search, extract, and generate a technical report.",
        "search_placeholder": "e.g.: heat recovery ventilation energy saving",
        "search_btn": "Search & Generate Report",
        "search_n": "Candidate count", "read_k": "Pages to read",
        "search_n_help": "Number of search results to return",
        "read_k_help": "Number of top pages to extract and summarize",
        "spinner": "Searching, extracting, generating report...",
        "no_results": "No results. Try different keywords.",
        "search_error": "Search error",
        "result_notice": "Results are ranked by relevance based on your keywords.",
        "metric_kw": "Keyword", "metric_results": "Results",
        "metric_pages": "Pages Read", "metric_report": "Report",
        "metric_yes": "✅ Generated", "metric_no": "❌ None",
        "report_empty": "No report yet. Enter keywords and search.",
        "report_title": "Heat Recovery Technology Report",
        "results_title": "Search Results",
        "rec_kw_title": "💡 Suggested Keywords",
        "debug_title": "Debug Info", "debug_engine": "Engine",
        "debug_kw_hits": "Keyword Hits", "debug_kw_hit_line": "total hits",
        "debug_rank_basis": "Ranking", "debug_excluded": "Excluded",
        "debug_quality": "Quality Filter", "debug_quality_none": "None",
        "source_label": "Open →", "content_label": "Page Excerpt",
        "empty_text": "Enter keywords to search heat recovery technology",
    },
}

def t(key): return L.get(st.session_state.lang, L["zh"]).get(key, key)

CAT_LABELS = {
    "gov": "🏛 政府", "edu": "🎓 高校", "research": "🔬 研究机构",
    "org": "🏢 行业协会", "news": "📰 新闻媒体", "enterprise": "🏭 企业平台", "normal": "🌐 网站",
}

METHOD_LABELS = {"trafilatura": "📄 trafilatura", "bs4": "📄 BS4", "none": "—"}


# ======================== UI 渲染函数 ========================

def render_lang_switcher():
    col = st.columns([5, 1])[1]
    with col:
        nl = st.selectbox("Lang", ["zh", "en"],
            index=0 if st.session_state.lang == "zh" else 1,
            format_func=lambda x: "🇨🇳 中文" if x == "zh" else "🇺🇸 English",
            key="lang_sel", label_visibility="collapsed")
        if nl != st.session_state.lang:
            st.session_state.lang = nl; st.rerun()


def render_hero():
    st.markdown("""
    <div class="hero-section">
        <div class="hero-left">
            <h1 class="hero-title">暖通空调中的热回收技术检索智能体</h1>
            <p class="hero-subtitle">聚焦热回收技术资料检索、网页信息提炼与技术小报生成。</p>
            <div class="hero-tags">
                <span class="hero-tag">♨️ 热回收技术</span>
                <span class="hero-tag">🏠 暖通空调节能</span>
                <span class="hero-tag">🤖 DeepSeek 智能总结</span>
            </div>
        </div>
        <div class="hero-right">
            <div class="status-card">
                <div class="status-card-title">✦ 课程项目信息 ✦</div>
                <div class="status-card-item">📘 课程项目</div>
                <div class="status-card-item">🔎 AI 检索</div>
                <div class="status-card-item">📰 技术小报</div>
                <div class="status-card-item">📝 知识提炼</div>
            </div>
        </div>
    </div>""", unsafe_allow_html=True)


def render_search_panel():
    """核心搜索面板"""
    c1, c2 = st.columns([3, 1])
    with c1:
        query = st.text_input("q", placeholder=t("search_placeholder"),
            key="query_input", label_visibility="collapsed")
    with c2:
        search_clicked = st.button(f"🔎 {t('search_btn')}", type="primary",
            use_container_width=True, key="search_btn")

    st.markdown('<div style="margin-top:14px;"></div>', unsafe_allow_html=True)
    p1, p2 = st.columns([1, 1])
    with p1:
        sn = st.number_input(t("search_n"), 5, 50, 20, 5,
            key="search_n_input", help=t("search_n_help"))
    with p2:
        rk = st.number_input(t("read_k"), 1, 15, 8, 1,
            key="read_k_input", help=t("read_k_help"))
    return query, sn, rk, search_clicked, "综合搜索"


_RECOMMENDED_KEYWORDS = [
    "热回收", "转轮热回收", "板翅式换热器", "板式换热器",
    "余热回收", "全热交换器", "新风换气机",
]

# 背景色（青绿 → 浅橙 → 浅米白 交替循环）
_BG_COLORS = ["#8FDBE0", "#FFC4AF", "#FFF6EC"]


def render_recommended_keywords():
    st.markdown(f'<p style="font-size:24px;font-weight:700;color:#3F3A36;margin:0 0 16px;">{t("rec_kw_title")}</p>', unsafe_allow_html=True)
    tags_html = " ".join(
        f'<a href="?kw={urllib.parse.quote(kw)}" class="keyword-tag" '
        f'style="text-decoration:none;cursor:pointer;background:{_BG_COLORS[i % 3]};color:#3F3A36;">{kw}</a>'
        for i, kw in enumerate(_RECOMMENDED_KEYWORDS)
    )
    st.markdown(f'<div style="margin-bottom:20px;">{tags_html}</div>', unsafe_allow_html=True)


def render_metric_cards(status, has_report):
    st.markdown('<div class="metric-row">', unsafe_allow_html=True)
    search_queries = status.get("search_queries", [])
    if search_queries:
        expansion_str = f"{len(search_queries)}个query"
    else:
        expansion_str = "无扩展"
    for icon, val, label in [
        ("🔑", f"{status.get('query','N/A')}", t("metric_kw")),
        ("🔍", status.get("crawled","N/A"), "搜索候选数量"),
        ("📑", status.get("pre_filtered_count","N/A"), "初筛后结果"),
        ("📖", status.get("successfully_read","N/A"), "成功读取正文"),
        ("🤖", status.get("deepseek_input","N/A"), "DeepSeek 总结来源"),
        ("🔀", expansion_str, "多query搜索"),
    ]:
        st.markdown(f'<div class="metric-card"><div class="metric-card-label">{icon} {label}</div><div class="metric-card-value">{val}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    # 显示扩展 query
    if search_queries:
        queries_html = " ".join(f'<span class="keyword-tag">{q}</span>' for q in search_queries)
        st.markdown(f'<div style="margin-bottom:20px;"><span style="font-size:18px;font-weight:600;color:#7A5C4B;">🔀 扩展搜索词：</span>{queries_html}</div>', unsafe_allow_html=True)


def render_report_card(summary):
    if not summary:
        st.info(f"📰 {t('report_empty')}")
        return
    st.markdown('<div class="report-section">', unsafe_allow_html=True)

    # 标题行：标题 + 导出按钮
    st.markdown(f'''
    <div class="report-title-row">
        <div class="report-section-title">📰 {t("report_title")}</div>
        <div class="report-export-btn">''', unsafe_allow_html=True)
    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.download_button(
            label="📥 MD导出",
            data=summary,
            file_name="热回收技术小报.md",
            mime="text/markdown",
            key="export_report_md",
            help="下载为 Markdown 文件",
        )
    with col_b:
        html_content = md_to_full_html(summary)
        st.download_button(
            label="📄 可读版导出",
            data=html_content,
            file_name="热回收技术小报.html",
            mime="text/html",
            key="export_report_html",
            help="下载为 HTML 文件，浏览器中打开后可打印为 PDF",
        )
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="report-body">{summary}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_result_card(item):
    # 从外部数据取值并统一 HTML 转义
    title = _html.escape((item.get("title") or item.get("name") or "无标题").strip())
    url = (item.get("url") or item.get("link") or "#").strip()
    domain_raw = item.get("domain", "").strip()
    if domain_raw:
        domain = _html.escape(domain_raw)
    elif url and url != "#":
        m = re.match(r'https?://([^/]+)', url)
        domain = _html.escape(m.group(1)) if m else "未知域名"
    else:
        domain = "未知域名"
    rank = item.get("rank", 0)
    source_id = item.get("source_id", f"#{rank}")
    final_score = item.get("final_score", 0)
    source_type = item.get("source_type", "未知")
    page_content = item.get("page_content", "")
    has_content = item.get("has_content", False)
    method = item.get("extract_method", "none")
    method_label = METHOD_LABELS.get(method, "无法提取")
    engine = item.get("engine", "").strip()
    pdate = item.get("publish_date", "").strip()
    if pdate:
        pdate = _html.escape(pdate)

    card = f"""<div class="result-card">
        <div style="display:flex;align-items:flex-start;gap:10px;">
            <span class="result-index">{source_id}</span>
            <span class="result-score">⭐{final_score:.1f}</span>
            <div style="flex:1;">
                <div class="result-title"><a href="{url}" target="_blank">{title}</a></div>
                <div class="result-meta">
                    <span class="result-domain">{domain}</span>
                    <span style="font-size:16px;opacity:0.7;">{source_type}</span>
                    <span style="font-size:16px;opacity:0.7;">{method_label}</span>"""
    if engine:
        card += f'<span class="source-badge">🔍 {engine}</span>'
    if pdate:
        card += f'<span style="font-size:16px;opacity:0.7;">📅 {pdate}</span>'
    if has_content:
        card += '<span style="font-size:16px;color:#22c55e;font-weight:700;">✅ 成功读取</span>'
    else:
        card += '<span style="font-size:16px;color:#aaa;">⚠ 未读取</span>'
    card += f"""
                </div>"""
    if page_content:
        cleaned = _clean_snippet(page_content, 600)
        if cleaned:
            card += f"""<div class="content-detail">
            <div class="content-detail-label">📖 {t('content_label')}</div>
            {cleaned}</div>"""
    card += f"""<div class="result-footer">
                    <span class="open-link"><a href="{url}" target="_blank">🔗 {t('source_label')}</a></span>
                </div>"""
    card += "</div></div></div>"
    st.markdown(card, unsafe_allow_html=True)


def render_source_index(results):
    """在小报下方显示来源索引"""
    st.markdown('<div class="report-section" style="border-left-color:#8FDBE0;margin-top:16px;">', unsafe_allow_html=True)
    st.markdown('<p style="font-size:22px;font-weight:800;color:#3F3A36;margin:0 0 12px;">📋 来源索引</p>', unsafe_allow_html=True)
    for r in results:
        sid = r.get("source_id", "")
        title = r.get("title", "")[:40]
        domain = r.get("domain", "")[:30]
        s_type = r.get("source_type", "未知")
        has_content = r.get("has_content", False)
        content_icon = "✅" if has_content else "⚠️"
        st.markdown(
            f'<div style="font-size:16px;padding:6px 0;border-bottom:1px dotted #FFC4AF;">'
            f'<span style="font-weight:700;">{sid}</span> '
            f'{title} | {domain} | {s_type} {content_icon}'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)


def render_course_positioning():
    st.markdown('<p class="section-title">📌 课程主题定位</p>', unsafe_allow_html=True)
    st.markdown("""<div class="info-card" style="margin-bottom:18px;">
        本系统围绕暖通空调系统中的热回收技术展开，聚焦排风热回收、转轮热回收、板式换热、热管换热、全热交换器等方向，
        辅助完成课程资料检索、技术理解和小报生成。
    </div>""", unsafe_allow_html=True)
    st.markdown("""<div class="info-card-row">
        <div class="info-card-item"><div class="info-card-item-title">🔬 技术对象</div><div class="info-card-item-desc">暖通空调热回收技术</div></div>
        <div class="info-card-item"><div class="info-card-item-title">🏢 应用场景</div><div class="info-card-item-desc">建筑节能、空调系统优化、余热利用</div></div>
        <div class="info-card-item"><div class="info-card-item-title">📄 输出成果</div><div class="info-card-item-desc">检索结果、资料摘要、技术小报</div></div>
    </div>""", unsafe_allow_html=True)


def render_search_flow():
    st.markdown('<p class="section-title">🔍 智能检索流程</p>', unsafe_allow_html=True)
    st.markdown("""<div class="flow-row">
        <div class="flow-card"><div class="flow-card-num">01</div><div class="flow-card-label">输入关键词</div><div class="flow-card-desc">明确研究方向</div></div>
        <div class="flow-card"><div class="flow-card-num">02</div><div class="flow-card-label">搜索候选网页</div><div class="flow-card-desc">Bing / 百度</div></div>
        <div class="flow-card"><div class="flow-card-num">03</div><div class="flow-card-label">初筛·去重·评分</div><div class="flow-card-desc">过滤无效结果</div></div>
        <div class="flow-card"><div class="flow-card-num">04</div><div class="flow-card-label">读取正文</div><div class="flow-card-desc">trafilatura 提取</div></div>
        <div class="flow-card"><div class="flow-card-num">05</div><div class="flow-card-label">二次评分过滤</div><div class="flow-card-desc">正文命中检验</div></div>
        <div class="flow-card"><div class="flow-card-num">06</div><div class="flow-card-label">DeepSeek 总结</div><div class="flow-card-desc">生成技术小报</div></div>
    </div>""", unsafe_allow_html=True)


def render_knowledge_cards():
    st.markdown('<p class="section-title">📚 热回收技术知识卡</p>', unsafe_allow_html=True)
    st.markdown("""<div class="knowledge-row">
        <div class="knowledge-card"><div class="knowledge-card-title">🔄 转轮式热回收</div><div class="knowledge-card-desc">适用于新风与排风之间的显热和潜热交换，利用旋转蓄热体在气流间交替传热传质，全热回收效率较高。</div></div>
        <div class="knowledge-card"><div class="knowledge-card-title">📐 板式热交换</div><div class="knowledge-card-desc">结构紧凑，气流通过固定板壁交叉换热，无运动部件，适合洁净度要求较高的暖通空调场景。</div></div>
        <div class="knowledge-card"><div class="knowledge-card-title">🔥 热管热回收</div><div class="knowledge-card-desc">依靠工质在蒸发段与冷凝段之间相变传热，无需外部动力，维护量较低，适合冷热温差大的场合。</div></div>
        <div class="knowledge-card"><div class="knowledge-card-title">♻️ 全热交换器</div><div class="knowledge-card-desc">可同时回收显热与潜热，在排出室内空气的同时预处理室外新风，显著提高新风系统能效。</div></div>
    </div>""", unsafe_allow_html=True)


def render_footer():
    st.markdown('<div class="footer">暖通空调热回收技术检索智能体 · 课程项目展示 · Powered by DeepSeek API</div>', unsafe_allow_html=True)


def render_debug_panel(dbg):
    with st.expander(f"🔧 {t('debug_title')}", expanded=False):
        st.markdown(f"**{t('debug_engine')}**：{dbg.get('engine','?')}")
        st.markdown("---")

        # 关键词扩展
        kw_info = dbg.get("kw_info")
        if kw_info:
            expansion_count = len(kw_info.get("search_queries", [])) - 1
            st.markdown(f"### 🔀 关键词扩展（{max(expansion_count, 0)} 个扩展query）")
            st.markdown(f"- **原始**: `{kw_info.get('original_query','')}`")
            if kw_info.get("chinese_keywords"):
                st.markdown(f"- **中文扩展**: {', '.join(kw_info['chinese_keywords'])}")
            if kw_info.get("english_keywords"):
                st.markdown(f"- **英文扩展**: {', '.join(kw_info['english_keywords'])}")
            if kw_info.get("academic_keywords"):
                st.markdown(f"- **论文关键词**: {', '.join(kw_info['academic_keywords'])}")
            st.markdown("**各 search_query**：")
            for sq in kw_info.get("search_queries", []):
                st.markdown(f"- `{sq['query']}` (权重 {sq['weight']:.1f}, {sq['source']})")
            st.markdown("**各 query 搜索返回数量**：")
            for qinfo in dbg.get("query_stats", []):
                if len(qinfo) >= 4:
                    q_text, q_weight, q_count, q_engine = qinfo[:4]
                    st.markdown(f"- `{q_text}` → {q_count} 条（{q_engine}）")
                else:
                    q_text, q_weight, q_count = qinfo[:3]
                    st.markdown(f"- `{q_text}` → {q_count} 条")
        else:
            st.markdown("**关键词扩展**：未启用")

        st.markdown("---")

        # 三层数量关系
        st.markdown("### 📊 数据质量控制链路")
        st.markdown(f"""
        | 阶段 | 数量 |
        |------|------|
        | 搜索候选数量 (search_top_n) | {dbg.get('search_top_n','?')} |
        | 原始返回结果 (raw) | {dbg.get('raw_count','?')} |
        | 初筛后结果 (pre_filtered) | {dbg.get('pre_filtered_count','?')} |
        | 计划读取 (planned) | {dbg.get('planned_read','?')} |
        | 成功读取正文 | {dbg.get('successfully_read','?')} |
        | DeepSeek 实际输入 (final) | {dbg.get('deepseek_input_count','?')} |
        """)

        # 关键词命中
        st.markdown(f"**{t('debug_kw_hits')}**：")
        for kw, hits in dbg.get("keyword_hits", {}).items():
            st.markdown(f'- 「{kw}」：{t("debug_kw_hit_line")} **{hits}** 次')

        # 阶段一：排除结果
        ec = dbg.get("pre_excluded_count", 0)
        if ec > 0:
            st.markdown(f"**阶段一排除结果**（共 {ec} 条）：")
            for ex in dbg.get("pre_excluded_samples", []):
                st.markdown(f"- ✗ {ex.get('title','')} — {ex.get('reason','')}")

        # 候选读取列表
        cand = dbg.get("candidates_to_read", [])
        if cand:
            st.markdown(f"**计划读取列表**（共 {len(cand)} 条）：")
            for c in cand:
                st.markdown(f"- [{c.get('pre_score',0)}] {c.get('title','')}")

        # 阶段二：读取后排除
        cr = dbg.get("content_rejected_list", [])
        if cr:
            st.markdown(f"**阶段二排除结果**（共 {dbg.get('content_rejected_count',0)} 条）：")
            for f in cr:
                extra = ""
                if f.get("length"): extra += f" | 长度: {f['length']}字符"
                st.markdown(f"- ⚠ {f.get('title','')} — {f.get('reason','')}{extra}")

        # 最终结果详情
        fd = dbg.get("final_results_detail", [])
        if fd:
            st.markdown(f"**最终送入 DeepSeek 的结果**（共 {len(fd)} 条）：")
            for f in fd:
                st.markdown(f"- {f.get('source_id','')} [{f.get('final_score',0)}] {f.get('title','')} | {f.get('extract_method','')} | {f.get('content_len',0)}字")


# ======================== 页面渲染 ========================

render_lang_switcher()
render_hero()
query, search_n, read_k, search_clicked, source_mode = render_search_panel()
render_recommended_keywords()

# --- 搜索逻辑（两阶段质量控制） ---
# 检测通过关键词标签点击传入的 ?kw= 参数
kw_from_url = None
try:
    kw_from_url = st.query_params.get("kw")
except Exception:
    pass
if kw_from_url:
    auto_trigger = True
    query = urllib.parse.unquote(str(kw_from_url))
    # 清除 URL 参数，避免重复触发
    st.query_params.clear()
else:
    auto_trigger = False

if (search_clicked or auto_trigger) and query.strip():
    with st.spinner(t("spinner")):
        try:
            q = query.strip()
            sn = int(search_n)
            rk = int(read_k)

            # 0. 关键词理解
            keywords = extract_keywords(q)
            expanded_keywords = expand_keywords(keywords)

            # ===== 1. 搜索原始候选（多 query 扩展搜索） =====
            kw_info = expand_query(q, source_mode)
            raw_results, engine, query_stats = multi_query_search(q, search_top_n=sn, source_mode=source_mode)
            if not raw_results:
                st.error(t("no_results"))
                st.stop()
            raw_count = len(raw_results)

            # ===== 2. 阶段一：读取前处理（过滤无效 + 去重 + pre_score） =====
            pre_filtered, pre_excluded = pre_filter_and_score(
                raw_results, keywords, expanded_keywords
            )
            pre_filtered_count = len(pre_filtered)

            # ===== 3. 选取 candidates_to_read =====
            if rk > pre_filtered_count:
                rk = pre_filtered_count
            candidates_to_read = pre_filtered[:rk]
            planned_read = len(candidates_to_read)

            # ===== 4. 读取正文 =====
            candidates_with_content = enrich_results_with_content(
                candidates_to_read, read_k=rk
            )

            # ===== 5. 阶段二：读取后处理（二次过滤 + final_score + 再次去重） =====
            final_results, content_rejected = post_read_filter_and_score(
                candidates_with_content, keywords, q
            )
            final_count = len(final_results)
            deepseek_input_count = final_count

            # 统计成功读取正文条数
            successfully_read = sum(
                1 for r in candidates_with_content
                if r.get("page_content") and r.get("extract_method") != "none"
            )

            # ===== 6. DeepSeek 总结（只使用 final_results） =====
            stats = {
                "search_top_n": sn,
                "crawled": raw_count,
                "pre_filtered_count": pre_filtered_count,
                "planned_read": planned_read,
                "read_pages": successfully_read,
                "deepseek_input": deepseek_input_count,
                "engine": engine,
            }
            summary = generate_summary(final_results, keywords, q, stats=stats)

            # ===== 7. 调试信息 =====
            debug_info = {
                "engine": engine,
                "search_top_n": sn,
                "read_top_k": rk,
                "raw_count": raw_count,
                "kw_info": kw_info,
                "query_stats": query_stats,
                "pre_filtered_count": pre_filtered_count,
                "planned_read": planned_read,
                "successfully_read": successfully_read,
                "deepseek_input_count": deepseek_input_count,
                "pre_excluded_count": len(pre_excluded),
                "pre_excluded_samples": [
                    {"title": t, "reason": r} for t, r in pre_excluded[:10]
                ],
                "content_rejected_count": len(content_rejected),
                "content_rejected_list": content_rejected,
                "candidates_to_read": [
                    {
                        "title": r.get("title", "")[:50],
                        "url": r.get("url", "")[:60],
                        "pre_score": r.get("_pre_score", 0),
                    }
                    for r in candidates_to_read
                ],
                "final_results_detail": [
                    {
                        "source_id": r.get("_source_id", ""),
                        "title": r.get("title", "")[:50],
                        "url": r.get("url", "")[:60],
                        "final_score": r.get("_final_score", 0),
                        "content_len": r.get("content_length", 0),
                        "extract_method": r.get("extract_method", "none"),
                    }
                    for r in final_results
                ],
                "keyword_hits": {},
            }
            for kw in keywords:
                debug_info["keyword_hits"][kw] = sum(
                    (r.get("title", "") + r.get("snippet", "")).lower().count(kw.lower())
                    for r in raw_results
                )

            # ===== 8. 格式化展示结果 =====
            display_results = []
            for r in final_results:
                cat = get_domain_category(r.get("domain", ""), r.get("url", ""))
                sid = r.get("_source_id", "")
                display_results.append({
                    "title": r["title"],
                    "url": r["url"],
                    "domain": r["domain"],
                    "domain_category": cat,
                    "source_type": r.get("_source_type", "未知"),
                    "snippet": r["snippet"],
                    "page_content": r.get("page_content", ""),
                    "has_content": bool(r.get("page_content_full") or r.get("page_content")),
                    "pre_score": r.get("_pre_score", 0),
                    "final_score": r.get("_final_score", 0),
                    "rank": r.get("_final_rank", 0),
                    "source_id": sid,
                    "content_length": r.get("content_length", 0),
                    "extract_method": r.get("extract_method", "none"),
                    "publish_date": r.get("publish_date", ""),
                    "engine": r.get("_engine", ""),
                })

            st.session_state.results = display_results
            st.session_state.summary = summary
            st.session_state.debug = debug_info
            st.session_state.kw_info = kw_info
            st.session_state.query_done = q
            st.session_state.status = {
                "engine": engine,
                "search_top_n": sn,
                "crawled": raw_count,
                "pre_filtered_count": pre_filtered_count,
                "planned_read": planned_read,
                "successfully_read": successfully_read,
                "deepseek_input": deepseek_input_count,
                "source_mode": "综合搜索",
                "search_queries": [sq["query"] for sq in kw_info.get("search_queries", [])[1:]],
                "total_found": len(display_results),
                "query": q,
            }
            st.rerun()
        except Exception as e:
            st.error(f"{t('search_error')}: {e}")

if "status" not in st.session_state:
    st.markdown(f'<div class="empty-state"><div class="icon">🔥</div><div class="text">{t("empty_text")}</div></div>', unsafe_allow_html=True)
    st.stop()

# --- 结果区 ---
status = st.session_state.status
has_report = bool(st.session_state.get("summary"))

render_metric_cards(status, has_report)

st.markdown(f'<p class="result-area-notice">📋 {t("result_notice")}</p>', unsafe_allow_html=True)

# 左右分栏：小报 + 结果
results_available = "results" in st.session_state and st.session_state.results
summary_available = "summary" in st.session_state

if results_available or summary_available:
    st.markdown('<div class="results-layout">', unsafe_allow_html=True)

    st.markdown('<div class="results-left">', unsafe_allow_html=True)
    if summary_available:
        render_report_card(st.session_state.summary)
        # 来源索引
        if results_available:
            render_source_index(st.session_state.results)
    else:
        st.info(f"📰 {t('report_empty')}")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="results-right">', unsafe_allow_html=True)
    if results_available:
        results = st.session_state.results
        st.markdown(f'<p class="section-title">📑 {t("results_title")}（共 {len(results)} 条）</p>', unsafe_allow_html=True)
        for i, r in enumerate(results, 1):
            r["_display_index"] = i
            render_result_card(r)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# 后续静态模块
render_course_positioning()
render_search_flow()
render_knowledge_cards()

if "debug" in st.session_state:
    render_debug_panel(st.session_state.debug)

render_footer()
