"""测试 Bing 搜索解析 - URL 编码版"""
import sys, urllib.parse
sys.stdout.reconfigure(encoding='utf-8')
import requests
from bs4 import BeautifulSoup

for q in ["热泵", "太阳能"]:
    print(f"\n=== {q} ===")
    url = f"https://www.bing.com/search?q={urllib.parse.quote(q)}&count=10"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    print(f"Status: {r.status_code}, Len: {len(r.text)}")
    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("li.b_algo")
    print(f"b_algo items: {len(items)}")
    for it in items[:5]:
        title_el = it.select_one("h2 a")
        snip_el = it.select_one(".b_caption p, .b_lineclamp2")
        dom_el = it.select_one("cite")
        title = title_el.get_text(strip=True) if title_el else "N/A"
        snip = snip_el.get_text(strip=True) if snip_el else ""
        domain = dom_el.get_text(strip=True) if dom_el else ""
        print(f"  [{domain}] {title[:60]}")
        print(f"     snippet: {snip[:80]}")
