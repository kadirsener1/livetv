#!/usr/bin/env python3
"""
LiveLive24 Sports Stream Scraper & M3U Generator
tv.json içinden SADECE "Sports" kategorisindeki kanalları seçer,
sayfalarını tarayıp asıl .m3u8 linklerini ayıklar ve M3U üretir.
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
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "sports.m3u")
DEFAULT_LOGO = "https://livelive24.com/fav.png"
MAX_WORKERS = 15  # Paralel sayfa tarama hızı
TIMEOUT = 12

# Sadece bu kelimeleri içeren kategoriler taranır (Sports, Spor, Sport vb.)
SPORTS_KEYWORDS = ["sport", "sports", "spor"]
# ────────────────────────────────────────────────────────────

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "tr,en-US;q=0.9,en;q=0.8"
})


def is_sports_category(category_name: str) -> bool:
    """Kategorinin Spor olup olmadığını denetler."""
    if not category_name:
        return False
    cat_lower = str(category_name).lower()
    return any(keyword in cat_lower for keyword in SPORTS_KEYWORDS)


def decode_base64_safely(s: str) -> str:
    """Bozuk/eksik paddingli Base64 metinleri çözer."""
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
    """HTML veya JS içindeki m3u8 linkini regex ile yakalar."""
    # 1. Doğrudan m3u8 linki
    m3u8_matches = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', text)
    if m3u8_matches:
        return m3u8_matches[0]

    # 2. Base64 içinde gizlenmiş m3u8
    b64_matches = re.findall(r'(?:url=|source=|file=|atob\([\'"])([a-zA-Z0-9+/=]{30,})[\'"]?', text)
    for b64 in b64_matches:
        decoded = decode_base64_safely(b64)
        if ".m3u8" in decoded:
            nested_m3u8 = find_m3u8_in_text(decoded)
            return nested_m3u8 if nested_m3u8 else decoded
        elif decoded.startswith("http"):
            return decoded

    # 3. Clappr / JWPlayer kaynakları
    js_source = re.findall(r'(?:source|file|src)\s*:\s*["\'](https?://[^"\']+)["\']', text, re.IGNORECASE)
    for src in js_source:
        if ".m3u8" in src or "live" in src or "stream" in src:
            return src

    return ""


def scrape_stream_url(page_url: str, depth: int = 0, max_depth: int = 2) -> str:
    """HTML sayfasına girip iframe ve JS kodlarını tarayarak yayını bulur."""
    if not page_url or depth > max_depth:
        return ""

    page_url = unquote(page_url.strip())

    # Doğrudan m3u8 linki ise taramaya gerek yok
    if ".m3u8" in page_url and not ("html" in page_url or "?" in page_url.split(".m3u8")[-1]):
        return page_url

    # Base64 parametreli url kontrolü
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

        # Sayfa içeriğinde m3u8 ara
        found_stream = find_m3u8_in_text(html)
        if found_stream:
            return found_stream

        # iframe içlerine gir
        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for iframe_src in iframes:
            if iframe_src.startswith("//"):
                iframe_src = "https:" + iframe_src
            elif not iframe_src.startswith("http"):
                iframe_src = urljoin(page_url, iframe_src)

            if any(ad in iframe_src for ad in ["google", "facebook", "twitter", "ads", "chat", "disqus"]):
                continue

            stream = scrape_stream_url(iframe_src, depth=depth + 1, max_depth=max_depth)
            if stream:
                return stream

    except Exception:
        pass

    return ""


def fetch_sports_channels(url: str) -> list:
    """JSON'dan SADECE Spor kategorisindeki kanalları filtreler."""
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
            # Eğer JSON kategori başlıklarına göre ayrılmışsa
            if is_sports_category(cat):
                if isinstance(val, list):
                    for v in val:
                        if isinstance(v, dict):
                            v["category"] = cat
                            raw_items.append(v)
            else:
                # Kategori adı spor değilse ama içinde spor olabilir mi kontrolü
                if isinstance(val, list):
                    for v in val:
                        if isinstance(v, dict) and is_sports_category(v.get("category", "")):
                            raw_items.append(v)

    sports_channels = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        category = item.get("category") or item.get("playing") or item.get("group") or ""
        
        # ⚠️ SPOR KONTROLÜ (Sadece spor olanları kabul et)
        if not is_sports_category(category):
            continue

        name = item.get("name") or item.get("channel_name") or item.get("title") or "Spor Kanalı"
        logo = item.get("image") or item.get("logo") or DEFAULT_LOGO
        channel_id = str(item.get("id") or item.get("match_id") or "")

        # 1. Streams dizisi varsa
        if "streams" in item and isinstance(item["streams"], list):
            for st in item["streams"]:
                if isinstance(st, dict):
                    link = st.get("url") or st.get("link") or ""
                    q = st.get("quality", "")
                    st_name = f"{name} [{q}]" if q else name
                    if link:
                        sports_channels.append({
                            "id": channel_id,
                            "name": st_name,
                            "logo": logo,
                            "category": category,
                            "page_url": link
                        })

        # 2. Doğrudan tekil sayfa linki varsa
        direct_link = item.get("url") or item.get("page") or item.get("stream_url")
        if direct_link and isinstance(direct_link, str):
            if not direct_link.startswith("http"):
                direct_link = urljoin("https://livelive24.com/", direct_link)
            sports_channels.append({
                "id": channel_id,
                "name": name,
                "logo": logo,
                "category": category,
                "page_url": direct_link
            })

    return sports_channels


def process_channel_task(channel: dict) -> dict:
    """Her bir kanal için arka planda yayın arar."""
    channel["stream_url"] = scrape_stream_url(channel["page_url"])
    return channel


def main():
    # 1. Sadece spor kanallarını filtrele
    channels = fetch_sports_channels(SOURCE_URL)
    print(f"⚽ {len(channels)} adet SPOR kanalı tespit edildi. Yayın linkleri aranıyor...")

    if not channels:
        print("⚠️ Hiç spor kanalı bulunamadı. Kategori isimlerini kontrol edin.")
        return

    # 2. Sayfaları tara ve stream URL'lerini bul
    resolved_channels = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_channel_task, ch) for ch in channels]
        for future in as_completed(futures):
            res = future.result()
            if res.get("stream_url"):
                resolved_channels.append(res)
                print(f"  [+] BULUNDU: {res['name']}")
            else:
                print(f"  [-] Bulunamadı: {res['name']}")

    # 3. M3U dosyasını oluştur
    lines = [
        '#EXTM3U',
        f'<!-- Spor Kanalları | Güncellenme: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
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

    # 4. Dosyaya kaydet
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n🎉 TAMAMLANDI! {len(resolved_channels)} spor yayını kaydedildi.")
    print(f"📁 Dosya: {file_path}")


if __name__ == "__main__":
    main()
