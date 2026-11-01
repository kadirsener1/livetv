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


def normalize(name):
    """Kanal ismini normalize et: küçük harf, sadece harf-rakam"""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def get_fresh_links():
    """API'den güncel m3u8 linklerini çek"""
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        channels = response.json()
    except Exception as e:
        print(f"❌ API hatası: {e}")
        return None

    link_map = {}
    for ch in channels:
        name = ch.get("name", "").strip()
        url = ch.get("m3u8_url", "")
        if name and url:
            # 1. Orijinal isim (BÜYÜK HARF)
            link_map[name.upper()] = url
            # 2. Normalize edilmiş isim (boşluksuz, özel karaktersiz)
            link_map[normalize(name)] = url

            # 3. URL'den slug çıkar (örn: .../live/bein1/playlist.m3u8 -> bein1)
            slug_match = re.search(r'/([^/]+)/[^/]*\.m3u8', url)
            if slug_match:
                link_map[slug_match.group(1).lower()] = url

    return link_map


def update_playlist(link_map):
    """Mevcut tv247tr.m3u dosyasındaki sadece linkleri güncelle"""
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

        # #EXTINF satırından kanal adını al
        if stripped.startswith("#EXTINF"):
            comma_pos = stripped.rfind(",")
            if comma_pos != -1:
                current_channel_name = stripped[comma_pos + 1:].strip()
            new_lines.append(line)

        # m3u8 link satırı - bunu güncelle
        elif "avvaupdate.com" in stripped and ".m3u8" in stripped:
            # Eşleşme sırası:
            # 1. Kanal ismi (BÜYÜK HARF) — EN GÜVENİLİR
            # 2. Normalize edilmiş kanal ismi
            # 3. URL'deki slug — SON ÇARE (bozuk URL'lerde yanlış olabilir)
            norm_name = normalize(current_channel_name)
            upper_name = current_channel_name.upper()

            slug_match = re.search(r'/([^/]+)/[^/]*\.m3u8', stripped)
            old_slug = slug_match.group(1).lower() if slug_match else ""

            new_url = (
                link_map.get(upper_name)
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
                print(f"✅ Güncellendi: {current_channel_name} (eşleşme: {upper_name if link_map.get(upper_name) else norm_name if link_map.get(norm_name) else old_slug})")
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
    print(f"🚀 [{now}] Linkler güncelleniyor...\n")

    # 1. API'den güncel linkleri al
    link_map = get_fresh_links()
    if not link_map:
        return

    print(f"📡 API'den {len(link_map)} kanal linki alındı.\n")

    # 2. Mevcut playlist'teki linkleri güncelle
    updated = update_playlist(link_map)

    if updated:
        print(f"\n🎉 Tamamlandı! {updated} kanal linki güncellendi.")
    else:
        print("\n⚠️ Hiçbir link güncellenemedi.")


if __name__ == "__main__":
    main()
