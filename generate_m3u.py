#!/usr/bin/env python3
"""
LiveLive24 TV & Stream Scraper & M3U Generator
HTML sayfalarını tarar, iframe/JS kodlarını çözer, gerçek .m3u8 yayın linklerini yakalar.
"""

import json
import base64
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs, urljoin, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# ─── AYARLAR ───────────────────────────────────────────────
SOURCE_URL = os.environ.get("SOURCE_URL", "https://livelive24.com/tv.json")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "tv.m3u")
DEFAULT_LOGO = "https://livelive24.com/fav.png"
MAX_WORKERS = 15  # Sayfaları paralel tarama hızı (aynı anda 15 sayfa)
TIMEOUT = 12
# ────────────────────────────────────────────────────────────

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "tr,en-US;q=0.9,en;q=0.8"
})


def decode_base64_safely(s: str) -> str:
    """Bozuk veya eksik paddingli Base64 metinleri çözer."""
    try:
        s_clean = s.strip()
        padding = 4 - len(s_clean) % 4
        if padding != 4:
            s_clean += "=" * padding
        decoded = base64.b64decode(s_clean).decode("utf-8", errors="ignore")
        return decoded
    except Exception:
        return ""


def find_m3u8_in_text(text: str) -> str:
    """Metin veya JS içindeki m3u8 linklerini regex ile bulur."""
    # 1. Doğrudan m3u8 linki
    m3u8_matches = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', text)
    if m3u8_matches:
        return m3u8_matches[0]

    # 2. Base64 içinde gizlenmiş m3u8
    b64_matches = re.findall(r'(?:url=|source=|file=|atob\([\'"])([a-zA-Z0-9+/=]{30,})[\'"]?', text)
    for b64 in b64_matches:
        decoded = decode_base64_safely(b64)
        if ".m3u8" in decoded or decoded.startswith("http"):
            nested_m3u8 = find_m3u8_in_text(decoded)
            if nested_m3u8:
                return nested_m3u8
            if decoded.startswith("http"):
                return decoded

    # 3. Clappr / JWPlayer kaynakları
    js_source = re.findall(r'(?:source|file|src)\s*:\s*["\'](https?://[^"\']+)["\']', text, re.IGNORECASE)
    for src in js_source:
        if ".m3u8" in src or "live" in src or "stream" in src:
            return src

    return ""


def scrape_stream_url(page_url: str, depth: int = 0, max_depth: int = 2) -> str:
    """
    Verilen HTML sayfasını ziyaret eder, iframe'leri takip eder ve asıl yayını bulur.
    """
    if not page_url or depth > max_depth:
        return ""

    page_url = unquote(page_url.strip())

    # Eğer verilen link zaten doğrudan .m3u8 ise taramaya gerek yok
    if ".m3u8" in page_url and not ("html" in page_url or "?" in page_url.split(".m3u8")[-1]):
        return page_url

    # dlhd.html?url=<base64> durumunu hızlıca çöz
    parsed = urlparse(page_url)
    qs = parse_qs(parsed.query)
    if "url" in qs:
        decoded = decode_base64_safely(qs["url"][0])
        if ".m3u8" in decoded:
            return decoded
        elif decoded.startswith("http"):
            page_url = decoded

    try:
        resp = SESSION.get(page_url, timeout=TIMEOUT, allow_redirects=True, headers={"Referer": page_url})
        if resp.status_code != 200:
            return ""

        html = resp.text

        # Sayfa içeriğinde m3u8 var mı bak
        found_stream = find_m3u8_in_text(html)
        if found_stream:
            return found_stream

        # Sayfa içindeki <iframe> linklerini yakala ve içeri gir
        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for iframe_src in iframes:
            if iframe_src.startswith("//"):
                iframe_src = "https:" + iframe_src
            elif not iframe_src.startswith("http"):
                iframe_src = urljoin(page_url, iframe_src)

            # Reklam/sosyal medya iframelerini atla
            if any(ad in iframe_src for ad in ["google", "facebook", "twitter", "ads", "chat", "disqus"]):
                continue

            stream = scrape_stream_url(iframe_src, depth=depth + 1, max_depth=max_depth)
            if stream:
                return stream

    except Exception:
        pass

    return ""


def fetch_and_parse_json(url: str) -> list:
    """JSON'dan kanal listesini çeker ve normalize eder."""
    print(f"📡 JSON indiriliyor: {url}")
    try:
        r = SESSION.get(url, timeout=20)
        data = r.json()
    except Exception as e:
        print(f"❌ JSON çekilemedi: {e}")
        sys.exit(1)

    raw_items = []
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        for cat, val in data.items():
            if isinstance(val, list):
                for v in val:
                    if isinstance(v, dict):
                        if "category" not in v:
                            v["category"] = cat
                        raw_items.append(v)
            elif isinstance(val, dict):
                raw_items.append(val)

    normalized_channels = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        name = item.get("name") or item.get("channel_name") or item.get("title") or "Kanal"
        logo = item.get("image") or item.get("logo") or DEFAULT_LOGO
        category = item.get("category") or item.get("playing") or item.get("group") or "Canlı TV"
        channel_id = str(item.get("id") or item.get("match_id") or "")

        # 1. Streams listesi varsa
        if "streams" in item and isinstance(item["streams"], list):
            for st in item["streams"]:
                if isinstance(st, dict):
                    link = st.get("url") or st.get("link") or ""
                    q = st.get("quality", "")
                    st_name = f"{name} [{q}]" if q else name
                    if link:
                        normalized_channels.append({
                            "id": channel_id,
                            "name": st_name,
                            "logo": logo,
                            "category": category,
                            "page_url": link
                        })
        # 2. Tekil sayfa/url linki varsa (Örn: page: "tv/cbsgoalzo.html" veya url: "...")
        direct_link = item.get("url") or item.get("page") or item.get("stream_url")
        if direct_link and isinstance(direct_link, str):
            if not direct_link.startswith("http"):
                direct_link = urljoin("https://livelive24.com/", direct_link)
            normalized_channels.append({
                "id": channel_id,
                "name": name,
                "logo": logo,
                "category": category,
                "page_url": direct_link
            })

    return normalized_channels


def process_channel_task(channel: dict) -> dict:
    """Tek bir kanalın yayın linkini arayan iş parçacığı (worker)."""
    page_url = channel["page_url"]
    resolved_stream = scrape_stream_url(page_url)
    channel["stream_url"] = resolved_stream
    return channel


def main():
    channels = fetch_and_parse_json(SOURCE_URL)
    print(f"🔍 Toplam {len(channels)} kanal tespit edildi. Yayın linkleri kazınıyor (Scraping)...")

    resolved_channels = []
    # Çoklu iş parçacığı (Thread) ile sayfaları hızlıca tara
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_channel_task, ch) for ch in channels]
        for future in as_completed(futures):
            res = future.result()
            if res.get("stream_url"):
                resolved_channels.append(res)
                print(f"  [+] BULUNDU: {res['name']} -> {res['stream_url'][:60]}...")
            else:
                print(f"  [-] Bulunamadı: {res['name']}")

    # M3U formatında birleştir
    lines = [
        '#EXTM3U',
        f'<!-- Güncellenme Tarihi: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
        ""
    ]

    for ch in resolved_channels:
        extinf = (
            f'#EXTINF:-1 '
            f'tvg-id="{ch["id"]}" '
            f'tvg-name="{ch["name"]}" '
            f'tvg-logo="{ch["logo"]}" '
            f'group-title="{ch["category"]}",'
            f'{ch["name"]}'
        )
        lines.append(extinf)
        lines.append(ch["stream_url"])
        lines.append("")

    # Dosyaya kaydet
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n🎉 TAMAMLANDI! {len(resolved_channels)}/{len(channels)} adet çalışan yayın M3U'ya yazıldı.")
    print(f"📁 Dosya: {file_path}")


if __name__ == "__main__":
    main()
