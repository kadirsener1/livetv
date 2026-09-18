#!/usr/bin/env python3
"""
LiveLive24 M3U Playlist Generator
JSON kaynağından maç yayınlarını çeker, base64 URL'leri çözer
ve IPTV uyumlu M3U dosyası üretir.
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
    "https://livelive24.com/test/processed_matches_prioritized.json"
)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "playlist.m3u")
LOGO_URL = "https://livelive24.com/fav.png"

# status_id filtreleri: 1=canlı, 2=yakında, 3=bitti
INCLUDE_STATUSES = [1, 2]
# ────────────────────────────────────────────────────────────


def fetch_json(url: str) -> list:
    """URL'den JSON verisini indirir."""
    print(f"📡 Veri indiriliyor: {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; M3UGenerator/1.0)"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ {len(data)} maç bulundu.")
            return data
    except urllib.error.URLError as e:
        print(f"❌ İndirme hatası: {e}")
        sys.exit(1)


def decode_stream_url(url: str) -> str:
    """
    dlhd.html?url=<base64> formatındaki URL'den
    gerçek m3u8 adresini çözer.
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    if "url" in qs:
        b64_str = qs["url"][0]
        try:
            # Base64 padding düzeltmesi
            padding = 4 - len(b64_str) % 4
            if padding != 4:
                b64_str += "=" * padding
            decoded = base64.b64decode(b64_str).decode("utf-8")
            return decoded
        except Exception:
            pass

    # Çözülemezse orijinal URL'yi döndür
    return url


def build_m3u(matches: list) -> str:
    """Maç listesinden M3U içeriği oluşturur."""
    lines = [
        '#EXTM3U x-tvg-url=""',
        f'<!-- Oluşturulma: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
        ""
    ]

    total_streams = 0

    for match in matches:
        status_id = match.get("status_id", 0)
        if status_id not in INCLUDE_STATUSES:
            continue

        name = match.get("name", "Bilinmeyen Maç")
        league = match.get("playing", "Bilinmeyen Lig")
        date = match.get("date", "")
        time = match.get("time", "")
        score = match.get("score", "")
        image = match.get("image", LOGO_URL)
        streams = match.get("streams", [])

        if not streams:
            continue

        # Durum etiketi
        if status_id == 1:
            status_tag = "🔴 CANLI"
        elif status_id == 2:
            status_tag = "🟡 YAKINDA"
        else:
            status_tag = "⚪"

        for stream in streams:
            stream_name = stream.get("name", "Stream")
            quality = stream.get("quality", "")
            language = stream.get("language", "en")
            raw_url = stream.get("url", "")

            if not raw_url:
                continue

            decoded_url = decode_stream_url(raw_url)

            # Kanal adı
            channel_name = f"{status_tag} {name} [{quality}]"
            if score and score != "0 - 0":
                channel_name = f"🔴 {name} ({score}) [{quality}]"

            # EXTINF satırı
            extinf = (
                f'#EXTINF:-1 '
                f'tvg-id="{match.get("match_id", "")}" '
                f'tvg-name="{channel_name}" '
                f'tvg-logo="{image}" '
                f'tvg-language="{language}" '
                f'group-title="{league}",'
                f'{channel_name}'
            )

            lines.append(extinf)
            lines.append(decoded_url)
            lines.append("")
            total_streams += 1

    print(f"📝 Toplam {total_streams} yayın M3U'ya yazıldı.")
    return "\n".join(lines)


def main():
    # 1) JSON'ı indir
    matches = fetch_json(SOURCE_URL)

    # 2) M3U içeriği oluştur
    m3u_content = build_m3u(matches)

    # 3) Dosyaya yaz
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"💾 M3U dosyası kaydedildi: {output_path}")

    # 4) Özet bilgi
    live = sum(1 for m in matches if m.get("status_id") == 1)
    upcoming = sum(1 for m in matches if m.get("status_id") == 2)
    print(f"📊 Özet: {live} canlı, {upcoming} yaklaşan maç")


if __name__ == "__main__":
    main()
