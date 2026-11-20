import re
import json
import requests
from datetime import datetime

API_URL = "https://avvasportshd1.com/api/channels"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://avvasportshd1.com/channels.html",
    "Accept": "application/json"
}

M3U_FILE = "tv247tr.m3u"
SUFFIX = "-Avva"


def strip_suffix(name):
    """Varsa sondaki -Avva ekini kaldırarak saf kanal adını döndür"""
    return re.sub(r'-Avva$', '', name.strip(), flags=re.IGNORECASE).strip()


def append_suffix(name):
    """Kanal adının sonuna -Avva ekler (zaten varsa tekrar eklemez)"""
    clean_name = name.strip()
    if not clean_name.lower().endswith(SUFFIX.lower()):
        return f"{clean_name}{SUFFIX}"
    return clean_name


def normalize(name):
    """Kanal ismini normalize et: küçük harf, sadece harf-rakam"""
    return re.sub(r'[^a-z0-9]', '', strip_suffix(name).lower())


def get_fresh_links():
    """API'den güncel m3u8 linklerini çek ve kanal adlarının sonuna -Avva ekle"""
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        channels = response.json()
    except Exception as e:
        print(f"❌ API hatası: {e}")
        return None

    link_map = {}
    for ch in channels:
        raw_name = ch.get("name", "").strip()
        url = ch.get("m3u8_url", "")
        if raw_name and url:
            avva_name = append_suffix(raw_name)
            base_name = strip_suffix(raw_name)

            # 1. -Avva eklenmiş isim (BÜYÜK HARF) ve saf isim (BÜYÜK HARF)
            link_map[avva_name.upper()] = url
            link_map[base_name.upper()] = url

            # 2. Normalize edilmiş isim (boşluksuz, özel karaktersiz)
            link_map[normalize(avva_name)] = url

            # 3. URL'den slug çıkar (örn: .../live/bein1/playlist.m3u8 -> bein1)
            slug_match = re.search(r'/([^/]+)/[^/]*\.m3u8', url)
            if slug_match:
                link_map[slug_match.group(1).lower()] = url

    return link_map


def update_playlist(link_map):
    """Mevcut tv247tr.m3u dosyasındaki kanal adlarına -Avva ekle ve linkleri güncelle"""
    try:
        with open(M3U_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ {M3U_FILE} dosyası bulunamadı!")
        print("Önce tv247tr.m3u dosyasını elle oluştur.")
        return False

    new_lines = []
    updated = 0
    current_channel_name = ""

    for i, line in enumerate(lines):
        stripped = line.strip()

        # #EXTINF satırından kanal adını al ve sonuna -Avva ekle
        if stripped.startswith("#EXTINF"):
            comma_pos = stripped.rfind(",")
            if comma_pos != -1:
                prefix_part = stripped[:comma_pos + 1]
                raw_channel_name = stripped[comma_pos + 1:].strip()
                current_channel_name = append_suffix(raw_channel_name)
                line_ending = "\n" if line.endswith("\n") else ""
                new_lines.append(f"{prefix_part} {current_channel_name}{line_ending}")
            else:
                new_lines.append(line)

        # m3u8 link satırı - bunu güncelle
        elif "avvaupdate.com" in stripped and ".m3u8" in stripped:
            norm_name = normalize(current_channel_name)
            upper_name = current_channel_name.upper()
            base_upper_name = strip_suffix(current_channel_name).upper()

            slug_match = re.search(r'/([^/]+)/[^/]*\.m3u8', stripped)
            old_slug = slug_match.group(1).lower() if slug_match else ""

            new_url = (
                link_map.get(upper_name)
                or link_map.get(base_upper_name)
                or link_map.get(norm_name)
                or link_map.get(old_slug)
            )

            if new_url:
                # 1. Karakter düzenlemelerini (URL encode) yapıyoruz
                new_url = new_url.replace("o=1&e", "o=1%26e")
                new_url = new_url.replace("&", "%26")

                # 2. Worker adresini ekle
                prefix = "https://avva.magnitude.workers.dev/?url="
                new_url = prefix + new_url

                new_lines.append(new_url + "\n")
                updated += 1
                print(f"✅ Güncellendi: {current_channel_name}")
            else:
                new_lines.append(line)
                print(f"⚠️ Eşleşme yok, eski link korundu: {current_channel_name} (aranan: '{upper_name}', '{norm_name}', '{old_slug}')")

        # Güncelleme tarih satırını güncelle
        elif stripped.startswith("# Son Güncelleme:") or stripped.startswith("# Last Updated:"):
            now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
            new_lines.append(f"# Son Güncelleme: {now}\n")

        # Diğer tüm satırlar aynen kalsın
        else:
            new_lines.append(line)

    # Dosyayı yaz
    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return updated


def main():
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    print(f"🚀 [{now}] Linkler ve kanal adları güncelleniyor...\n")

    # 1. API'den güncel linkleri al
    link_map = get_fresh_links()
    if not link_map:
        return

    print(f"📡 API'den {len(link_map)} eşleşme anahtarı alındı.\n")

    # 2. Mevcut playlist'teki kanal adlarını ve linkleri güncelle
    updated = update_playlist(link_map)

    if updated:
        print(f"\n🎉 Tamamlandı! {updated} kanal güncellendi.")
    else:
        print("\n⚠️ Hiçbir kanal güncellenemedi.")


if __name__ == "__main__":
    main()
