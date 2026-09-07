import os
import re
import time
import requests

# AtomSporTV
START_URL = "https://url24.link/AtomSporTV"
OUTPUT_FILE = "tv247tr.m3u"

GREEN = "\033[92m"
RESET = "\033[0m"

headers = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'tr-TR,tr;q=0.8',
    'Connection': 'keep-alive',
    'User-Agent': (
        'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like'
        ' Gecko) Chrome/138.0.0.0 Mobile Safari/537.36'
    ),
    'Referer': 'https://url24.link/',
}


def get_base_domain():
    """Ana domain'i bul"""
    try:
        response = requests.get(
            START_URL, headers=headers, allow_redirects=False, timeout=10
        )

        if 'location' in response.headers:
            location1 = response.headers['location']
            response2 = requests.get(
                location1, headers=headers, allow_redirects=False, timeout=10
            )

            if 'location' in response2.headers:
                base_domain = response2.headers['location'].strip().rstrip('/')
                print(f"Ana Domain: {base_domain}")
                return base_domain

        return "https://www.atomsportv480.top"

    except Exception as e:
        print(f"Domain hatası: {e}")
        return "https://www.atomsportv512.top"


def get_channel_m3u8(channel_id, base_domain):
    """PHP mantığı ile m3u8 linkini al"""
    try:
        # 1. matches?id= endpoint
        matches_url = f"{base_domain}/matches?id={channel_id}"
        response = requests.get(matches_url, headers=headers, timeout=10)
        html = response.text

        # 2. fetch URL'sini bul
        fetch_match = re.search(r'fetch\("(.*?)"', html)
        if not fetch_match:
            fetch_match = re.search(r'fetch\(\s*["\'](.*?)["\']', html)

        if fetch_match:
            fetch_url = fetch_match.group(1).strip()

            # 3. fetch URL'sine istek yap
            custom_headers = headers.copy()
            custom_headers['Origin'] = base_domain
            custom_headers['Referer'] = base_domain

            if not fetch_url.endswith(channel_id):
                fetch_url = fetch_url + channel_id

            response2 = requests.get(
                fetch_url, headers=custom_headers, timeout=10
            )
            fetch_data = response2.text

            # 4. m3u8 linkini bul
            m3u8_match = re.search(r'"deismackanal":"(.*?)"', fetch_data)
            if m3u8_match:
                m3u8_url = m3u8_match.group(1).replace('\\', '')
                return m3u8_url

            # Alternatif pattern
            m3u8_match = re.search(
                r'"(?:stream|url|source)":\s*"(.*?\.m3u8)"', fetch_data
            )
            if m3u8_match:
                return m3u8_match.group(1).replace('\\', '')

        return None

    except Exception as e:
        return None


def get_all_possible_channels():
    """Sadece TV kanallarını oluştur"""
    print("TV kanal ID'leri oluşturuluyor...")

    channels = []

    # SADECE TV KANALLARI
    tv_channels = [
        # BEIN SPORTS
        ("bein-sports-1", "BEIN SPORTS 1-ARDA"),
        ("bein-sports-2", "BEIN SPORTS 2-ARDA"),
        ("bein-sports-3", "BEIN SPORTS 3-ARDA"),
        ("bein-sports-4", "BEIN SPORTS 4-ARDA"),
        ("bein-sports-5", "BEIN SPORTS 5-ARDA"),
        ("bein-sports-max-1", "BEIN SPORTS MAX 1-ARDA"),
        ("bein-sports-max-2", "BEIN SPORTS MAX 2-ARDA"),
        # S SPORT
        ("s-sport", "S SPORT-ARDA"),
        ("s-sport-2", "S SPORT 2-ARDA"),
        # TİVİBU SPOR
        ("tivibu-spor-1", "TİVİBU SPOR 1-ARDA"),
        ("tivibu-spor-2", "TİVİBU SPOR 2-ARDA"),
        ("tivibu-spor-3", "TİVİBU SPOR 3-ARDA"),
        # TRT
        ("trt-spor", "TRT SPOR-ARDA"),
        ("trt-yildiz", "TRT YILDIZ-ARDA"),
        ("trt1", "TRT 1-ARDA"),
        # DİĞER
        ("a-spor", "A SPOR-ARDA"),
    ]

    for channel_id, name in tv_channels:
        channels.append(
            {'id': channel_id, 'name': name, 'group': 'Atom Spor'}
        )

    print(f"Toplam {len(channels)} TV kanal ID'si oluşturuldu")
    return channels


def test_channels(channels, base_domain):
    """Kanaları test et ve çalışanları bul"""
    print(f"\n{len(channels)} kanal test ediliyor...")

    working_channels = []

    for i, channel in enumerate(channels):
        channel_id = channel["id"]
        channel_name = channel["name"]

        print(f"{i+1:2d}. {channel_name}...", end=" ", flush=True)

        m3u8_url = get_channel_m3u8(channel_id, base_domain)

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

    # Eşleştirmeyi kolaylaştırmak için sözlük hazırlayalım (küçük/büyük harf toleranslı)
    new_links = {
        ch["name"].strip().lower(): ch["url"].strip()
        for ch in working_channels
        if "url" in ch
    }

    # Dosya henüz yoksa sıfırdan oluşturur
    if not os.path.exists(OUTPUT_FILE):
        print(
            f"[!] '{OUTPUT_FILE}' bulunamadığı için yeni olarak"
            " oluşturuluyor..."
        )
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for channel in working_channels:
                f.write(
                    f'#EXTINF:-1 tvg-id="{channel["id"]}"'
                    f' tvg-name="{channel["name"]}" group-title="Atom'
                    f' Spor",{channel["name"]}\n'
                )
                f.write(f'{channel["url"]}\n\n')
        print(f"{GREEN}[✓] Yeni M3U dosyası oluşturuldu.{RESET}")
        return

    # Dosya varsa mevcut yapıyı koruyarak güncelle
    with open(OUTPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    updated_lines = []
    matched_new_url = None
    updated_count = 0

    for line in lines:
        stripped = line.strip()

        # 1. #EXTINF satırından kanal adını al (virgülden sonraki kısım)
        if stripped.startswith("#EXTINF"):
            matched_new_url = None  # Önceki eşleşmeyi sıfırla
            if "," in stripped:
                channel_name = stripped.rsplit(",", 1)[1].strip().lower()
                if channel_name in new_links:
                    matched_new_url = new_links[channel_name]

            # Orijinal #EXTINF satırını aynen koru
            updated_lines.append(line)

        # 2. Diğer etiket satırları veya boş satırlar (#EXTVLCOPT, #EXTM3U vb.)
        elif stripped.startswith("#") or not stripped:
            updated_lines.append(line)

        # 3. Yayın linki satırı
        else:
            if matched_new_url:
                # İsim birebir uyduğu için yeni linki yaz
                updated_lines.append(matched_new_url + "\n")
                matched_new_url = None
                updated_count += 1
            else:
                # Eşleşme yoksa dosyadaki eski linki aynen bırak
                updated_lines.append(line)

    # Dosyaya geri kaydet
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    print(
        f"{GREEN}[✓] M3U güncellendi! Toplam {updated_count} kanalın linki"
        f" yenilendi.{RESET}"
    )


def main():
    print(f"{GREEN}AtomSporTV M3U Güncelleyici{RESET}")
    print("=" * 60)

    # 1. Ana domain'i bul
    print("\n1. Ana domain bulunuyor...")
    base_domain = get_base_domain()

    # 2. TV kanallarını oluştur
    print("\n2. TV kanal ID'leri oluşturuluyor...")
    all_channels = get_all_possible_channels()

    # 3. Kanalları test et
    print("\n3. Kanallar test ediliyor...")
    working_channels = test_channels(all_channels, base_domain)

    if not working_channels:
        print("\n❌ Hiç çalışan kanal bulunamadı!")
        return

    # 4. Sadece eşleşen isimlerin linklerini güncelle
    print("\n4. M3U dosyası güncelleniyor...")
    update_m3u(working_channels, base_domain)

    # 5. Sonuçları göster
    print("\n" + "=" * 60)
    print("ÇALIŞAN KANALLAR:")

    for channel in working_channels:
        print(f"  ✓ {channel['name']}")

    # 6. GitHub komutları
    print("\n" + "=" * 60)
    print("GitHub komutları:")
    print(f"  git add {OUTPUT_FILE}")
    print('  git commit -m "AtomSporTV M3U güncellemesi"')
    print("  git push")


if __name__ == "__main__":
    main()
