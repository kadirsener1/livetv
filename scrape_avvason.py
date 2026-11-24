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


def get_fresh_links():
    """API'den güncel m3u8 linklerini ve kanal adlarını çek"""
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        channels = response.json()
    except Exception as e:
        print(f"❌ API hatası: {e}")
        return None, set()

    link_map = {}
    api_names = set()

    for ch in channels:
        raw_name = ch.get("name", "").strip()
        url = ch.get("m3u8_url", "")
        if raw_name and url:
            clean_name = strip_suffix(raw_name)
            key_name = clean_name.upper()
            api_names.add(key_name)
            link_map[key_name] = url

    return link_map, api_names


def update_playlist(link_map, api_names):
    """Yalnızca adı API'deki kanal adıyla aynı olan kanalların sonuna -Avva ekle ve linkini güncelle"""
    try:
        with open(M3U_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ {M3U_FILE} dosyası bulunamadı!")
        print("Önce tv247tr.m3u dosyasını elle oluştur.")
        return 0

    updated = 0
    matched_indices = {}  # extinf_index -> yeni_kanal_adi
    current_extinf_idx = None
    current_channel_name = ""

    temp_lines = list(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("#EXTINF"):
            comma_pos = stripped.rfind(",")
            if comma_pos != -1:
                current_channel_name = stripped[comma_pos + 1:].strip()
                current_extinf_idx = i

        elif "avvaupdate.com" in stripped and ".m3u8" in stripped:
            clean_name = strip_suffix(current_channel_name)
            key_name = clean_name.upper()

            is_same_name = key_name in api_names
            new_url = link_map.get(key_name)

            if is_same_name and new_url:
                new_url = new_url.replace("o=1&e", "o=1%26e")
                new_url = new_url.replace("&", "%26")
                prefix = "https://avva.magnitude2.workers.dev/?url="
                temp_lines[i] = prefix + new_url + "\n"

                if current_extinf_idx is not None:
                    matched_indices[current_extinf_idx] = append_suffix(current_channel_name)

                updated += 1
                print(f"✅ Eşleşti ve güncellendi: {append_suffix(current_channel_name)}")
            else:
                print(f"⏭️ Adı aynı değil, dokunulmadı: {current_channel_name}")

    final_lines = []
    for i, line in enumerate(temp_lines):
        stripped = line.strip()
        if i in matched_indices:
            comma_pos = line.rfind(",")
            if comma_pos != -1:
                prefix_part = line[:comma_pos + 1]
                line_ending = "\n" if line.endswith("\n") else ""
                final_lines.append(f"{prefix_part} {matched_indices[i]}{line_ending}")
            else:
                final_lines.append(line)
        elif stripped.startswith("# Son Güncelleme:") or stripped.startswith("# Last Updated:"):
            now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
            final_lines.append(f"# Son Güncelleme: {now}\n")
        else:
            final_lines.append(line)

    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.writelines(final_lines)

    return updated


def main():
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    print(f"🚀 [{now}] Adı aynı olan kanallar kontrol ediliyor...\n")

    link_map, api_names = get_fresh_links()
    if not link_map:
        return

    print(f"📡 API'den {len(link_map)} kanal adı alındı.\n")

    updated = update_playlist(link_map, api_names)

    if updated:
        print(f"\n🎉 Tamamlandı! {updated} kanalın adı ve linki güncellendi.")
    else:
        print("\n⚠️ Adı aynı olan kanal bulunamadı.")


if __name__ == "__main__":
    main()
