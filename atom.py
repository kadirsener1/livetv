import os
import re
import time
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "tv247tr.m3u"

GREEN = "\033[92m"
RESET = "\033[0m"

def get_channel_m3u8_with_browser(channel_id):
    """Playwright kullanarak tarayıcı tabanlı m3u8 / stream linkini yakala"""
    base_domain = "https://www.atomsportv520.top"
    target_url = f"{base_domain}/matches?id={channel_id}"
    captured_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        context.set_extra_http_headers({
            "Referer": "https://url24.link/",
            "Origin": base_domain
        })
        
        page = context.new_page()

        def handle_request(request):
            nonlocal captured_url
            if ".m3u8" in request.url or "manifest" in request.url:
                if not captured_url:
                    captured_url = request.url

        page.on("request", handle_request)

        try:
            page.goto(target_url, timeout=15000)
            page.wait_for_timeout(4000)
            
            if not captured_url:
                content = page.content()
                match = re.search(r'(https?://[^\s\'"]+?\.m3u8[^\s\'"]*)', content)
                if match:
                    captured_url = match.group(1).replace('\\', '')

        except Exception as e:
            pass
        finally:
            browser.close()

        return captured_url

def get_all_channels():
    """Sadece TV kanallarının ID ve isim listesi"""
    return [
        ("bein-sports-1", "BEIN SPORTS 1-A"),
        ("bein-sports-2", "BEIN SPORTS 2-A"),
        ("bein-sports-3", "BEIN SPORTS 3-A"),
        ("bein-sports-4", "BEIN SPORTS 4-A"),
        ("bein-sports-5", "BEIN SPORTS 5-A"),
        ("bein-sports-max-1", "BEIN SPORTS MAX 1-A"),
        ("bein-sports-max-2", "BEIN SPORTS MAX 2-A"),
        ("s-sport", "S SPORT-A"),
        ("s-sport-2", "S SPORT 2-A"),
        ("a-spor", "A SPOR-A"),
    ]

def update_m3u(working_channels):
    """Mevcut M3U dosyasını bozmadan SADECE eşleşen kanal adlarını ve linklerini günceller/ekler"""
    print(f"\nM3U dosyası taranıyor ve güncelleniyor: {OUTPUT_FILE}...")

    # Yeni bulunan linkleri ve grup bilgilerini hızlı erişim için sözlüğe atalım (küçük harf duyarlılığını kaldırmak için)
    new_channels_dict = {
        ch["name"].strip().lower(): {
            "id": ch["id"],
            "name": ch["name"],
            "url": ch["url"].strip(),
            "group": "Spor"
        }
        for ch in working_channels if "url" in ch
    }

    # Eğer dosya hiç yoksa sıfırdan oluştur
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in working_channels:
                f.write(f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-name="{ch["name"]}" group-title="Spor",{ch["name"]}\n')
                f.write(f'{ch["url"]}\n\n')
        print(f"{GREEN}[✓] Yeni M3U dosyası oluşturuldu.{RESET}")
        return

    # Dosya varsa satır satır oku ve güncelle
    with open(OUTPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    updated_lines = []
    matched_new_data = None
    updated_count = 0
    processed_channels = set()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # #EXTINF satırını yakala
        if stripped.startswith("#EXTINF"):
            matched_new_data = None
            if "," in stripped:
                channel_name = stripped.rsplit(",", 1)[1].strip().lower()
                if channel_name in new_channels_dict:
                    matched_new_data = new_channels_dict[channel_name]
                    processed_channels.add(channel_name)
                    # Grup adını da "Spor" olacak şekilde güncellemek istersek EXTINF satırını yenileyebiliriz:
                    ch_info = matched_new_data
                    updated_line = f'#EXTINF:-1 tvg-id="{ch_info["id"]}" tvg-name="{ch_info["name"]}" group-title="Spor",{ch_info["name"]}\n'
                    updated_lines.append(updated_line)
                    i += 1
                    # Bir sonraki satır link satırısıdır, onu yeni link ile değiştir
                    if i < len(lines):
                        updated_lines.append(matched_new_data["url"] + "\n")
                        updated_count += 1
                    i += 1
                    continue

            # Eşleşmeyen diğer kanalların satırlarını aynen koru
            updated_lines.append(line)
            i += 1
        else:
            # Diğer satırlar (boşluklar, #EXTM3U veya diğer dış gruplar) aynen kalır
            updated_lines.append(line)
            i += 1

    # Kodda olup da mevcut M3U dosyasında hiç yer almayan yeni kanalları dosyanın sonuna ekle
    added_new_count = 0
    for ch_name_lower, ch_data in new_channels_dict.items():
        if ch_name_lower not in processed_channels:
            updated_lines.append(f'\n#EXTINF:-1 tvg-id="{ch_data["id"]}" tvg-name="{ch_data["name"]}" group-title="Spor",{ch_data["name"]}\n')
            updated_lines.append(ch_data["url"] + "\n")
            added_new_count += 1

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    print(f"{GREEN}[✓] M3U güncellendi! {updated_count} kanalın linki yenilendi, {added_new_count} yeni kanal eklendi. Diğer kanallarınız korundu.{RESET}")

def main():
    print(f"{GREEN}AtomSporTV Playwright M3U Güncelleyici{RESET}")
    print("=" * 60)

    channels = get_all_channels()
    working_channels = []

    print(f"\n{len(channels)} kanal taranıyor...")
    for i, (cid, name) in enumerate(channels):
        print(f"{i+1:2d}. {name}...", end=" ", flush=True)
        url = get_channel_m3u8_with_browser(cid)
        if url:
            print(f"{GREEN}✓ Bulundu{RESET}")
            working_channels.append({"id": cid, "name": name, "url": url})
        else:
            print("✗ Bulunamadı")
        time.sleep(0.3)

    if not working_channels:
        print("\n❌ Hiçbir kanal linki yakalanamadı. M3U dosyasına dokunulmadı.")
        return

    update_m3u(working_channels)

if __name__ == "__main__":
    main()
