"""测试小报生成 - 输出到文件"""
import json, requests

for query in ["热泵", "太阳能"]:
    print("Testing:", query)
    r = requests.post(
        "http://127.0.0.1:8081/search",
        json={"query": query, "search_n": 10, "read_k": 3},
        timeout=120,
    )
    d = r.json()
    fname = f"report_{query}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"=== {query} ===\n")
        f.write(f"Engine: {d.get('engine')}\n")
        f.write(f"Total Results: {d.get('total_found')}\n")
        f.write(f"Keywords: {d.get('keywords')}\n\n")
        f.write("--- Summary ---\n")
        f.write(d.get("summary", "NO SUMMARY"))
        f.write("\n\n--- Titles ---\n")
        for i, rr in enumerate(d.get("results", [])[:10]):
            f.write(f"  {i+1}. {rr['title']} [{rr.get('domain_category','')}]\n")
    print(f"  -> saved to {fname}, length: {len(d.get('summary',''))}")
