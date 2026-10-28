import os
import re
import time
import requests

# ArdaSporTV
START_URL = "https://ardaspor38.top"
OUTPUT_FILE = "ardaspor.m3u"

GREEN = "\033[92m"
RESET = "\033[0m"

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'tr-TR,tr;q=0.8',
    'Connection': 'keep-alive',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://ardaspor38.top/',
}


def get_base_domain():
    """Ana domain'i kontrol et ve döndür"""
    try:
        response = requests.get(START_URL, headers=headers, allow_redirects=True, timeout=10)
        base_domain = response.url.strip().rstrip('/')
        print(f"Ana Domain: {base_domain}")
        return base_domain
    except Exception as e:
        print(f"Domain hatası: {e}")
        return START_URL


def get_channel_m3u8(channel_path, base_domain):
    """canli-mac endpoint'inden ve player scriptlerinden m3u8 linkini al"""
    try:
        channel_url = f"{base_domain}/{channel_path}"
        custom_headers = headers.copy()
        custom_headers['Referer'] = base_domain
        
        response = requests.get(channel_url, headers=custom_headers, timeout=10)
        html = response.text

        # 1. Doğrudan sayfa kaynağında .m3u8 linki arama
        m3u8_match = re.search(r'(https?://[^\s<>"]+?\.m3u8[^\s<>"]*)', html)
        if m3u8_match:
            return m3u8_match.group(1).replace('\\', '')

        # 2. Sayfa içindeki script dosyalarını (.js) bulup aralarında m3u8 veya fetch endpoint'i arayalım
        script_srcs = re.findall(r'<script[^>]+src=["\'](.*?)["\']', html)
        for src in script_srcs:
            if not src.startswith('http'):
                script_url = base_domain + ("/" if not src.startswith("/") else "") + src
            else:
                script_url = src
            
            try:
                js_res = requests.get(script_url, headers=custom_headers, timeout=5)
                js_match = re.search(r'(https?://[^\s<>"]+?\.m3u8[^\s<>"]*)', js_res.text)
                if js_match:
                    return js_match.group(1).replace('\\', '')
            except:
                continue

        # 3. Sayfadaki yaygın player değişken kalıpları (source, file, url vb.)
        patterns = [
            r'"deismackanal"\s*:\s*"(.*?)"',
            r'"(?:stream|url|source|file|hls)"\s*:\s*"(.*?\.m3u8.*?)"',
            r'source\s*:\s*["\'](.*?)["\']',
            r'file\s*:\s*["\'](.*?)["\']',
            r'src\s*:\s*["\'](.*?.m3u8.*?)["\']'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url_val = match.group(1).replace('\\', '')
                if url_val.startswith('http'):
                    return url_val

        # 4. Sayfa içerisindeki fetch veya ajax isteklerini yakala
        fetch_matches = re.findall(r'fetch\(\s*["\'](.*?)["\']', html)
        for fetch_url in fetch_matches:
            if not fetch_url.startswith('http'):
                fetch_url = base_domain + ("/" if not fetch_url.startswith("/") else "") + fetch_url
            
            try:
                res2 = requests.get(fetch_url, headers=custom_headers, timeout=5)
                m3u8_match2 = re.search(r'(https?://[^\s<>"]+?\.m3u8[^\s<>"]*)', res2.text)
                if m3u8_match2:
                    return m3u8_match2.group(1).replace('\\', '')
            except:
                continue

        return None

    except Exception as e:
        return None


def get_all_possible_channels():
    """TV kanallarını ve canli-mac yollarını oluştur"""
    print("TV kanal yolları oluşturuluyor...")

    channels = []

    tv_channels = [
        # BEIN SPORTS
        ("canli-mac/bein-sports-1", "BEIN SPORTS 1"),
        ("canli-mac/bein-sports-2", "BEIN SPORTS 2"),
        ("canli-mac/bein-sports-3", "BEIN SPORTS 3"),
        ("canli-mac/bein-sports-4", "BEIN SPORTS 4"),
        ("canli-mac/bein-sports-max-1", "BEIN SPORTS MAX 1"),
        ("canli-mac/bein-sports-max-2", "BEIN SPORTS MAX 2"),
        # S SPORT
        ("canli-mac/s-sport-1", "S SPORT 1"),
        ("canli-mac/s-sport-2", "S SPORT 2"),
        # TİVİBU SPOR
        ("canli-mac/tivibu-spor-1", "TİVİBU SPOR 1"),
        ("canli-mac/tivibu-spor-2", "TİVİBU SPOR 2"),
        ("canli-mac/tivibu-spor-3", "TİVİBU SPOR 3"),
        # TRT
        ("canli-mac/trt-spor", "TRT SPOR"),
        ("canli-mac/trt-yildiz", "TRT YILDIZ"),
        ("canli-mac/trt-1", "TRT 1"),
        # DİĞER
        ("canli-mac/a-spor", "A SPOR"),
    ]

    for channel_path, name in tv_channels:
        channel_id = channel_path.split("/")[-1]
        channels.append(
            {'id': channel_id, 'path': channel_path, 'name': name, 'group': 'Arda Spor'}
        )

    print(f"Toplam {len(channels)} TV kanalı hazırlandı.")
    return channels


def test_channels(channels, base_domain):
    """Kanalları test et ve çalışanları bul"""
    print(f"\n{len(channels)} kanal test ediliyor...")

    working_channels = []

    for i, channel in enumerate(channels):
        channel_path = channel["path"]
        channel_name = channel["name"]

        print(f"{i+1:2d}. {channel_name}...", end=" ", flush=True)

        m3u8_url = get_channel_m3u8(channel_path, base_domain)

        if m3u8_url:
            print(f"{GREEN}✓{RESET}")
            channel['url'] = m3u8_url
            working_channels.append(channel)
        else:
            print("✗")

    return working_channels


def update_m3u(working_channels, base_domain):
    """Mevcut M3U dosyasını bozmadan SADECE kanal adına göre linkleri günceller"""
    print(f"\nM3U dosyası taranıyor ve güncelleniyor: {OUTPUT_FILE}...")

    new_links = {
        ch["name"].strip().lower(): ch["url"].strip()
        for ch in working_channels
        if "url" in ch
    }

    if not os.path.exists(OUTPUT_FILE):
        print(f"[!] '{OUTPUT_FILE}' bulunamadığı için yeni olarak oluşturuluyor...")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for channel in working_channels:
                f.write(
                    f'#EXTINF:-1 tvg-id="{channel["id"]}"'
                    f' tvg-name="{channel["name"]}" group-title="Arda Spor",{channel["name"]}\n'
                )
                f.write(f'{channel["url"]}\n\n')
        print(f"{GREEN}[✓] Yeni M3U dosyası oluşturuldu.{RESET}")
        return

    with open(OUTPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    updated_lines = []
    matched_new_url = None
    updated_count = 0

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#EXTINF"):
            matched_new_url = None
            if "," in stripped:
                channel_name = stripped.rsplit(",", 1)[1].strip().lower()
                if channel_name in new_links:
                    matched_new_url = new_links[channel_name]

            updated_lines.append(line)

        elif stripped.startswith("#") or not stripped:
            updated_lines.append(line)

        else:
            if matched_new_url:
                updated_lines.append(matched_new_url + "\n")
                matched_new_url = None
                updated_count += 1
            else:
                updated_lines.append(line)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    print(
        f"{GREEN}[✓] M3U güncellendi! Toplam {updated_count} kanalın linki yenilendi.{RESET}"
    )


def main():
    print(f"{GREEN}ArdaSporTV M3U Güncelleyici{RESET}")
    print("=" * 60)

    print("\n1. Ana domain bulunuyor...")
    base_domain = get_base_domain()

    print("\n2. TV kanal yolları oluşturuluyor...")
    all_channels = get_all_possible_channels()

    print("\n3. Kanallar test ediliyor...")
    working_channels = test_channels(all_channels, base_domain)

    if not working_channels:
        print("\n❌ Hiç çalışan kanal bulunamadı!")
        return

    print("\n4. M3U dosyası güncelleniyor...")
    update_m3u(working_channels, base_domain)

    print("\n" + "=" * 60)
    print("ÇALIŞAN KANALLAR:")

    for channel in working_channels:
        print(f"  ✓ {channel['name']}")

    print("\n" + "=" * 60)
    print("GitHub komutları:")
    print(f"  git add {OUTPUT_FILE}")
    print('  git commit -m "ArdaSporTV M3U güncellemesi"')
    print("  git push")


if __name__ == "__main__":
    main()
