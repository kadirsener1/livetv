#!/usr/bin/env python3
"""
LiveLive24 TV Kanalları M3U Generator
tv.json dosyasındaki tüm kanalları ve yayınları tek bir M3U dosyasına dönüştürür.
"""

import json
import base64
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs, unquote
import urllib.request
import urllib.error

# ─── AYARLAR ───────────────────────────────────────────────
SOURCE_URL = os.environ.get("SOURCE_URL", "https://livelive24.com/tv.json")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "tv.m3u")
DEFAULT_LOGO = "https://livelive24.com/fav.png"
# ────────────────────────────────────────────────────────────


def fetch_json(url: str):
    """tv.json dosyasını web sitesinden indirir."""
    print(f"📡 Veri indiriliyor: {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception as e:
        print(f"❌ Veri çekme hatası: {e}")
        sys.exit(1)


def decode_stream_url(url: str) -> str:
    """
    Link içindeki base64 kodlu stream URL'sini çözer.
    Örn: dlhd.html?url=aHR0c... -> https://.../playlist.m3u8
    """
    if not url:
        return ""

    url = unquote(url.strip())
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    # ?url= parametresi kontrolü
    if "url" in qs:
        b64_str = qs["url"][0]
        try:
            padding = 4 - len(b64_str) % 4
            if padding != 4:
                b64_str += "=" * padding
            decoded = base64.b64decode(b64_str).decode("utf-8")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass

    # Doğrudan base64 formatında gönderildiyse
    if url.startswith("aHR0c"):
        try:
            padding = 4 - len(url) % 4
            if padding != 4:
                url += "=" * padding
            decoded = base64.b64decode(url).decode("utf-8")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass

    return url


def process_channels(data) -> list:
    """JSON yapısını düzleştirip normalize eder."""
    channels = []

    # Eğer data liste ise
    if isinstance(data, list):
        items = data
    # Eğer data dict ise (kategoriye göre grupluysa)
    elif isinstance(data, dict):
        items = []
        for cat_name, val in data.items():
            if isinstance(val, list):
                for v in val:
                    if isinstance(v, dict) and "category" not in v:
                        v["category"] = cat_name
                    items.append(v)
            elif isinstance(val, dict):
                items.append(val)
    else:
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue

        name = item.get("name") or item.get("channel_name") or item.get("title") or "Bilinmeyen Kanal"
        logo = item.get("image") or item.get("logo") or item.get("icon") or DEFAULT_LOGO
        category = item.get("category") or item.get("group") or item.get("country") or "Genel TV"
        channel_id = str(item.get("id") or item.get("channel_id") or "")

        # 1. Durum: 'streams' dizisi varsa
        if "streams" in item and isinstance(item["streams"], list):
            for stream in item["streams"]:
                if isinstance(stream, dict):
                    raw_url = stream.get("url") or stream.get("stream_url") or ""
                    quality = stream.get("quality", "")
                    lang = stream.get("language", "tr")
                    stream_name = stream.get("name", "")
                    
                    full_name = f"{name} [{quality}]" if quality else (f"{name} ({stream_name})" if stream_name else name)
                    
                    if raw_url:
                        channels.append({
                            "id": channel_id,
                            "name": full_name,
                            "logo": logo,
                            "category": category,
                            "language": lang,
                            "url": decode_stream_url(raw_url)
                        })

        # 2. Durum: Doğrudan 'url' veya 'stream_url' varsa
        direct_url = item.get("url") or item.get("stream_url") or item.get("link")
        if direct_url and isinstance(direct_url, str):
            channels.append({
                "id": channel_id,
                "name": name,
                "logo": logo,
                "category": category,
                "language": item.get("language", "tr"),
                "url": decode_stream_url(direct_url)
            })

    return channels


def build_m3u(channels: list) -> str:
    """IPTV uyumlu M3U içeriği oluşturur."""
    lines = [
        '#EXTM3U',
        f'<!-- Oluşturulma Tarihi: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
        ""
    ]

    for ch in channels:
        url = ch.get("url", "")
        if not url:
            continue

        extinf = (
            f'#EXTINF:-1 '
            f'tvg-id="{ch.get("id", "")}" '
            f'tvg-name="{ch.get("name", "")}" '
            f'tvg-logo="{ch.get("logo", "")}" '
            f'tvg-language="{ch.get("language", "tr")}" '
            f'group-title="{ch.get("category", "Genel")}",'
            f'{ch.get("name", "")}'
        )

        lines.append(extinf)
        lines.append(url)
        lines.append("")

    return "\n".join(lines)


def main():
    # 1. JSON verisini çek
    raw_data = fetch_json(SOURCE_URL)

    # 2. Kanalları işle ve URL'leri çöz
    channel_list = process_channels(raw_data)
    print(f"✅ Toplam {len(channel_list)} adet yayın/kanal çözüldü.")

    # 3. M3U formatına çevir
    m3u_text = build_m3u(channel_list)

    # 4. Dosyaya kaydet
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(m3u_text)

    print(f"💾 M3U Dosyası Başarıyla Yazıldı: {file_path}")


if __name__ == "__main__":
    main()
