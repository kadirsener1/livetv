#!/usr/bin/env python3
"""
LiveLive24 NTV JSON to M3U Playlist Generator
JSON içindeki tüm yayınları ve linkleri çözer, tek bir M3U dosyası oluşturur.
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
    """dlhd.html?url=<base64> veya şifreli parametrelerden gerçek m3u8 linkini çözer."""
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

    # 2. Doğrudan Base64 string verilmişse
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
    """JSON içeriğini M3U formatına çevirir."""
    lines = [
        '#EXTM3U',
        f'<!-- Güncellenme Tarihi: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
        ""
    ]

    total_streams = 0

    # JSON liste veya sözlük yapısını normalize et
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                items.extend(val)
            elif isinstance(val, dict):
                items.append(val)

    for item in items:
        if not isinstance(item, dict):
            continue

        name = item.get("name") or item.get("title") or item.get("channel_name") or "Bilinmeyen Yayın"
        group = item.get("playing") or item.get("category") or item.get("group") or "Genel"
        logo = item.get("image") or item.get("logo") or DEFAULT_LOGO
        item_id = str(item.get("match_id") or item.get("id") or "")
        
        # Streams dizisi varsa
        streams = item.get("streams", [])
        if streams and isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                
                raw_url = stream.get("url") or stream.get("stream_url") or ""
                if not raw_url:
                    continue

                quality = stream.get("quality", "")
                stream_name = stream.get("name", "")
                
                # İsimlendirme
                if quality:
                    channel_name = f"{name} [{quality}]"
                elif stream_name:
                    channel_name = f"{name} ({stream_name})"
                else:
                    channel_name = name

                final_url = decode_stream_url(raw_url)

                extinf = (
                    f'#EXTINF:-1 '
                    f'tvg-id="{item_id}" '
                    f'tvg-name="{channel_name}" '
                    f'tvg-logo="{logo}" '
                    f'group-title="{group}",'
                    f'{channel_name}'
                )

                lines.append(extinf)
                lines.append(final_url)
                lines.append("")
                total_streams += 1

        # Doğrudan url varsa
        elif item.get("url") or item.get("stream_url"):
            raw_url = item.get("url") or item.get("stream_url")
            final_url = decode_stream_url(raw_url)

            extinf = (
                f'#EXTINF:-1 '
                f'tvg-id="{item_id}" '
                f'tvg-name="{name}" '
                f'tvg-logo="{logo}" '
                f'group-title="{group}",'
                f'{name}'
            )

            lines.append(extinf)
            lines.append(final_url)
            lines.append("")
            total_streams += 1

    return "\n".join(lines), total_streams


def main():
    data = fetch_json(SOURCE_URL)
    m3u_content, count = build_m3u(data)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"\n✅ Toplam {count} adet yayın M3U'ya eklendi.")
    print(f"💾 Dosya kaydedildi: {file_path}")


if __name__ == "__main__":
    main()
