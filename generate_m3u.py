#!/usr/bin/env python3
"""
LiveLive24 M3U Generator
JSON içindeki tüm yayın linklerini çözer ve doğrudan tek bir M3U dosyasına yazar.
"""

import json
import base64
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import urllib.request

SOURCE_URL = os.environ.get(
    "SOURCE_URL",
    "https://livelive24.com/test/processed_matches_prioritized.json"
)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "playlist.m3u")
DEFAULT_LOGO = "https://livelive24.com/fav.png"


def fetch_json(url: str) -> list:
    """JSON verisini indirir."""
    print(f"📡 Veri indiriliyor: {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ Toplam {len(data)} maç bulundu.")
            return data
    except Exception as e:
        print(f"❌ Veri çekme hatası: {e}")
        sys.exit(1)


def decode_stream_url(url: str) -> str:
    """dlhd.html?url=<base64> linkindeki gerçek m3u8 adresini çözer."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    if "url" in qs:
        b64_str = qs["url"][0]
        try:
            # Base64 padding tamamlama
            padding = 4 - len(b64_str) % 4
            if padding != 4:
                b64_str += "=" * padding
            return base64.b64decode(b64_str).decode("utf-8")
        except Exception:
            pass

    return url


def build_m3u(matches: list) -> tuple[str, int]:
    """Tüm maçları filtresiz M3U formatına çevirir."""
    lines = [
        '#EXTM3U',
        f'<!-- Güncellenme Tarihi: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
        ""
    ]

    total_streams = 0

    for match in matches:
        name = match.get("name", "Bilinmeyen Yayın")
        league = match.get("playing", "Diğer")
        image = match.get("image") or DEFAULT_LOGO
        match_id = match.get("match_id", "")
        streams = match.get("streams", [])

        if not streams:
            continue

        for stream in streams:
            quality = stream.get("quality", "")
            language = stream.get("language", "tr")
            raw_url = stream.get("url", "")

            if not raw_url:
                continue

            stream_url = decode_stream_url(raw_url)

            # Başlık: "Kasimpasa vs Konyaspor [HD]"
            channel_name = f"{name} [{quality}]" if quality else name

            # M3U Satırları
            extinf = (
                f'#EXTINF:-1 '
                f'tvg-id="{match_id}" '
                f'tvg-name="{channel_name}" '
                f'tvg-logo="{image}" '
                f'tvg-language="{language}" '
                f'group-title="{league}",'
                f'{channel_name}'
            )

            lines.append(extinf)
            lines.append(stream_url)
            lines.append("")
            total_streams += 1

    return "\n".join(lines), total_streams


def main():
    # 1. JSON'ı çek
    matches = fetch_json(SOURCE_URL)

    # 2. M3U dosyasını hazırla
    m3u_content, stream_count = build_m3u(matches)

    # 3. Dosyayı kaydet
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"\n💾 M3U Dosyası Yazıldı: {file_path}")
    print(f"📊 Toplam Eklenen Yayın: {stream_count}")


if __name__ == "__main__":
    main()
