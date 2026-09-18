#!/usr/bin/env python3
"""
LiveLive24 NTV JSON to M3U Playlist Generator
ntv.json içindeki 'sources' yapısını okur, base64 linkleri çözer ve M3U yazar.
"""

import json
import base64
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs, unquote
import urllib.request

# ─── AYARLAR ───────────────────────────────────────────────
SOURCE_URL = os.environ.get(
    "SOURCE_URL",
    "https://livelive24.com/test/ntv/ntv.json"
)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "playlist.m3u")
DEFAULT_LOGO = "https://livelive24.com/fav.png"
# ────────────────────────────────────────────────────────────


def fetch_json(url: str):
    """JSON verisini indirir."""
    print(f"📡 Veri indiriliyor: {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception as e:
        print(f"❌ JSON indirme hatası: {e}")
        sys.exit(1)


def decode_stream_url(url: str) -> str:
    """dlhd.html?url=<base64> linkini çözer."""
    if not url:
        return ""
    
    url = unquote(url.strip())
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    # 1. ?url=base64 parametresi kontrolü
    if "url" in qs:
        b64_str = qs["url"][0]
        try:
            padding = 4 - len(b64_str) % 4
            if padding != 4:
                b64_str += "=" * padding
            decoded = base64.b64decode(b64_str).decode("utf-8", errors="ignore")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass

    # 2. Doğrudan Base64 string ise
    if url.startswith("aHR0c"):
        try:
            padding = 4 - len(url) % 4
            if padding != 4:
                url += "=" * padding
            decoded = base64.b64decode(url).decode("utf-8", errors="ignore")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass

    return url


def build_m3u(data) -> tuple[str, int]:
    """JSON içeriğini M3U formatına çevirir (Yeni 'sources' uyumlu)."""
    lines = [
        '#EXTM3U',
        f'<!-- Güncellenme Tarihi: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
        ""
    ]

    total_streams = 0

    # Liste formatında veri geleceğini varsayıyoruz
    items = data if isinstance(data, list) else []

    for item in items:
        if not isinstance(item, dict):
            continue

        # Ana Bilgiler
        title = item.get("title") or item.get("name") or "Bilinmeyen Maç"
        group = item.get("tournament") or item.get("category") or "Spor Etkinliği"
        logo = item.get("image") or item.get("logo") or DEFAULT_LOGO
        item_id = str(item.get("id") or "")

        # ⚠️ Yeni formatta 'sources' listesi kullanılır, eski formatta 'streams'
        sources = item.get("sources") or item.get("streams") or []

        if isinstance(sources, list) and len(sources) > 0:
            for src in sources:
                if not isinstance(src, dict):
                    continue

                raw_url = src.get("url") or src.get("stream_url") or ""
                if not raw_url:
                    continue

                # Yayın İsmi (Örn: Stream 1 [en], Stream SD vb.)
                stream_name = src.get("channelName") or src.get("name") or src.get("quality") or "Yayın"
                channel_title = f"{title} ({stream_name})"

                final_url = decode_stream_url(raw_url)

                # M3U Satır formatı
                extinf = (
                    f'#EXTINF:-1 '
                    f'tvg-id="{item_id}" '
                    f'tvg-name="{channel_title}" '
                    f'tvg-logo="{logo}" '
                    f'group-title="{group}",'
                    f'{channel_title}'
                )

                lines.append(extinf)
                lines.append(final_url)
                lines.append("")
                total_streams += 1

    return "\n".join(lines), total_streams


def main():
    # 1. JSON'ı çek
    data = fetch_json(SOURCE_URL)
    
    # 2. M3U formatına dönüştür
    m3u_content, count = build_m3u(data)

    # 3. Dosyayı kaydet
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"\n✅ Başarılı! Toplam {count} adet yayın M3U'ya eklendi.")
    print(f"💾 Dosya kaydedildi: {file_path}")


if __name__ == "__main__":
    main()
