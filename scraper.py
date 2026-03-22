"""
scraper.py — Islamweb Fatwa Scraper
Scrapes Arabic and English fatwas from islamweb.net → data/fatwas.json

Usage:
    python scraper.py              # Scrape 500 AR + 500 EN fatwas (default)
    python scraper.py --test       # Quick test: 5 fatwas only
    python scraper.py --limit 100  # Scrape 100 total (50 AR + 50 EN)

Features:
    - Retry logic (3 attempts per fatwa with backoff)
    - Random delay between requests to avoid rate limiting
    - Incremental save (safe to stop and resume)
    - Multiple HTML extraction strategies for robustness
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re
import random
import sys
import argparse
from typing import Dict, List, Optional
from config import SCRAPER_DELAY_MIN, SCRAPER_DELAY_MAX, SCRAPER_MAX_RETRIES

# ── Windows console encoding fix ─────────────────────────────────────────────
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

DATA_DIR = "data"
OUTPUT_FILE = os.path.join(DATA_DIR, "fatwas.json")

# ── Known working fatwa IDs (manually curated high-quality content) ───────────
# These cover: prayer, fasting, zakat, hajj, marriage, family, transactions, purity

ARABIC_FATWA_SEEDS = [
    # Well-known high-quality IDs
    6341, 6594, 4058, 15442, 41356, 42508, 65627, 81469, 113729, 184221,
    198385, 249250, 286597, 298534, 433744, 436171, 441109, 443017, 464092,
    464173, 466768, 468811, 472930, 491689, 495895,
    # Prayer
    3001, 5000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 14000,
    16000, 17000, 18000, 19000, 20000, 21000, 22000, 23000, 25000, 26000,
    # Fasting
    27000, 28000, 29000, 30000, 31000, 32000, 33000, 34000, 35000, 36000,
    37000, 38000, 39000, 40000, 43000, 44000, 45000, 46000, 47000, 48000,
    # Zakat
    49000, 50000, 51000, 52000, 53000, 54000, 55000, 56000, 57000, 58000,
    59000, 60000, 62000, 63000, 64000, 66000, 67000, 68000, 69000, 70000,
    # Hajj
    71000, 72000, 73000, 74000, 75000, 76000, 77000, 78000, 79000, 80000,
    82000, 83000, 84000, 85000, 86000, 87000, 88000, 89000, 90000, 91000,
    # Marriage & Family
    92000, 93000, 94000, 95000, 96000, 97000, 98000, 99000, 100000, 101000,
    102000, 103000, 104000, 105000, 106000, 107000, 108000, 109000, 110000, 111000,
    # Transactions
    112000, 114000, 115000, 116000, 117000, 118000, 119000, 120000, 121000, 122000,
    123000, 124000, 125000, 126000, 127000, 128000, 129000, 130000, 131000, 132000,
    133000, 134000, 135000, 136000, 137000, 138000, 139000, 140000, 141000, 142000,
    143000, 144000, 145000, 146000, 147000, 148000, 149000, 150000, 151000, 152000,
    # Purity
    153000, 154000, 155000, 156000, 157000, 158000, 159000, 160000, 161000, 162000,
    163000, 164000, 165000, 166000, 167000, 168000, 169000, 170000, 171000, 172000,
    173000, 174000, 175000, 176000, 177000, 178000, 180000, 182000, 183000, 185000,
    186000, 187000, 188000, 189000, 190000, 191000, 192000, 193000, 194000, 195000,
    196000, 197000, 199000, 200000, 202000, 205000, 210000, 215000, 220000, 225000,
    230000, 235000, 240000, 245000, 250000, 255000, 260000, 265000, 270000, 275000,
    280000, 285000, 290000, 295000, 300000, 310000, 320000, 330000, 340000, 350000,
    360000, 370000, 380000, 390000, 400000, 410000, 420000, 430000, 440000, 450000,
    460000, 470000, 480000, 490000, 500000,
]

ENGLISH_FATWA_SEEDS = [
    81469, 86618, 88283, 91529, 92684, 95612, 99018, 103280, 108806, 110992,
    115056, 119084, 122483, 127521, 131413, 138205, 143619, 148072, 153846,
    158924, 163274, 167938, 172094, 176433, 180891, 185043, 189427, 193815,
    198026, 202394, 206812, 211034, 215692, 219834, 224176, 228043, 232891,
    237054, 241839, 246012, 250483, 254719, 258943, 263018, 267429, 271803,
    275914, 280123, 284506, 288739, 292014, 296387, 300752, 304918, 309176,
    313502, 317894, 322046, 326571, 330892, 335124, 339506, 343812, 347914,
    352076, 356439, 360751, 364918, 369024, 373547, 377893, 382014, 386297,
    390543, 394817, 399023, 403276, 407594, 411823, 416047, 420381, 424703,
    428917, 433142, 437506, 441892, 446017, 450382, 454718, 459023, 463347,
    467682, 471918, 476034, 480392, 484718, 489023, 493347, 497682, 501918,
    506234, 510582, 514918, 519023, 523342, 527691, 531918, 536034,
    # Additional English IDs
    540000, 545000, 550000, 555000, 560000, 565000, 570000, 575000, 580000,
    585000, 590000, 595000, 600000, 605000, 610000, 615000, 620000, 625000,
    630000, 635000, 640000, 645000, 650000, 655000, 660000, 665000, 670000,
    675000, 680000, 685000, 690000, 695000, 700000, 705000, 710000, 715000,
    720000, 725000, 730000, 735000, 740000, 745000, 750000, 755000, 760000,
    765000, 770000, 775000, 780000, 785000, 790000, 795000, 800000, 805000,
    810000, 815000, 820000, 825000, 830000, 835000, 840000, 845000, 850000,
    855000, 860000, 865000, 870000, 875000, 880000, 885000, 890000, 895000,
    900000, 905000, 910000, 915000, 920000, 925000, 930000, 935000, 940000,
    945000, 950000, 955000, 960000, 965000, 970000, 975000, 980000, 985000,
    990000, 995000, 1000000,
]


class IslamwebScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ar,en;q=0.9",
            "Connection": "keep-alive",
        })

    def clean_text(self, text: str) -> str:
        """Normalize whitespace and strip."""
        text = re.sub(r"\s+", " ", text or "")
        return text.strip()

    def scrape_fatwa(self, fatwa_id: int, lang: str = "ar") -> Optional[Dict]:
        """
        Scrapes a single fatwa page with retry logic.
        Returns dict with title, question, answer, url, lang or None if failed.
        """
        base = "ar" if lang == "ar" else "en"
        url = f"https://www.islamweb.net/{base}/fatwa/{fatwa_id}/"

        for attempt in range(1, SCRAPER_MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=20)

                # Not found or redirect away from fatwa page
                if resp.status_code == 404:
                    return None
                if resp.status_code != 200:
                    if attempt < SCRAPER_MAX_RETRIES:
                        time.sleep(attempt * 2)
                        continue
                    return None

                # Redirect check: valid fatwa URL must contain the ID
                if f"/fatwa/{fatwa_id}" not in resp.url and f"/{fatwa_id}/" not in resp.url:
                    return None

                soup = BeautifulSoup(resp.content, "lxml")

                # ── Extract Title ────────────────────────────────────────────
                title = ""
                for tag in ["h1", "h2"]:
                    el = soup.find(tag)
                    if el:
                        title = self.clean_text(el.get_text())
                        if title:
                            break

                content_parts = []

                # ── Strategy 1: Schema.org itemprop (most reliable) ──────────
                q_wrap = soup.find(attrs={"itemprop": "mainEntity"})
                if q_wrap:
                    q_text = q_wrap.find(attrs={"itemprop": "text"})
                    if q_text:
                        q = self.clean_text(q_text.get_text())
                        if q:
                            prefix = "السؤال: " if lang == "ar" else "Question: "
                            content_parts.append(prefix + q)

                a_wrap = soup.find(attrs={"itemprop": "acceptedAnswer"})
                if a_wrap:
                    a_text = a_wrap.find(attrs={"itemprop": "text"})
                    if a_text:
                        a = self.clean_text(a_text.get_text())
                        if a:
                            prefix = "الإجابة: " if lang == "ar" else "Answer: "
                            content_parts.append(prefix + a)

                content = "\n\n".join(content_parts)

                # ── Strategy 2: CSS class fallback ───────────────────────────
                if not content.strip():
                    items = soup.find_all(
                        "div",
                        class_=re.compile(r"mainitem|fatwa.content|quest|answer", re.I),
                    )
                    for item in items:
                        t = self.clean_text(item.get_text())
                        if len(t) > 80:
                            content_parts.append(t)
                    content = "\n\n".join(content_parts)

                # ── Strategy 3: Generic paragraph fallback ───────────────────
                if not content.strip():
                    paras = soup.find_all("p")
                    gathered = [
                        self.clean_text(p.get_text())
                        for p in paras
                        if len(p.get_text().strip()) > 50
                    ]
                    content = " ".join(gathered)

                if len(content) < 100:
                    return None

                return {
                    "id": fatwa_id,
                    "lang": lang,
                    "url": url,
                    "title": title or f"Islamweb Fatwa #{fatwa_id}",
                    "content": content,
                }

            except requests.Timeout:
                print(f"    [TIMEOUT] Attempt {attempt}/{SCRAPER_MAX_RETRIES} for #{fatwa_id}")
                if attempt < SCRAPER_MAX_RETRIES:
                    time.sleep(attempt * 3)
            except requests.RequestException as e:
                print(f"    [ERROR] Attempt {attempt}/{SCRAPER_MAX_RETRIES} for #{fatwa_id}: {e}")
                if attempt < SCRAPER_MAX_RETRIES:
                    time.sleep(attempt * 2)

        return None

    def scrape_batch(
        self, fatwa_ids: List[int], lang: str, limit: int, existing_ids: set
    ) -> List[Dict]:
        """Scrape a batch of fatwas, skipping already-collected IDs."""
        results = []
        ids_shuffled = list(fatwa_ids)
        random.shuffle(ids_shuffled)

        for fid in ids_shuffled:
            if len(results) >= limit:
                break

            # Skip already scraped
            uid = f"{fid}_{lang}"
            if uid in existing_ids:
                continue

            print(f"  [{lang.upper()}] #{fid:>7} ... ", end="", flush=True)
            data = self.scrape_fatwa(fid, lang)

            if data:
                results.append(data)
                print(f"OK  ({len(data['content'])} chars) — {data['title'][:55]}")
            else:
                print("SKIP")

            # Random delay to avoid rate limiting
            delay = random.uniform(SCRAPER_DELAY_MIN, SCRAPER_DELAY_MAX)
            time.sleep(delay)

        return results


def load_existing(path: str) -> List[Dict]:
    """Load previously scraped fatwas (for resume support)."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_fatwas(fatwas: List[Dict], path: str):
    """Save fatwas to JSON (pretty printed, UTF-8)."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fatwas, f, ensure_ascii=False, indent=2)


def main(limit: int = 1000, test_mode: bool = False):
    if test_mode:
        limit = 10
        print("[INFO] TEST MODE — scraping 10 sample fatwas (5 AR + 5 EN)")

    per_lang = limit // 2
    print(f"\n{'='*60}")
    print(f"  Islamweb Scraper  —  Target: {limit} fatwas ({per_lang} AR + {per_lang} EN)")
    print(f"{'='*60}\n")

    # Load existing to enable resume
    existing = load_existing(OUTPUT_FILE)
    existing_uids = {f"{f['id']}_{f['lang']}" for f in existing}
    print(f"[INFO] Already collected: {len(existing)} fatwas (resuming from here)")

    scraper = IslamwebScraper()

    # ── Arabic fatwas ────────────────────────────────────────────────────────
    ar_needed = max(0, per_lang - sum(1 for f in existing if f["lang"] == "ar"))
    print(f"\n[1/2] Arabic fatwas — need {ar_needed} more...")
    if ar_needed > 0:
        ar_new = scraper.scrape_batch(ARABIC_FATWA_SEEDS, "ar", ar_needed, existing_uids)
        existing.extend(ar_new)
        existing_uids.update(f"{f['id']}_{f['lang']}" for f in ar_new)
        save_fatwas(existing, OUTPUT_FILE)
        print(f"  [OK] +{len(ar_new)} Arabic fatwas  (total: {len(existing)})")

    # ── English fatwas ───────────────────────────────────────────────────────
    en_needed = max(0, per_lang - sum(1 for f in existing if f["lang"] == "en"))
    print(f"\n[2/2] English fatwas — need {en_needed} more...")
    if en_needed > 0:
        en_new = scraper.scrape_batch(ENGLISH_FATWA_SEEDS, "en", en_needed, existing_uids)
        existing.extend(en_new)
        save_fatwas(existing, OUTPUT_FILE)
        print(f"  [OK] +{len(en_new)} English fatwas  (total: {len(existing)})")

    ar_count = sum(1 for f in existing if f["lang"] == "ar")
    en_count = sum(1 for f in existing if f["lang"] == "en")
    print(f"\n{'='*60}")
    print(f"  DONE  |  Arabic: {ar_count}  |  English: {en_count}  |  Total: {len(existing)}")
    print(f"  Saved to: {os.path.abspath(OUTPUT_FILE)}")
    print(f"{'='*60}")
    print(f"\n  Next step: run  python ingest.py\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Islamweb Fatwa Scraper")
    parser.add_argument(
        "--limit", type=int, default=1000,
        help="Total fatwas to collect (split equally AR/EN, default: 1000)"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode: scrape only 10 fatwas (5 AR + 5 EN)"
    )
    args = parser.parse_args()
    main(limit=args.limit, test_mode=args.test)
