#!/usr/bin/env python3
"""
LiveLive24 - Tek M3U Playlist Oluşturucu
Canlı ve Yaklaşan tüm maçları tek bir playlist.m3u dosyasında toplar.
"""

import json
import base64
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error

# ─── AYARLAR ───────────────────────────────────────────────
SOURCE_URL = os.environ.get(
    "SOURCE_URL",
    "https://livelive24.com/test/processed_matches_prioritized.json"
)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "playlist.m3u")
DEFAULT_LOGO = "https://livelive24.com/fav.png"
# ────────────────────────────────────────────────────────────


def fetch_json(url: str) -> list:
    """JSON verisini çeker."""
    print(f"📡 Veri indiriliyor: {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ Toplam {len(data)} maç verisi alındı.")
            return data
    except Exception as e:
        print(f"❌ Veri çekme hatası: {e}")
        sys.exit(1)


def decode_stream_url(url: str) -> str:
    """dlhd.html?url=<base64> linkini m3u8 formatına çevirir."""
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


def generate_single_m3u(matches: list) -> tuple[str, int, int]:
    """Tüm canlı ve yaklaşan maçları tek M3U'ya yazar."""
    lines = [
        '#EXTM3U x-tvg-url=""',
        f'<!-- Güncellenme Tarihi: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} -->',
        ""
    ]

    live_count = 0
    upcoming_count = 0

    # Canlı maçları önce, yaklaşanları sonra getirmek için sıralıyoruz
    # status_id: 1 (Canlı), 2 (Yakında)
    valid_matches = [m for m in matches if m.get("status_id") in [1, 2]]
    valid_matches.sort(key=lambda m: (m.get("status_id", 99), m.get("league_order", 999)))

    for match in valid_matches:
        status_id = match.get("status_id", 0)
        name = match.get("name", "Bilinmeyen Maç")
        league = match.get("playing", "Diğer Ligler")
        score = match.get("score", "")
        match_time = match.get("time", "")
        image = match.get("image") or DEFAULT_LOGO
        streams = match.get("streams", [])

        if not streams:
            continue

        # Canlı / Yaklaşan formatlaması
        if status_id == 1:
            live_count += 1
            status_prefix = "🔴 CANLI"
            group_name = f"🔴 CANLI | {league}"
            # Skor varsa isme ekle
            display_title = f"🔴 {name} ({score})" if (score and score != "0 - 0") else f"🔴 {name}"
        else:
            upcoming_count += 1
            status_prefix = "🟡 YAKINDA"
            group_name = f"🟡 YAKINDA | {league}"
            display_title = f"🟡 [{match_time}] {name}" if match_time else f"🟡 {name}"

        # Yayın linklerini ekle (SD, HD vb.)
        for stream in streams:
            quality = stream.get("quality", "HD")
            language = stream.get("language", "tr")
            raw_url = stream.get("url", "")

            if not raw_url:
                continue

            stream_url = decode_stream_url(raw_url)
            channel_name = f"{display_title} [{quality}]"

            # IPTV standardı EXTINF satırı
            extinf = (
                f'#EXTINF:-1 '
                f'tvg-id="{match.get("match_id", "")}" '
                f'tvg-name="{channel_name}" '
                f'tvg-logo="{image}" '
                f'tvg-language="{language}" '
                f'group-title="{group_name}",'
                f'{channel_name}'
            )

            lines.append(extinf)
            lines.append(stream_url)
            lines.append("")

    return "\n".join(lines), live_count, upcoming_count


def main():
    # 1. Veriyi çek
    matches = fetch_json(SOURCE_URL)

    # 2. Tek M3U içeriğini hazırla
    m3u_content, live_count, upcoming_count = generate_single_m3u(matches)

    # 3. Dosyaya yaz
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"\n💾 M3U Başarıyla Oluşturuldu: {file_path}")
    print(f"📊 Özet: {live_count} Canlı Maç, {upcoming_count} Yaklaşan Maç tek dosyaya eklendi.")


if __name__ == "__main__":
    main()
