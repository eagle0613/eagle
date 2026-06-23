"""
搜索引擎调用与结果解析
- Bing/百度 HTML 搜索 → 解析 → trafilatura 正文抓取
- 通用 query 关键词理解
- 发布日期解析 + 正文质量校验（长度/时效）
"""
import re
import urllib.parse
from datetime import datetime
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
TIMEOUT = 10

# 质量过滤阈值
MIN_CONTENT_LENGTH = 300


def _safe_decode(resp) -> str:
    """安全解码 HTTP 响应，防止中文乱码。
    策略：先取 apparent_encoding（chardet），如果不含中文字符则回退到 resp.text。
    """
    raw = resp.content
    apparent = resp.apparent_encoding
    if apparent and apparent.lower() != resp.encoding.lower():
        try:
            decoded = raw.decode(apparent)
            # 验证：至少包含一些中文字符才算有效编码
            if re.search(r"[\u4e00-\u9fff]", decoded):
                return decoded
        except (UnicodeDecodeError, LookupError):
            pass
    # 尝试 UTF-8
    try:
        decoded = raw.decode("utf-8")
        if re.search(r"[\u4e00-\u9fff]", decoded):
            return decoded
    except (UnicodeDecodeError, LookupError):
        pass
    # 最终回退
    return resp.text


def _extract_date_from_snippet(snippet: str) -> str:
    """从搜索引擎 snippet 中提取日期作为 fallback（格式: 2025年9月27日 / 2024-09-27 等）"""
    if not snippet:
        return ""
    patterns = [
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
        r"(\d{1,2})\s+[A-Z][a-z]{2,8}\s+(\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, snippet)
        if m:
            groups = m.groups()
            try:
                if len(groups) == 3 and groups[0].isdigit() and len(groups[0]) == 4:
                    y, mo, d = groups
                    return f"{int(y)}-{int(mo):02d}-{int(d):02d}"
                elif len(groups) == 2 and groups[1].isdigit() and len(groups[1]) == 4:
                    # 英文日期格式
                    return f"{int(groups[1])}-01-01"
            except (ValueError, IndexError):
                pass
    return ""


# ==================== 0. 通用 query 理解 ====================

def extract_keywords(query: str) -> list[str]:
    """从任意 query 中提取关键词，完全通用"""
    keywords = []
    en_words = re.findall(r"[a-zA-Z0-9+/\-]{2,}", query)
    keywords.extend(w.lower() for w in en_words if len(w) >= 2)
    zh_words = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    keywords.extend(zh_words)
    if not keywords:
        keywords = [query.strip().lower()]
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


def expand_keywords(keywords: list[str]) -> list[str]:
    """为关键词构造搜索用组合词"""
    expanded = list(keywords)
    zh = [kw for kw in keywords if re.search(r"[\u4e00-\u9fff]", kw)]
    if len(zh) >= 2:
        for i in range(len(zh) - 1):
            combo = zh[i] + zh[i + 1]
            if combo not in expanded:
                expanded.append(combo)
        full = "".join(zh)
        if full not in expanded and len(full) <= 12:
            expanded.append(full)
    return expanded


# ==================== 关键词扩展 ====================

# 复合后缀（紧贴原始词，不插空格，避免搜索引擎拆分匹配到无关字符）
_COMPOUND_SUFFIXES = ["技术", "系统", "设备", "原理", "案例", "节能", "效率", "换热器"]

# HVAC 领域限定前缀（用空格分隔，确保搜索引擎按多词匹配，限定在暖通领域）
_CONTEXT_PREFIXES = ["暖通空调", "暖通", "新风系统", "空调系统"]


def _is_result_set_relevant(results: list[dict], original_keyword: str, min_relevant: int = 1) -> bool:
    """验证搜索结果集是否与原始关键词相关：至少 N 条结果标题或摘要中包含关键词"""
    if not results:
        return False
    kw_lower = original_keyword.lower()
    relevant = 0
    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        if kw_lower in text:
            relevant += 1
    return relevant >= min_relevant


def expand_query(query: str, source_mode: str = "综合搜索") -> dict:
    """
    生成扩展搜索 query：
    1. 原始 query 直接搜索
    2. 复合后缀拼接（无空格）
    3. HVAC 领域限定（前缀 + 原始词），确保结果限定在暖通空调领域
    """
    query = query.strip()
    search_queries = [{"query": query, "weight": 1.0, "source": "原始query"}]

    # 复合后缀：技术、系统、设备...
    for suffix in _COMPOUND_SUFFIXES:
        if suffix in query:
            continue
        qq = f"{query}{suffix}"  # 复合词，不加空格
        search_queries.append({"query": qq, "weight": 0.6, "source": f"扩展({suffix})"})

    # HVAC 领域限定：前缀 + 空格 + 原始词，确保搜索范围限定在暖通空调领域
    for prefix in _CONTEXT_PREFIXES:
        if prefix in query:
            continue
        qq = f"{prefix} {query}"
        search_queries.append({"query": qq, "weight": 0.7, "source": f"限定({prefix})"})

    return {
        "original_query": query,
        "chinese_keywords": [],
        "english_keywords": [],
        "academic_keywords": [],
        "search_queries": search_queries,
    }


def multi_query_search(
    query: str,
    search_top_n: int = 20,
    source_mode: str = "综合搜索",
) -> tuple[list[dict], str, list[tuple[str, float, int]]]:
    """
    多 query 搜索：原始 query 占绝对主导，扩展 query 仅在结果不足时补充。
    返回 (合并去重后的结果列表, 搜索引擎名称, [(query, weight, result_count, engine_name), ...])
    """
    kw_info = expand_query(query, source_mode)
    search_queries = kw_info["search_queries"]  # [{"query", "weight", "source"}, ...]
    original_query = search_queries[0]["query"]
    used_engine = "Bing"
    query_stats = []

    # 原始 query 占大量配额（70%），至少搜 15 条（search_top_n=20 时）
    original_quota = max(int(search_top_n * 0.7), 12)
    if original_quota > search_top_n:
        original_quota = search_top_n

    # ===== 搜索原始 query（Bing → 百度 fallback） =====
    results, engine = search_bing(original_query, max_results=original_quota)
    if not results:
        results, engine = search_baidu(original_query, max_results=original_quota)
    used_engine = engine
    for r in results:
        r["_query_source"] = "original"
        r["_query_weight"] = 1.0
    query_stats.append((original_query, 1.0, len(results), engine))

    # ===== 如果原始 query 结果太少，尝试用百度 + 扩大搜索量 =====
    if len(results) < max(5, search_top_n // 3):
        if engine == "Bing":
            r_baidu, _ = search_baidu(original_query, max_results=original_quota)
            if len(r_baidu) > len(results):
                results = r_baidu
                used_engine = "百度"
                for r in results:
                    r["_query_source"] = "original"
                    r["_query_weight"] = 1.0
                query_stats[0] = (original_query, 1.0, len(results), used_engine)

        if len(results) < max(5, search_top_n // 3):
            retry_quota = search_top_n
            print(f"[搜索增强] 原始 query 仅 {len(results)} 条，扩大搜索到 {retry_quota} 条")
            r_retry, e_retry = search_bing(original_query, max_results=retry_quota)
            if len(r_retry) < len(results):
                r_retry, e_retry = search_baidu(original_query, max_results=retry_quota)
            if len(r_retry) > len(results):
                used_engine = e_retry
                results = r_retry
                for r in results:
                    r["_query_source"] = "original"
                    r["_query_weight"] = 1.0
                query_stats[0] = (original_query, 1.0, len(results), used_engine)

    all_results = list(results)

    # ===== 扩展 query：只在原始结果不足 search_top_n 时补充 =====
    # 辅助引擎轮换列表（每个扩展query用不同引擎，增加信息来源多样性）
    aux_engines = [(name, fn) for name, fn in _ALL_SEARCH_ENGINES]

    extra_queries = search_queries[1:] if len(search_queries) > 1 else []
    if len(all_results) < search_top_n and extra_queries:
        remain_quota = search_top_n - len(all_results)
        each_quota = max(3, remain_quota // max(len(extra_queries), 1))

        for idx, sq in enumerate(extra_queries):
            exp_q = sq["query"]
            weight = sq["weight"]
            if exp_q == original_query:
                continue
            if len(all_results) >= search_top_n:
                break

            # 轮换使用不同搜索引擎：每个扩展query从不同引擎开始尝试
            # e.g. idx=0 从 engines[0] 开始, idx=1 从 engines[1] 开始...
            r2 = []
            engine_name = "未知"
            engine_count = len(aux_engines)
            for offset in range(engine_count):
                eng_idx = (idx + offset) % engine_count
                eng_name, eng_fn = aux_engines[eng_idx]
                r2, engine_name = eng_fn(exp_q, max_results=each_quota)
                if r2:
                    break

            # 验证扩展结果是否与原始关键词相关
            if not _is_result_set_relevant(r2, original_query):
                print(f"[扩展过滤] '{exp_q}' 返回 {len(r2)} 条但均不相关，已丢弃")
                continue
            for r in r2:
                r["_query_source"] = "expansion"
                r["_query_weight"] = weight
                r["_engine"] = engine_name
            all_results.extend(r2)
            query_stats.append((exp_q, weight, len(r2), engine_name))

    # 合并后去重
    from ranker import deduplicate_results
    deduped = deduplicate_results(all_results)

    if len(deduped) > search_top_n:
        deduped = deduped[:search_top_n]

    return deduped, used_engine, query_stats


# ==================== 1. 搜索引擎搜索结果获取 ====================

def search_baidu(query: str, max_results: int = 20) -> tuple[list[dict], str]:
    """百度搜索：请求百度结果页，解析 HTML 提取搜索结果"""
    url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}&rn={max_results}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for container in soup.select(".c-container, .result"):
            title_el = container.select_one("h3 a, .t a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not title or not href:
                continue
            snippet_el = container.select_one(
                ".c-abstract, .content-right_8Zs40, .c-span-last, span.content-right_8Zs40"
            )
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            domain_el = container.select_one(".c-showurl, .c-showurl span, .c-color-gray")
            domain = domain_el.get_text(strip=True) if domain_el else ""
            if not domain:
                domain = urlparse(href).netloc
            results.append({
                "title": title, "url": href, "domain": domain, "snippet": snippet,
            })
            if len(results) >= max_results:
                break
        return results, "百度"
    except Exception as e:
        print(f"[百度搜索失败] {e}")
        return [], "百度"


def search_bing(query: str, max_results: int = 20) -> tuple[list[dict], str]:
    """Bing 搜索：作为主方案"""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={max_results}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for item in soup.select("li.b_algo"):
            title_el = item.select_one("h2 a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not title or not href:
                continue
            snippet_el = item.select_one(".b_caption p, .b_lineclamp2, .b_algoSlug")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            domain_el = item.select_one(".tpmeta .b_attribution, cite")
            domain = domain_el.get_text(strip=True) if domain_el else ""
            if not domain:
                domain = urlparse(href).netloc
            results.append({
                "title": title, "url": href, "domain": domain, "snippet": snippet,
            })
            if len(results) >= max_results:
                break
        return results, "Bing"
    except Exception as e:
        print(f"[Bing搜索失败] {e}")
        return [], "Bing"


def search_sogou(query: str, max_results: int = 10) -> tuple[list[dict], str]:
    """搜狗搜索：辅助渠道，解析 HTML 提取搜索结果"""
    url = f"https://www.sogou.com/web?query={urllib.parse.quote(query)}&num={max_results}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for item in soup.select(".results .rb, .vrwrap"):
            title_el = item.select_one(".vr-title a, h3 a, .vrTitle a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not title or not href:
                continue
            snippet_el = item.select_one(".star-wiki, .str-text, .space-txt, .vr-txt, .str_info_div")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            domain_el = item.select_one(".citeurl, cite, .vr-title cite, .fb-hint")
            domain = domain_el.get_text(strip=True) if domain_el else ""
            if not domain:
                domain = urlparse(href).netloc
            results.append({
                "title": title, "url": href, "domain": domain, "snippet": snippet,
            })
            if len(results) >= max_results:
                break
        return results, "搜狗"
    except Exception as e:
        print(f"[搜狗搜索失败] {e}")
        return [], "搜狗"


def search_360(query: str, max_results: int = 10) -> tuple[list[dict], str]:
    """360搜索：辅助渠道，解析 HTML 提取搜索结果"""
    url = f"https://www.so.com/s?q={urllib.parse.quote(query)}&pn=0&src=srp_paging"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for item in soup.select(".res-list > li, .result"):
            title_el = item.select_one("h3.res-title a, h3 a, .res-title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not title or not href:
                continue
            snippet_el = item.select_one(".res-desc, .res-comm-con, .res-summary")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            domain_el = item.select_one(".res-linkinfo cite, cite, .res-linkinfo")
            domain = domain_el.get_text(strip=True) if domain_el else ""
            if not domain:
                domain = urlparse(href).netloc
            results.append({
                "title": title, "url": href, "domain": domain, "snippet": snippet,
            })
            if len(results) >= max_results:
                break
        return results, "360搜索"
    except Exception as e:
        print(f"[360搜索失败] {e}")
        return [], "360搜索"


# 所有可用搜索引擎列表，按优先级排列（辅助查询时轮换使用）
_ALL_SEARCH_ENGINES = [
    ("Bing", search_bing),
    ("百度", search_baidu),
    ("搜狗", search_sogou),
    ("360搜索", search_360),
]


def unified_search(query: str, max_results: int = 20) -> tuple[list[dict], str]:
    """统一搜索入口：优先百度，百度失败则用 Bing"""
    results, engine = search_baidu(query, max_results)
    if results:
        return results, engine
    print("[回退] 百度无结果，尝试 Bing...")
    results, engine = search_bing(query, max_results)
    return results, engine


# ==================== 2. 发布日期解析 ====================

def _parse_publish_date(html_text: str, url: str = "") -> str:
    """
    从 HTML 中解析发布日期。
    优先级：<meta article:published_time> → <meta date> → <time datetime> →
           JSON-LD datePublished → 正文中日期模式
    返回 ISO 格式日期字符串，或空字符串。
    """
    soup = BeautifulSoup(html_text, "html.parser")

    # 1) <meta property="article:published_time">
    meta = soup.find("meta", attrs={"property": "article:published_time"})
    if meta and meta.get("content"):
        return meta["content"][:10]

    # 2) <meta name="date"> / <meta name="DC.date">
    for name in ["date", "DC.date", "dc.date", "pubdate", "pub_date", "publish-date"]:
        meta = soup.find("meta", attrs={"name": lambda v: v and v.lower() == name})
        if meta and meta.get("content"):
            val = meta["content"]
            m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", val)
            if m:
                return m.group(1).replace("/", "-")[:10]

    # 3) <time datetime="...">
    for time_el in soup.find_all("time"):
        dt = time_el.get("datetime", "")
        if dt:
            m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", dt)
            if m:
                return m.group(1).replace("/", "-")[:10]

    # 4) JSON-LD datePublished
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                graph = data.get("@graph", [data])
            else:
                graph = data if isinstance(data, list) else [data]
            for item in graph:
                if isinstance(item, dict):
                    for key in ["datePublished", "dateCreated", "dateModified"]:
                        val = item.get(key)
                        if val:
                            m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", str(val))
                            if m:
                                return m.group(1).replace("/", "-")[:10]
        except Exception:
            pass

    # 5) 正文中明显的日期模式（如 "2024年1月15日"）
    text = trafilatura.extract(html_text, include_comments=False, include_tables=False) or ""
    body_date = re.search(r"(20\d{2})\s*[年/\-]\s*(\d{1,2})\s*[月/\-]\s*(\d{1,2})\s*[日]", text)
    if body_date:
        return f"{body_date.group(1)}-{int(body_date.group(2)):02d}-{int(body_date.group(3)):02d}"

    # 6) URL 中的日期（如 /2024/05/...）
    url_date = re.search(r"/(20\d{2})/(\d{2})(?:/(\d{2}))?", url)
    if url_date:
        y = url_date.group(1)
        m = url_date.group(2)
        d = url_date.group(3) or "01"
        return f"{y}-{m}-{d}"

    return ""


# ==================== 3. trafilatura 正文提取 + 质量校验 ====================

def fetch_page_text(url: str) -> dict:
    """
    单跳访问链接，用 trafilatura 提取正文，附带质量元数据。
    返回 {"content": str, "length": int, "date": str, "method": "trafilatura"|"bs4"|"none"}
    """
    result = {"content": "", "length": 0, "date": "", "method": "none"}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return result

        # 编码修复：优先用 apparent_encoding（chardet 检测），避免乱码
        html_text = _safe_decode(resp)

        # === 尝试 trafilatura ===
        extracted = trafilatura.extract(
            html_text,
            include_comments=False,
            include_tables=False,
            include_images=False,
            include_links=False,
            favor_precision=True,
            no_fallback=False,
        )
        if extracted and len(extracted.strip()) > 50:
            result["content"] = extracted.strip()
            result["method"] = "trafilatura"
        else:
            # === fallback: BeautifulSoup ===
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
                tag.decompose()

            text_parts = []
            main_selectors = [
                "article", "main", '[role="main"]',
                ".article-content", ".post-content", ".content", ".article",
                "#content", "#article", "#main",
            ]
            found_main = False
            for sel in main_selectors:
                container = soup.select_one(sel)
                if container:
                    for p in container.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
                        t = p.get_text(strip=True)
                        if len(t) > 15:
                            text_parts.append(t)
                    found_main = True
                    break
            if not found_main:
                body = soup.find("body")
                if body:
                    for p in body.find_all(["p", "h1", "h2", "h3"]):
                        t = p.get_text(strip=True)
                        if len(t) > 15:
                            text_parts.append(t)

            seen = set()
            unique = []
            for t in text_parts:
                if t not in seen:
                    seen.add(t)
                    unique.append(t)
            if unique:
                result["content"] = "\n".join(unique)
                result["method"] = "bs4"

        # === 截断 ===
        if len(result["content"]) > 5000:
            result["content"] = result["content"][:5000] + "..."

        result["length"] = len(result["content"])

        # === 解析发布日期 ===
        try:
            result["date"] = _parse_publish_date(html_text, url)
        except Exception:
            result["date"] = ""

        return result

    except Exception as e:
        print(f"[页面抓取失败] {url[:60]}... => {e}")
        return result


# ==================== 4. 批量抓取 ====================

def enrich_results_with_content(
    results: list[dict],
    read_k: int = None,
    min_content_len: int = MIN_CONTENT_LENGTH,
) -> list[dict]:
    """
    对前 read_k 条结果用 trafilatura 抓取正文。
    不再在这里做质量过滤——质量闸门由 ranker.py 的 post_read_filter_and_score 负责。
    返回带有 page_content / page_content_full / content_length / extract_method / publish_date 的结果列表。
    """
    top = min(read_k, len(results)) if read_k else len(results)
    if top == 0:
        return results

    for i in range(top):
        r = results[i]
        url = r.get("url", "")
        if not url.startswith("http"):
            r["content_length"] = 0
            r["quality_pass"] = False
            r["quality_reason"] = "非HTTP链接"
            r["page_content"] = ""
            r["page_content_full"] = ""
            r["publish_date"] = ""
            r["extract_method"] = "none"
            continue

        print(f"[读取正文] ({i + 1}/{top}) {r['title'][:45]}...")
        extracted = fetch_page_text(url)

        r["extract_method"] = extracted["method"]
        r["content_length"] = extracted["length"]
        r["publish_date"] = extracted.get("date", "")
        # 如果页面没提取到日期，尝试从 snippet 中获取
        if not r["publish_date"]:
            r["publish_date"] = _extract_date_from_snippet(r.get("snippet", ""))

        if extracted["method"] == "none":
            r["page_content"] = ""
            r["page_content_full"] = ""
            r["quality_pass"] = False
            r["quality_reason"] = "正文提取失败"
            continue

        if extracted["length"] < min_content_len:
            r["page_content"] = extracted["content"][:2000] if extracted["content"] else ""
            r["page_content_full"] = extracted["content"]
            r["quality_pass"] = False
            r["quality_reason"] = f"正文过短（{extracted['length']}字符 < {min_content_len}字符）"
            continue

        r["page_content"] = extracted["content"][:2000] if extracted["content"] else ""
        r["page_content_full"] = extracted["content"]
        r["quality_pass"] = True
        r["quality_reason"] = ""

    return results
