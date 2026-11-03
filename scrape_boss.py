import asyncio
import requests
from playwright.async_api import async_playwright

CHANNEL_PATH = "/?channel=channel%3Atflix-MDJjNzUwY2JiYTUzYTZlZg"
CHANNEL_NAME = "Boss Sports - Tflix"
OUTPUT_FILE = "playlist.m3u"

def find_active_domain_fast():
    """
    1000 ile 2000 arasındaki geniş aralığı HTTP istekleriyle 
    saniyeler içinde tarar ve çalışan aktif domain'i bulur.
    """
    base_prefix = "https://bosssports"
    base_suffix = ".com"
    
    print("Geniş domain aralığı taranıyor (1000 - 2000)...")
    
    # Performans için son bilinen çalışan numaradan başlayıp dışa doğru genişleyen 
    # veya 1000-2000 arasında hızlı bir tarama sırası oluşturabiliriz.
    # Örnek olarak 1050 ile 1200 arasındaki yaygın aralığı veya tam listeyi tarayalım:
    for num in range(1000, 2000):
        url = f"{base_prefix}{num}{base_suffix}"
        try:
            # Sadece başlıkları çekerek (HEAD isteği) hızlıca test et
            response = requests.head(url, timeout=1.5, allow_redirects=True)
            if response.status_code < 400:
                full_url = f"{url}{CHANNEL_PATH}"
                print(f" Aktif domain bulundu: {full_url}")
                return full_url
        except requests.RequestException:
            continue
            
    print("Aralıkta aktif domain bulunamadı!")
    return None

async def get_stream_url(page, full_url):
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and not stream_url:
            stream_url = request.url

    page.on("request", handle_request)

    try:
        print(f"Yayın yükleniyor: {full_url}")
        await page.goto(full_url, timeout=45000)
        await page.wait_for_timeout(6000)
    except Exception as e:
        print(f"Yükleme hatası: {e}")

    page.remove_listener("request", handle_request)
    return stream_url

async def main():
    # 1. Adım: Hızlı HTTP taramasıyla aktif domain'i bul
    active_url = find_active_domain_fast()
    
    if not active_url:
        return

    # 2. Adım: Bulunan aktif adres üzerinden Playwright ile m3u8 linkini yakala
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        stream_url = await get_stream_url(page, active_url)
        await browser.close()

        if stream_url:
            print(f" Başarılı! Bulunan m3u8 linki: {stream_url}")
            m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-name="{CHANNEL_NAME}" group-title="Otomatik Spor", {CHANNEL_NAME}
{stream_url}
"""
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write(m3u_content)
        else:
            print("Aktif sayfa bulundu ancak .m3u8 akış adresi yakalanamadı.")

if __name__ == "__main__":
    asyncio.main() if hasattr(asyncio, 'main') else asyncio.run(main())
