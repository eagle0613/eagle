"""
结果打分与筛选 — 两阶段质量控制
阶段一（读取前）：无效过滤 + 去重 + pre_score
阶段二（读取后）：正文质量过滤 + final_score + 再次去重
"""
import re
from urllib.parse import urlparse


# ==================== 1. 来源可信度识别 ====================

def get_domain_category(domain: str, url: str) -> str:
    """根据域名和 URL 判断来源类别。返回: gov / edu / research / org / news / enterprise / normal"""
    d = (domain + url).lower()
    if re.search(r"\.gov\.cn|\.gov/|\.gov$|\.gov\.", d):
        return "gov"
    if re.search(r"\.edu\.cn|\.edu/|\.edu$|\.ac\.cn|\.ac\.uk", d):
        return "edu"
    if re.search(r"cas\.cn|caep\.cn|cass\.cn|researchgate|arxiv|sci-hub|nature\.com|science\.org|cell\.com|ieee\.org|springer|sciencedirect|pnas|lancet|jama|nejm|wiley|pubmed|ncbi|research\.", d):
        return "research"
    if re.search(r"\.org\.cn|\.org/|\.org$|association|society|union|federation|alliance", d):
        return "org"
    if re.search(r"news|daily|times|post|xinhuanet|people\.com|china\.com|cctv|sina|sohu|163\.com|qq\.com|ifeng|thepaper|guancha|huanqiu|36kr|jiemian|caixin|yicai|cls\.cn|eastmoney|stcn|cnr|chinanews|chinaqw|toutiao", d):
        return "news"
    if re.search(r"baike\.|zhihu\.|csdn\.|cnblogs\.|jianshu\.|woshipm|huxiu|geekpark", d):
        return "enterprise"
    return "normal"


DOMAIN_CREDIBILITY = {
    "gov": 1.5, "edu": 1.4, "research": 1.5, "org": 1.2,
    "news": 0.9, "enterprise": 0.8, "normal": 1.0,
}


def get_credibility_weight(domain: str, url: str) -> float:
    cat = get_domain_category(domain, url)
    return DOMAIN_CREDIBILITY.get(cat, 1.0)


# ==================== 2. 无效结果过滤（阶段一用） ====================

INVALID_TITLE_PATTERNS = [
    (r"^首页[-\s]*$", True),
    (r"^home[-\s]*$", True),
    (r"^主页[-\s]*$", True),
    (r"登录页面|立即登录|请登录|登录注册|账号登录", False),
    (r"sign\s*in\b|log\s*in\b|sign\s*up\b", False),
    (r"站内搜索|站内检索|search\s*result|搜索结果页", False),
    (r"广告推广|sponsored|推广链接", False),
    (r"网站导航|站点地图|sitemap|site\s*navigation", False),
    (r"正在跳转|页面跳转|redirecting", False),
    (r"^栏目$|^频道$|^专题$|^分类$", True),
    (r"免责声明|版权声明|隐私政策|用户协议", False),
    (r"privacy\s*policy|terms\s*of\s*service", False),
    (r"验证码|请输入验证码|captcha", False),
]

INVALID_URL_PATTERNS = [
    r"baidu\.com/link\?",
    r"/s\?.*wd=",
    r"/search\?.*q=",
    r"/login", r"/signin", r"/signup", r"/register", r"/auth",
    r"pos\.baidu\.com", r"cpro\.baidu",
]


def _is_invalid_result(result: dict) -> tuple[bool, str]:
    """判断搜索结果是否无效。返回 (是否无效, 原因)"""
    title = result.get("title", "")
    url = result.get("url", "")
    snippet = result.get("snippet", "")
    combined = (title + " " + snippet).lower()

    if not title.strip():
        return True, "空标题"
    if not snippet.strip() or len(snippet.strip()) < 8:
        return True, "摘要过短"

    for pat, title_only in INVALID_TITLE_PATTERNS:
        target = title.lower() if title_only else combined
        if re.search(pat, target):
            return True, f"匹配无效模式: {pat[:30]}"

    for pat in INVALID_URL_PATTERNS:
        if re.search(pat, url, re.IGNORECASE):
            return True, f"匹配无效URL: {pat[:30]}"

    if len(title) <= 5 and url.count("/") <= 3:
        return True, "疑似首页"

    return False, ""


# ==================== 3. 去重 ====================

def _normalize_url(url: str) -> str:
    """去除 URL 中的 tracking 参数"""
    parsed = urlparse(url)
    qs = parsed.query
    if not qs:
        return url
    params = qs.split("&")
    cleaned = []
    for p in params:
        key = p.split("=")[0] if "=" in p else p
        if key.lower() in ("utm_source", "utm_medium", "utm_campaign", "utm_content",
                           "utm_term", "ref", "spm", "from", "source", "tracking",
                           "session_id", "sid", "click_id", "gclid", "fbclid", "msclkid"):
            continue
        cleaned.append(p)
    new_qs = "&".join(cleaned)
    if new_qs != qs:
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path
        return f"{scheme}://{netloc}{path}" + (f"?{new_qs}" if new_qs else "")
    return url


def _normalize_title(title: str) -> str:
    """标题规整化：小写 + 去空格 + 去标点"""
    t = title.lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t


def deduplicate_results(results: list[dict]) -> list[dict]:
    """
    去重：URL 完全相同 → 去除 tracking 参数后 URL 相同 → title 完全相同 → title 前30字高度相似
    """
    if not results:
        return []

    kept = []
    seen_urls = set()
    seen_norm_urls = set()
    seen_titles = set()
    seen_title_prefixes = set()

    for r in results:
        url = r.get("url", "")
        title = r.get("title", "")

        # 1) URL 完全相同
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # 2) 去除 tracking 参数后相同
        norm_url = _normalize_url(url)
        if norm_url in seen_norm_urls:
            continue
        seen_norm_urls.add(norm_url)

        # 3) title 规整后完全相同
        norm_title = _normalize_title(title)
        if norm_title in seen_titles:
            continue
        seen_titles.add(norm_title)

        # 4) title 前 30 字高度相似
        title_prefix = norm_title[:30]
        if title_prefix and title_prefix in seen_title_prefixes:
            continue
        if title_prefix:
            seen_title_prefixes.add(title_prefix)

        kept.append(r)

    return kept


# ==================== 4. 阶段一：读取前评分 pre_score ====================

def _compute_pre_score(result: dict, keywords: list[str], expanded_keywords: list[str]) -> float:
    """
    只能使用搜索结果页已有信息：
    - title/snippet 是否命中 query
    - URL 是否包含相关关键词
    - domain 可信度
    - 是否疑似无效页
    """
    title_lower = result.get("title", "").lower()
    snippet_lower = result.get("snippet", "").lower()
    url_lower = result.get("url", "").lower()
    domain = result.get("domain", "")

    score = 0.0

    # 关键词命中 title（权重高）
    for kw in keywords:
        kw_lower = kw.lower()
        score += title_lower.count(kw_lower) * 5.0

    # 关键词命中 snippet
    for kw in keywords:
        kw_lower = kw.lower()
        score += snippet_lower.count(kw_lower) * 1.5

    # 扩展词辅助匹配
    for kw in expanded_keywords:
        kw_lower = kw.lower()
        if kw_lower not in [k.lower() for k in keywords]:
            score += (title_lower + " " + snippet_lower).count(kw_lower) * 0.5

    # URL 包含关键词（弱信号）
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in url_lower:
            score += 1.0

    # 来源可信度加权
    credibility = get_credibility_weight(domain, result.get("url", ""))
    score *= credibility

    # 查询来源权重：原始 query 权重最高（1.0），扩展 query 降权（0.4-0.8）
    query_weight = result.get("_query_weight", 1.0)
    score *= query_weight

    # 标题信息量
    title_len = len(result.get("title", ""))
    if title_len < 5:
        score *= 0.4
    elif title_len > 25:
        score *= 1.1

    # snippet 长度
    snip_len = len(result.get("snippet", ""))
    if snip_len > 80:
        score *= 1.05
    if snip_len < 15:
        score *= 0.7

    return round(score, 2)


def pre_filter_and_score(
    results: list[dict],
    keywords: list[str],
    expanded_keywords: list[str],
    min_score: float = 0.5,
) -> tuple[list[dict], list]:
    """
    阶段一：过滤无效 + 去重 + pre_score 排序。
    返回 (pre_filtered_results, excluded_list)
    """
    excluded = []

    # Step 1: 过滤无效结果
    valid = []
    for r in results:
        is_invalid, reason = _is_invalid_result(r)
        if is_invalid:
            excluded.append((r.get("title", "")[:30], reason))
            continue
        valid.append(r)

    # Step 2: 去重
    deduped = deduplicate_results(valid)

    # Step 3: 计算 pre_score 并排序
    scored = []
    for r in deduped:
        s = _compute_pre_score(r, keywords, expanded_keywords)
        r["_pre_score"] = s
        if s >= min_score:
            scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    pre_filtered = [item[1] for item in scored]
    for i, r in enumerate(pre_filtered):
        r["_pre_rank"] = i + 1

    return pre_filtered, excluded


# ==================== 5. 阶段二：读取后评分 final_score ====================

def _compute_final_score(result: dict, keywords: list[str], query: str) -> float:
    """
    对已成功读取正文的结果做二次评分：
    - 正文是否命中 query
    - 正文长度是否足够
    - 正文是否围绕主题
    - title / snippet / content / source_type 综合
    """
    title_lower = result.get("title", "").lower()
    snippet_lower = result.get("snippet", "").lower()
    content = (result.get("page_content", "") or "").lower()
    domain = result.get("domain", "")
    url = result.get("url", "")

    score = 0.0

    # title 命中（与 pre_score 一致的基础分）
    for kw in keywords:
        kw_lower = kw.lower()
        score += title_lower.count(kw_lower) * 5.0
        score += snippet_lower.count(kw_lower) * 1.5

    # 正文命中（二次评分的核心）
    for kw in keywords:
        kw_lower = kw.lower()
        content_count = content.count(kw_lower)
        score += content_count * 2.0

    # 正文长度奖励
    content_len = len(result.get("page_content", "") or "")
    if content_len > 2000:
        score += 5.0
    elif content_len > 1000:
        score += 3.0
    elif content_len > 500:
        score += 1.5
    elif content_len > 200:
        score += 0.5

    # 来源可信度
    credibility = get_credibility_weight(domain, url)
    score *= credibility

    return round(score, 2)


def post_read_filter_and_score(
    results_with_content: list[dict],
    keywords: list[str],
    query: str,
    min_content_len: int = 200,
) -> tuple[list[dict], list]:
    """
    阶段二：对已读取正文的结果做二次过滤+评分。
    - 只过滤读取失败 / 正文过短
    - 成功读取的全部保留，不按可信度过滤
    - final_score 仅用于排序和展示
    返回 (final_results, rejected_list)
    """
    rejected = []
    valid = []

    for r in results_with_content:
        content = r.get("page_content", "") or ""
        extract_method = r.get("extract_method", "none")

        # 读取失败
        if extract_method == "none" or not content:
            rejected.append({
                "title": r.get("title", "")[:40],
                "url": r.get("url", "")[:60],
                "reason": "正文读取失败",
            })
            continue

        # 正文过短
        if len(content) < min_content_len:
            rejected.append({
                "title": r.get("title", "")[:40],
                "url": r.get("url", "")[:60],
                "length": len(content),
                "reason": f"正文过短（{len(content)}字符 < {min_content_len}字符）",
            })
            continue

        # 成功读取 → 全部保留
        fs = _compute_final_score(r, keywords, query)
        r["_final_score"] = fs
        cat = get_domain_category(r.get("domain", ""), r.get("url", ""))
        r["_source_type"] = _get_source_type_label(cat)
        valid.append(r)

    # 按 final_score 排序
    valid.sort(key=lambda x: x.get("_final_score", 0), reverse=True)

    # 去重
    final_results = deduplicate_results(valid)

    for i, r in enumerate(final_results):
        r["_final_rank"] = i + 1
        r["_source_id"] = f"#{i + 1}"

    return final_results, rejected


def _get_source_type_label(category: str) -> str:
    """来源类别中文标签"""
    labels = {
        "gov": "政府/标准机构",
        "edu": "高校/科研机构",
        "research": "研究机构",
        "org": "行业协会",
        "news": "新闻媒体",
        "enterprise": "企业资料",
        "normal": "普通网页",
    }
    return labels.get(category, "未知来源")


# ==================== 6. 兼容旧接口（向后兼容） ====================

def filter_and_rank(
    results: list[dict],
    keywords: list[str],
    expanded_keywords: list[str],
    min_relevance: float = 0.5,
) -> tuple[list[dict], list]:
    """
    兼容旧接口：使用阶段一的 pre_score 进行过滤和排序。
    返回 (ranked, excluded)
    """
    scored = []
    excluded = []

    for r in results:
        is_invalid, reason = _is_invalid_result(r)
        if is_invalid:
            excluded.append((r.get("title", "")[:30], reason))
            continue

        s = _compute_pre_score(r, keywords, expanded_keywords)
        credibility = get_credibility_weight(r.get("domain", ""), r.get("url", ""))
        r["_score"] = s
        r["_credibility"] = round(credibility, 2)

        if s >= min_relevance:
            scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [item[1] for item in scored]
    for i, r in enumerate(ranked):
        r["_rank"] = i + 1

    return ranked, excluded
