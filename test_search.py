"""测试搜索闭环 - 编码安全版"""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import requests

for query in ["热泵", "太阳能"]:
    print(f"\n{'='*60}")
    print(f"测试 query: {query}")
    print(f"{'='*60}")
    r = requests.post(
        "http://127.0.0.1:8081/search",
        json={"query": query, "search_n": 10, "read_k": 3},
        timeout=120,
    )
    d = r.json()
    print(f"引擎: {d.get('engine')} | 结果数: {d.get('total_found')} | 关键词: {d.get('keywords')}")
    print("--- 标题列表 ---")
    for i, rr in enumerate(d.get("results", [])[:10]):
        print(f"  {i+1}. {rr['title'][:70]} [{rr.get('domain_category','')}]")
    print("--- 总结小报 (前200字) ---")
    summary = d.get("summary", "")
    print(summary[:200])
    print()
