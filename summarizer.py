"""
总结小报生成
提取式摘要 → 事实句识别 → 话题聚类 → 7节结构化报告
支持来源编号标注 + 可信度等级
"""
import re
from ranker import get_domain_category, DOMAIN_CREDIBILITY


# ==================== 文本处理 ====================

def _split_sentences_with_source(text: str, source_id: str) -> list[tuple[str, str]]:
    """分句，返回 (句子, 来源ID) 列表，过滤过短句"""
    result = []
    for p in re.split(r"[。！？\.\!\?\;\；\n]+", text):
        p = p.strip()
        if len(p) > 10:
            result.append((p, source_id))
    return result


def _is_fact_sentence(s: str) -> bool:
    """判断是否包含事实性信息（数字、百分比、年份、定义等）"""
    return bool(
        re.search(r"\d+[%％万千兆亿]|\d{4}年|\d+℃|\d+kW|\d+兆瓦|约\d+|超过\d+|达到\d+|占比|总计|数据", s) or
        re.search(r"是指|定义为|即[^\d]|又称|全称|简称|通常|一般|主要|其[中主]", s)
    )


def _extract_source_label(result: dict) -> str:
    """从结果中提取可读的来源标签"""
    title = result.get("title", "")[:30]
    domain = result.get("domain", "")[:40]
    cat = get_domain_category(domain, result.get("url", ""))
    cat_cn = {"gov": "政府", "edu": "高校", "research": "研究", "org": "协会",
              "news": "媒体", "enterprise": "企业", "normal": "网站"}
    if domain:
        domain_clean = re.sub(r"^https?://(www\.)?", "", domain).rstrip("/")
        return f"{title} ({domain_clean}, {cat_cn.get(cat, '')})"
    return title


# ==================== 话题聚类 ====================

def _cluster_sentences(sentences: list[str], keywords: list[str]) -> list[list[str]]:
    """按关键词共现将句子分成话题簇"""
    if not sentences:
        return []
    kw_vec = []
    for s in sentences:
        vec = tuple(1 if kw in s else 0 for kw in keywords[:5])
        kw_vec.append(vec)

    seen = set()
    clusters = []
    for i, vec in enumerate(kw_vec):
        if i in seen:
            continue
        group = [sentences[i]]
        seen.add(i)
        for j, v2 in enumerate(kw_vec):
            if j in seen:
                continue
            if vec == v2:
                group.append(sentences[j])
                seen.add(j)
        clusters.append(group)
    return clusters


# ==================== 不确定性检测 ====================

def _detect_uncertainty(results: list[dict], all_sentences: list[str]) -> list[str]:
    """检测不确定点：来源矛盾、数据缺失、观点对立、宣传倾向、正文不完整"""
    points = []
    all_text = " ".join(all_sentences)

    # 1) 矛盾/争议词检测
    contradiction_terms = ["然而", "但是", "却", "争议", "不同观点", "有待", "尚无定论", "不同看法"]
    for term in contradiction_terms:
        for s in all_sentences:
            if term in s and len(s) < 120 and s not in points:
                points.append(s)

    # 2) 数据缺失检测
    if re.search(r"(具体|详细|目前).*(数据|数字|尚不|未公布|未知)", all_text):
        for s in all_sentences:
            if re.search(r"(尚不|未公布|数据.*缺|暂无)", s) and s not in points:
                points.append(s)

    # 3) 时效性检测
    years = re.findall(r"(\d{4})年", all_text)
    if years:
        max_year = max(int(y) for y in years)
        if max_year < 2024:
            points.append(f"搜索结果中最新的数据年份为{max_year}年，信息可能不够新。")

    # 4) 正文读取完整性
    short_content = sum(1 for r in results if r.get("content_length", 0) < 500)
    if short_content > 0:
        points.append(f"有 {short_content} 个页面的正文不足 500 字，可能影响总结完整性。")

    # 5) 企业来源偏多（可能有宣传倾向）
    enterprise_count = sum(1 for r in results if get_domain_category(r.get("domain", ""), r.get("url", "")) == "enterprise")
    if enterprise_count >= len(results) * 0.5 and len(results) >= 2:
        points.append("当前结果中企业技术资料占比较高，部分内容可能存在宣传倾向，建议交叉比对。")

    # 确保至少 2 条
    if len(points) < 2:
        all_domains = set(r.get("domain", "") for r in results)
        points.append(f"本次搜索结果来自 {len(all_domains)} 个不同域名，未检测到明显矛盾点。")
        points.append("部分搜索结果可能包含时效性不足的信息，建议关注发布时间。")

    return points[:5]


# ==================== 后续建议 ====================

def _generate_suggestions(keywords: list[str], results: list[dict], all_sentences: list[str]) -> list[str]:
    """根据搜索覆盖情况生成后续建议"""
    suggestions = []
    all_text = " ".join(all_sentences)
    has_data = bool(re.search(r"\d+[%％万千兆亿度℃]", all_text))
    has_policy = bool(re.search(r"政策|规划|标准|法规|补贴", all_text))
    has_tech = bool(re.search(r"技术|原理|工艺|方法|系统|设备", all_text))
    has_case = bool(re.search(r"案例|应用|项目|实例|工程|试点", all_text))
    has_global = bool(re.search(r"国际|美国|欧洲|日本|德国|国外|全球", all_text))

    kw_str = "、".join(keywords[:3])
    if not has_data:
        suggestions.append(f"建议补充检索「{kw_str} 最新数据」，获取定量信息。")
    if not has_policy:
        suggestions.append(f"建议检索「{kw_str} 政策 标准」，了解行业规范。")
    if not has_tech:
        suggestions.append(f"建议检索「{kw_str} 技术原理」，深入了解机制。")
    if not has_case:
        suggestions.append(f"建议检索「{kw_str} 案例 项目」，查看实际应用。")
    if not has_global:
        suggestions.append(f"建议检索「{kw_str} 国际 对比」，获得全球视角。")
    if len(suggestions) < 2:
        suggestions.append(f"建议检索「{kw_str} 前景 趋势」，把握发展方向。")
    return suggestions[:4]


# ==================== 主入口：生成总结 ====================

def generate_summary(
    results: list[dict],
    keywords: list[str],
    query: str,
    stats: dict = None,
) -> str:
    """
    生成结构化研究小报（7节结构）：
    1.查询主题 / 2.搜索概况 / 3.核心发现（带来源标注）/ 4.重要来源 / 5.当前结论 / 6.不确定点 / 7.后续建议

    results 必须是 final_results（即已经过两阶段评分的高质量结果），每条必须包含 _source_id。
    """
    if not results:
        return "未找到足够信息生成摘要，请尝试更换关键词。"

    # 收集文本，同时记录每个句子的来源
    all_sentences_raw = []  # list of (sentence, source_id)
    content_count = 0
    for r in results:
        source_id = r.get("_source_id", f"#{r.get('_final_rank', '?')}")
        content = r.get("page_content_full", "") or r.get("page_content", "")
        if content:
            content_count += 1
            sentences = _split_sentences_with_source(content, source_id)
            all_sentences_raw.extend(sentences)
        # snippet 也收集，但用更低优先级标记
        snippet = r.get("snippet", "")
        if snippet:
            snip_sentences = _split_sentences_with_source(snippet, source_id + "[摘要]")
            all_sentences_raw.extend(snip_sentences)

    all_sentences = [s for s, _ in all_sentences_raw]
    # 句子的来源映射
    sentence_source_map = {}
    for s, sid in all_sentences_raw:
        if s not in sentence_source_map:
            sentence_source_map[s] = set()
        sentence_source_map[s].add(sid)

    if not all_sentences:
        return "未找到足够信息生成摘要，请尝试更换关键词。"

    fact_sentences = [s for s in all_sentences if _is_fact_sentence(s)]
    desc_sentences = [s for s in all_sentences if s not in fact_sentences]

    def sent_score(s):
        s_lower = s.lower()
        sc = sum(s_lower.count(kw.lower()) for kw in keywords)
        if re.search(r"\d+[%％万千兆亿度℃]", s):
            sc += 2
        if len(s) > 30:
            sc += 0.5
        return sc

    # 1. 查询主题
    report = [f"# 研究小报：{query}"]

    # 2. 搜索概况
    s = stats or {}
    crawled = s.get("crawled", len(results))
    retained = s.get("retained", len(results))
    read_pages = s.get("read_pages", content_count)
    deepseek_input = s.get("deepseek_input", len(results))
    engine = s.get("engine", "搜索引擎")
    report.append("")
    report.append("## 搜索概况")
    report.append(f"- 搜索候选数量：{s.get('search_top_n', crawled)} 条")
    report.append(f"- 原始返回结果：{crawled} 条")
    report.append(f"- 初筛后结果：{s.get('pre_filtered_count', retained)} 条")
    report.append(f"- 计划读取网页：{s.get('planned_read', read_pages)} 条")
    report.append(f"- 成功读取正文：{read_pages} 条")
    report.append(f"- DeepSeek 实际总结来源：{deepseek_input} 条")
    report.append(f"- 搜索源：{engine}")
    report.append("")

    # 3. 核心发现（带来源标注）
    report.append("## 核心发现")
    scored_facts = sorted(
        [(sent_score(s), s) for s in fact_sentences if sent_score(s) > 0],
        key=lambda x: x[0], reverse=True,
    )
    seen_norm = set()
    findings_with_sources = []
    for sc, s in scored_facts:
        norm = re.sub(r"\s+", "", s)[:40]
        if norm not in seen_norm:
            seen_norm.add(norm)
            sources = sentence_source_map.get(s, set())
            # 清理来源ID（去掉[摘要]后缀）
            clean_sources = set()
            for sid in sources:
                clean_sid = re.sub(r"\[摘要\]$", "", sid)
                clean_sources.add(clean_sid)
            findings_with_sources.append((s, sorted(clean_sources, key=lambda x: int(re.sub(r"[^0-9]", "", x)) if re.search(r"\d+", x) else 999)))
        if len(findings_with_sources) >= 6:
            break
    if len(findings_with_sources) < 3:
        scored_desc = sorted(
            [(sent_score(s), s) for s in desc_sentences if sent_score(s) > 0],
            key=lambda x: x[0], reverse=True,
        )
        for sc, s in scored_desc:
            norm = re.sub(r"\s+", "", s)[:40]
            if norm not in seen_norm:
                seen_norm.add(norm)
                sources = sentence_source_map.get(s, set())
                clean_sources = set()
                for sid in sources:
                    clean_sid = re.sub(r"\[摘要\]$", "", sid)
                    clean_sources.add(clean_sid)
                findings_with_sources.append((s, sorted(clean_sources, key=lambda x: int(re.sub(r"[^0-9]", "", x)) if re.search(r"\d+", x) else 999)))
            if len(findings_with_sources) >= 6:
                break

    for i, (f, source_ids) in enumerate(findings_with_sources[:6], 1):
        text = f[:150]
        if source_ids:
            src_str = ", ".join(source_ids)
            report.append(f"{i}. {text} [来源 {src_str}]")
        else:
            report.append(f"{i}. {text}")
    report.append("")

    # 4. 重要来源
    report.append("## 重要来源")
    seen_domains = set()
    sources = []
    for r in results:
        domain = r.get("domain", "")
        url = r.get("url", "")
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            cat = get_domain_category(domain, url)
            s_type = r.get("_source_type", "未知")
            sources.append((cat, s_type, r))
    sources.sort(key=lambda x: DOMAIN_CREDIBILITY.get(x[0], 1.0), reverse=True)
    for i, (cat, s_type, r) in enumerate(sources[:5], 1):
        title_short = r.get("title", "")[:50]
        domain_short = re.sub(r"^https?://(www\.)?", "", r.get("domain", "")).rstrip("/")
        sid = r.get("_source_id", f"#{i}")
        content_len = r.get("content_length", 0)
        report.append(f"{i}. **{title_short}** | {domain_short} | {s_type} | {sid} (正文约 {content_len} 字)")

    report.append("")

    # 5. 当前结论
    report.append("## 当前结论")
    conclusion_parts = []
    all_text = "".join(all_sentences)
    n = len(results)
    clusters = _cluster_sentences(all_sentences, keywords)
    unique_topics = len(clusters)

    if findings_with_sources:
        if len(findings_with_sources) >= 3:
            conclusion_parts.append(f"搜索结果显示，「{query}」相关主题下共筛选出 {n} 条高质量结果，涵盖 {unique_topics} 个主要话题方向。")
        fact_ratio = len(fact_sentences) / max(len(all_sentences), 1)
        if fact_ratio > 0.3:
            conclusion_parts.append(f"搜索结果中事实性信息占比较高（约 {int(fact_ratio*100)}%），表明该主题有较为丰富的数据与研究支撑。")
        elif fact_ratio > 0.1:
            conclusion_parts.append(f"搜索结果中事实性信息约占 {int(fact_ratio*100)}%，数据和量化信息较为有限，存在进一步深入研究的空间。")
        else:
            conclusion_parts.append("当前搜索结果以概述性和介绍性内容为主，定量数据较少，建议进一步检索具体的统计数据和技术报告。")

        all_cats = set()
        for r in results:
            all_cats.add(get_domain_category(r.get("domain", ""), r.get("url", "")))
        if len(all_cats) >= 4:
            conclusion_parts.append(f"信息来源涵盖 {len(all_cats)} 类不同性质的网站，来源多样性较好，具备一定的综合参考价值。")
        elif len(all_cats) >= 2:
            conclusion_parts.append(f"信息来源主要集中于 {len(all_cats)} 类渠道，建议拓展检索范围以获得更全面的信息。")

    if not conclusion_parts:
        conclusion_parts.append(f"本次搜索共获得 {n} 条相关结果，对该主题进行了初步信息收集。")
    for cp in conclusion_parts:
        report.append(f"- {cp}")
    report.append("")

    # 6. 不确定点
    report.append("## 不确定点")
    uncertainties = _detect_uncertainty(results, all_sentences)
    if uncertainties:
        for u in uncertainties:
            report.append(f"- {u[:120]}")
    else:
        all_domains = set(r.get("domain", "") for r in results)
        report.append(f"- 本次搜索结果来自 {len(all_domains)} 个不同域名，但未检测到明显的观点矛盾或数据争议。")
        report.append("- 部分搜索结果可能包含时效性不足的信息，建议关注发布时间。")
    report.append("")

    # 7. 后续建议
    report.append("## 后续建议")
    suggestions = _generate_suggestions(keywords, results, all_sentences)
    for sug in suggestions:
        report.append(f"- {sug}")
    report.append("")
    report.append(f"> 本小报基于 {deepseek_input} 条高质量搜索结果自动生成，仅供参考，建议交叉验证关键信息。")

    return "\n".join(report)
