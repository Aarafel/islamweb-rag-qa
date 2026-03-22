"""
scrape_specific.py — Fetch specific Islamweb fatwa/article URLs and save to fatwas.json.
Uses a smarter extractor that handles both fatwa and article page structures.
"""
import json
import os
import sys
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

URLS = [
    "https://www.islamweb.net/ar/fatwa/378016/",  # حكم الصيام في السفر
    "https://www.islamweb.net/ar/fatwa/323833/",  # بيان وجوب الجمعة
    "https://www.islamweb.net/ar/fatwa/265213/",  # مقدار زكاة الفطر
    "https://www.islamweb.net/ar/article/136222/", # حكم الحج وشروط وجوبه
    "https://www.islamweb.net/ar/fatwa/39350/",    # فتاوى في الحج (خطوات الحج)
    "https://www.islamweb.net/ar/fatwa/55629/",    # الفرق بين الحج والعمرة
    "https://www.islamweb.net/ar/article/136278/", # صفة الحج
    "https://www.islamweb.net/ar/article/136215/", # أركان الحج وواجباته وسننه
    "https://www.islamweb.net/ar/fatwa/441715/",   # السعي للجمعة
    "https://www.islamweb.net/ar/fatwa/28770/",    # تفويت صلاة الجمعة
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ar,en;q=0.9",
}

def extract_all_text(soup: BeautifulSoup) -> str:
    """Extract ALL readable text from the page body, stripping nav/footer/scripts."""
    # Remove unwanted elements
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header", "aside",
                               "meta", "link", "button", "form", "iframe", "svg"]):
        tag.decompose()

    # Try to find the main content container first
    containers = [
        ".zawj-content", ".fatwa-answer", ".article-content", ".text-content",
        ".fatwa-body", ".item-content", ".content-body", "article", "main",
        "#content", ".content", "#main", ".main"
    ]
    
    content_el = None
    for sel in containers:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 200:
            content_el = el
            break

    target = content_el if content_el else soup.body if soup.body else soup
    
    # Use get_text() which NEVER includes raw HTML tags
    raw = target.get_text(separator="\n")
    
    # Aggressive cutoff: Throw away everything after "Related Fatwas" or comments
    # This prevents the list of related fatwa titles from polluting the chunks
    cut_markers = ["مواد ذات صلة", "مواد ذات الصله", "مشاركات الزوار", "التعليقات"]
    for marker in cut_markers:
        if marker in raw:
            raw = raw.split(marker)[0]

    lines = [ln.strip() for ln in raw.splitlines()]
    
    # Filter noise: too-short lines AND obvious navigation/footer patterns
    noise_patterns = [
        "جميع الحقوق محفوظة", "copyright", "©",
        "اعدادات الخط", "مشاركات الزوار", "خدمات تفاعلية",
        "وثيقة الخصوصية", "اتفاقية الخدمة", "مواقيت الصلاة",
        "مواد ذات الصله", "مواد ذات صلة",
        "محاور رئيسية", "محاور فرعية", "الرحمة المهداة",
        "اشترك بالقائمة البريدية", "بريدك الإلكتروني",
        "البحث عن فتوى", "من فضلك اختار",
        "الذنوب والمعاصي تضر", "للمعاصي آثارا",  # repeated sidebar ad text
        "loaded from cached", "cache"
    ]
    
    def is_noise(line: str) -> bool:
        ll = line.lower()
        return any(p.lower() in ll for p in noise_patterns)
    
    lines = [ln for ln in lines if len(ln) > 15 and not is_noise(ln)]
    
    return "\n".join(lines)


def extract_title(soup: BeautifulSoup) -> str:
    for sel in ["h1", ".fatwa-title", ".page-title", ".article-title", "title"]:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(strip=True)
            if t and len(t) < 200:
                return t
    return "مقال إسلامي"


def scrape_url(url: str) -> dict | None:
    print(f"  Scraping: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")

        title = extract_title(soup)
        content = extract_all_text(soup)

        if len(content) < 100:
            print(f"    [WARN] Too little content ({len(content)} chars)")
            return None

        # derive a unique id from the URL path
        parts = [p for p in url.rstrip("/").split("/") if p]
        uid = parts[-1] if parts else url

        return {
            "id": uid,
            "url": url,
            "title": title,
            "question": "",
            "content": content,
            "category": "مختار",
            "lang": "ar",
        }
    except Exception as e:
        print(f"    [ERROR] {e}")
        return None


def main():
    target_file = "data/fatwas.json"

    data = []
    if os.path.exists(target_file):
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    print(f"Existing fatwas: {len(data)}")
    existing_urls = {d.get("url", "") for d in data}

    added = 0
    updated = 0
    for url in URLS:
        item = scrape_url(url)
        if not item:
            continue

        # Always force-update these target URLs with freshly cleaned content
        existing = next((d for d in data if d.get("url", "") == url), None)
        if existing:
            existing.update(item)
            print(f"    -> Updated '{item['title'][:40]}' ({len(item['content'])} chars)")
            updated += 1
        else:
            data.append(item)
            added += 1
            print(f"    -> Added '{item['title'][:50]}' ({len(item['content'])} chars)")

    if added + updated > 0:
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\nSaved: {added} added, {updated} updated → total {len(data)} fatwas.")
    else:
        print("\nNo changes.")


if __name__ == "__main__":
    main()
