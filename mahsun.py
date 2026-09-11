import concurrent.futures
import os
import re
import warnings
import requests
import urllib3

# Sertifika uyarılarını kapatmak için
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore')

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
}

# Hedef dosya adı
OUTPUT_FILENAME = "tv247tr.m3u"


def get_andro_content():
    """Çalışan yayın linklerini yakalar ve {Kanal Adı: URL} sözlüğü döner."""
    print("--- Andro Panel Taraması Başlatıldı ---")
    channel_streams = {}
    base_pattern = "https://mahsunsports{}.xyz"
    headers = HEADERS.copy()

    channels = [
        ("androstreamlivebiraz1", 'BEIN SPORTS 1-Mahsun'),
        ("androstreamlivebs1", 'BEIN SPORTS 1-Mahsun2'),
        ("androstreamlivebs2", 'BEIN SPORTS 2-Mahsun'),
        ("androstreamlivebs3", 'BEIN SPORTS 3-Mahsun'),
        ("androstreamlivebs4", 'BEIN SPORTS 4-Mahsun'),
        ("androstreamlivebs5", 'BEIN SPORTS 5-Mahsun'),
        ("androstreamlivebsm1", 'BEIN SPORTS MAX 1-Mahsun'),
        ("androstreamlivebsm2", 'BEIN SPORTS MAX 2-Mahsun'),
        ("androstreamlivess1", 'S SPORT 1-Mahsun'),
        ("androstreamlivess2", 'S SPORT 2-Mahsun'),
        ("androstreamlivets", 'TİVİBU SPOR-Mahsun'),
        ("androstreamlivets1", 'TİVİBU SPOR 1-Mahsun'),
        ("androstreamlivets2", 'TİVİBU SPOR 2-Mahsun'),
        ("androstreamlivets3", 'TİVİBU SPOR 3-Mahsun'),
        ("androstreamlivets4", 'TİVİBU SPOR 4-Mahsun'),
        ("androstreamlivesm1", 'SMART SPOR 1-Mahsun'),
        ("androstreamlivesm2", 'SMART SPOR 2-Mahsun'),
        ("androstreamlivees1", 'EURO SPORT 1-Mahsun'),
        ("androstreamlivees2", 'EURO SPORT 2-Mahsun'),
        ("androstreamlivetb", 'TABİİ SPOR-Mahsun'),
        ("androstreamlivetb1", 'TABİİ SPOR 1-Mahsun'),
        ("androstreamlivetb2", 'TABİİ SPOR 2-Mahsun'),
        ("androstreamlivetb3", 'TABİİ SPOR 3-Mahsun'),
        ("androstreamlivetb4", 'TABİİ SPOR 4-Mahsun'),
        ("androstreamlivetb5", 'TABİİ SPOR 5-Mahsun'),
        ("androstreamlivetb6", 'TABİİ SPOR 6-Mahsun'),
        ("androstreamlivetb7", 'TABİİ SPOR 7-Mahsun'),
        ("androstreamlivetb8", 'TABİİ SPOR 8-Mahsun'),
        ("androstreamliveexn", 'EXXEN-Mahsun'),
        ("androstreamliveexn1", 'EXXEN 1-Mahsun'),
        ("androstreamliveexn2", 'EXXEN 2-Mahsun'),
        ("androstreamliveexn3", 'EXXEN 3-Mahsun'),
        ("androstreamliveexn4", 'EXXEN 4-Mahsun'),
        ("androstreamliveexn5", 'EXXEN 5-Mahsun'),
        ("androstreamliveexn6", 'EXXEN 6-Mahsun'),
        ("androstreamliveexn7", 'EXXEN 7-Mahsun'),
        ("androstreamliveexn8", 'EXXEN 8-Mahsun'),
    ]

    def check_domain(index):
        url = base_pattern.format(index)
        try:
            response = requests.get(
                url, headers=headers, timeout=5, verify=False
            )
            if response.status_code == 200:
                return url
        except:
            return None
        return None

    print("Aktif domain aranıyor (10-99)...")
    active_site = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_domain, i) for i in range(10, 100)]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                active_site = result
                break

    if not active_site:
        print("Aktif site bulunamadı.")
        return channel_streams

    print(f"Bulunan Domain: {active_site}")
    event_url = f"{active_site}/event.html?id=androstreamlivebs1"

    try:
        r2 = requests.get(event_url, headers=headers, verify=False, timeout=10)
        h2_text = r2.text
    except Exception as e:
        print(f"Event sayfası hatası: {e}")
        return channel_streams

    baseurl_match = re.search(
        r'baseurls\s*=\s*\[(.*?)\]', h2_text, re.DOTALL | re.IGNORECASE
    )
    if not baseurl_match:
        print("Sunucu adresleri bulunamadı.")
        return channel_streams

    urls_text = (
        baseurl_match.group(1)
        .replace('"', '')
        .replace("'", "")
        .replace("\n", "")
        .replace("\r", "")
    )
    servers = [
        url.strip()
        for url in urls_text.split(',')
        if url.strip().startswith("http")
    ]
    servers = list(set(servers))

    active_servers = []
    test_id = "androstreamlivebs1"
    for server in servers:
        server = server.rstrip('/')
        test_url = (
            f"{server}/{test_id}.m3u8"
            if "checklist" in server
            else f"{server}/checklist/{test_id}.m3u8"
        )
        test_url = test_url.replace("checklist//", "checklist/")
        try:
            temp_response = requests.get(
                test_url,
                headers={'Referer': active_site + "/"},
                verify=False,
                timeout=5,
            )
            if temp_response.status_code == 200:
                active_servers.append(server)
        except:
            continue

    # Çalışan sunuculardan kanal linklerini sözlüğe ekle
    for server in active_servers:
        server = server.rstrip('/')
        for cid, cname in channels:
            final_url = (
                f"{server}/{cid}.m3u8"
                if "checklist" in server
                else f"{server}/checklist/{cid}.m3u8"
            )
            final_url = final_url.replace("checklist//", "checklist/")

            # İlk yakalanan aktif linki sakla
            if cname not in channel_streams:
                channel_streams[cname] = final_url

    return channel_streams


def update_m3u_by_name(file_path, channel_streams):
    """Mevcut M3U dosyasını bozmadan SADECE kanal ismine bakarak linkleri günceller/yamalar."""
    if not channel_streams:
        print("[-] Güncellenecek aktif yayın linki bulunamadı.")
        return

    # Küçük/büyük harf ve boşluk farklarını tolere etmek için normalize ediyoruz
    normalized_new = {
        k.strip().lower(): v.strip() for k, v in channel_streams.items()
    }

    # Dosya henüz yoksa oluşturur
    if not os.path.exists(file_path):
        print(f"[!] '{file_path}' bulunamadı, yeni olarak oluşturuluyor...")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for cname, stream_url in channel_streams.items():
                f.write(f'#EXTINF:-1 group-title="Spor",{cname}\n')
                f.write(f'{stream_url}\n\n')
        print(f"[✓] '{file_path}' oluşturuldu.")
        return

    # Dosya varsa mevcut satırları oku ve linkleri yama
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    updated_lines = []
    pending_new_url = None
    updated_count = 0

    for line in lines:
        stripped = line.strip()

        # 1. #EXTINF satırından kanal adını yakala
        if stripped.startswith("#EXTINF"):
            pending_new_url = None
            if "," in stripped:
                channel_name = stripped.rsplit(",", 1)[1].strip().lower()
                if channel_name in normalized_new:
                    pending_new_url = normalized_new[channel_name]

            # Orijinal #EXTINF satırını (tvg-logo, id, grup vs.) HİÇ DEĞİŞTİRMEDEN ekle
            updated_lines.append(line)

        # 2. Diğer etiketler ve boş satırlar (#EXTVLCOPT vb.)
        elif stripped.startswith("#") or not stripped:
            updated_lines.append(line)

        # 3. Yayın Linki satırı
        else:
            if pending_new_url:
                # Eşleşen kanalın altına sadece yeni linki koy
                updated_lines.append(pending_new_url + "\n")
                pending_new_url = None
                updated_count += 1
            else:
                # Eşleşmeyen kanalların eski linkine dokunma
                updated_lines.append(line)

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    print(
        f"\n[✓] Başarılı! '{file_path}' dosyasındaki {updated_count} adet kanalın"
        " linki güncellendi."
    )


def main():
    print("İşlem Başladı...")
    channel_streams = get_andro_content()

    # Sadece tv247tr.m3u dosyasına yama uygula
    update_m3u_by_name(OUTPUT_FILENAME, channel_streams)


if __name__ == "__main__":
    main()
