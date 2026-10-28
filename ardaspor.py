import os
import time
from playwright.sync_api import sync_playwright

# ArdaSporTV
START_URL = "https://ardaspor38.top"
OUTPUT_FILE = "ardaspor.m3u"

GREEN = "\033[92m"
RESET = "\033[0m"


def get_channel_m3u8(channel_path):
    """Headless tarayıcı kullanarak dinamik m3u8 linkini yakala"""
    m3u8_url = None
    
    with sync_playwright() as p:
        # Tarayıcıyı başlat
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            referer=START_URL
        )
        page = context.new_page()

        # Sayfa yüklenirken geçen tüm istekleri dinle ve .m3u8 olanı yakala
        def intercept_request(request):
            nonlocal m3u8_url
            if ".m3u8" in request.url:
                m3u8_url = request.url

        page.on("request", intercept_request)

        try:
            target_url = f"{START_URL}/{channel_path}"
            page.goto(target_url, timeout=20000)
            
            # Oynatıcının yüklenmesi için 4-5 saniye bekle
            page.wait_for_timeout(5000)

            # Eğer ağ isteğinde yakalanamadıysa sayfa kaynağında regex ile ara
            if not m3u8_url:
                content = page.content()
                import re
                match = re.search(r'(https?://[^\s<>"]+?\.m3u8[^\s<>"]*)', content)
                if match:
                    m3u8_url = match.group(1).replace('\\', '')

        except Exception as e:
            print(f"Tarayıcı hatası ({channel_path}): {e}")
        finally:
            browser.close()

    return m3u8_url


def get_all_possible_channels():
    """TV kanallarını ve canli-mac yollarını oluştur"""
    print("TV kanal yolları oluşturuluyor...")

    channels = []
    tv_channels = [
        ("canli-mac/bein-sports-1", "BEIN SPORTS 1"),
        ("canli-mac/bein-sports-2", "BEIN SPORTS 2"),
        ("canli-mac/bein-sports-3", "BEIN SPORTS 3"),
        ("canli-mac/bein-sports-4", "BEIN SPORTS 4"),
        ("canli-mac/bein-sports-max-1", "BEIN SPORTS MAX 1"),
        ("canli-mac/bein-sports-max-2", "BEIN SPORTS MAX 2"),
        ("canli-mac/s-sport-1", "S SPORT 1"),
        ("canli-mac/s-sport-2", "S SPORT 2"),
        ("canli-mac/tivibu-spor-1", "TİVİBU SPOR 1"),
        ("canli-mac/tivibu-spor-2", "TİVİBU SPOR 2"),
        ("canli-mac/tivibu-spor-3", "TİVİBU SPOR 3"),
        ("canli-mac/trt-spor", "TRT SPOR"),
        ("canli-mac/trt-yildiz", "TRT YILDIZ"),
        ("canli-mac/trt-1", "TRT 1"),
        ("canli-mac/a-spor", "A SPOR"),
    ]

    for channel_path, name in tv_channels:
        channel_id = channel_path.split("/")[-1]
        channels.append(
            {'id': channel_id, 'path': channel_path, 'name': name, 'group': 'Arda Spor'}
        )

    print(f"Toplam {len(channels)} TV kanalı hazırlandı.")
    return channels


def test_channels(channels):
    """Kanalları tarayıcı ile test et ve çalışanları bul"""
    print(f"\n{len(channels)} kanal taranıyor...")

    working_channels = []

    for i, channel in enumerate(channels):
        channel_path = channel["path"]
        channel_name = channel["name"]

        print(f"{i+1:2d}. {channel_name}...", end=" ", flush=True)

        m3u8_url = get_channel_m3u8(channel_path)

        if m3u8_url:
            print(f"{GREEN}✓{RESET}")
            channel['url'] = m3u8_url
            working_channels.append(channel)
        else:
            print("✗")

    return working_channels


def update_m3u(working_channels):
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
    print(f"{GREEN}ArdaSporTV M3U Güncelleyici (Playwright Engine){RESET}")
    print("=" * 60)

    print("\n1. TV kanal yolları oluşturuluyor...")
    all_channels = get_all_possible_channels()

    print("\n2. Kanallar tarayıcı ile test ediliyor...")
    working_channels = test_channels(all_channels)

    if not working_channels:
        print("\n❌ Hiç çalışan kanal bulunamadı!")
        return

    print("\n3. M3U dosyası güncelleniyor...")
    update_m3u(working_channels)

    print("\n" + "=" * 60)
    print("ÇALIŞAN KANALLAR:")
    for channel in working_channels:
        print(f"  ✓ {channel['name']}")


if __name__ == "__main__":
    main()
