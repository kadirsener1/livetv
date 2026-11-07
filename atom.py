import os
import time
from playwright.sync_api import sync_playwright

START_URL = "https://url24.link/AtomSporTV"
OUTPUT_FILE = "tv247tr.m3u"

GREEN = "\033[92m"
RESET = "\033[0m"

def get_channel_m3u8_with_browser(channel_id):
    """Playwright kullanarak tarayıcı tabanlı m3u8 / stream linkini yakala"""
    target_url = f"https://www.atomsportv520.top/matches?id={channel_id}"
    captured_url = None

    with sync_playwright() as p:
        # Tarayıcıyı arka planda (headless) başlat
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            referer="https://url24.link/"
        )
        page = context.new_page()

        # Ağ isteklerini dinle ve .m3u8 uzantılı adresleri yakala
        def handle_request(request):
            nonlocal captured_url
            if ".m3u8" in request.url or "manifest" in request.url:
                if not captured_url:
                    captured_url = request.url

        page.on("request", handle_request)

        try:
            print(f"Yükleniyor: {target_url}")
            page.goto(target_url, timeout=15000)
            
            # Sayfanın ve oynatıcının yüklenmesi için kısa bir bekleme
            page.wait_for_timeout(4000)
            
            # Eğer ağ isteğinde yakalanamadıysa sayfa kaynağındaki scriptlerde ara
            if not captured_url:
                content = page.content()
                import re
                match = re.search(r'(https?://[^\s\'"]+?\.m3u8[^\s\'"]*)', content)
                if match:
                    captured_url = match.group(1).replace('\\', '')

        except Exception as e:
            print(f"Hata oluştu ({channel_id}): {e}")
        finally:
            browser.close()

        return captured_url

def get_all_channels():
    return [
        ("bein-sports-1", "BEIN SPORTS 1-A"),
        ("bein-sports-2", "BEIN SPORTS 2-A"),
        ("bein-sports-3", "BEIN SPORTS 3-A"),
        ("bein-sports-4", "BEIN SPORTS 4-A"),
        ("bein-sports-max-1", "BEIN SPORTS MAX 1-A"),
        ("bein-sports-max-2", "BEIN SPORTS MAX 2-A"),
        ("s-sport", "S SPORT-A"),
        ("s-sport-2", "S SPORT 2-A"),
        ("tivibu-spor-1", "TİVİBU SPOR 1-A"),
        ("tivibu-spor-2", "TİVİBU SPOR 2-A"),
        ("tivibu-spor-3", "TİVİBU SPOR 3-A"),
        ("trt-spor", "TRT SPOR-A"),
        ("trt-yildiz", "TRT YILDIZ-A"),
        ("trt1", "TRT 1-A"),
        ("a-spor", "A SPOR-A"),
    ]

def main():
    print(f"{GREEN}AtomSporTV Playwright M3U Güncelleyici{RESET}")
    print("=" * 60)

    channels = get_all_channels()
    working_channels = []

    for cid, name in channels:
        print(f"Taranıyor: {name}...", end=" ", flush=True)
        url = get_channel_m3u8_with_browser(cid)
        if url:
            print(f"{GREEN}✓ Bulundu{RESET}")
            working_channels.append({"id": cid, "name": name, "url": url})
        else:
            print("✗ Bulunamadı")

    if not working_channels:
        print("\n❌ Hiçbir kanal linki yakalanamadı.")
        return

    # M3U Dosyasına Yazma
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ch in working_channels:
            f.write(f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-name="{ch["name"]}" group-title="Atom Spor",{ch["name"]}\n')
            f.write(f'{ch["url"]}\n\n')

    print(f"\n{GREEN}[✓] Başarıyla {len(working_channels)} kanal '{OUTPUT_FILE}' dosyasına kaydedildi!{RESET}")

if __name__ == "__main__":
    main()
