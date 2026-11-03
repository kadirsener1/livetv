import asyncio
from playwright.async_api import async_playwright

CHANNEL_URL = "https://bosssports1074.com/?channel=channel%3Atflix-MDJjNzUwY2JiYTUzYTZlZg"
CHANNEL_NAME = "Boss Sports - Tflix"
OUTPUT_FILE = "playlist.m3u"

async def run():
    async with async_playwright() as p:
        # Tarayıcıyı başlat
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        stream_url = None

        # Ağ isteklerini dinle ve m3u8 içeren URL'yi yakala
        def handle_request(request):
            nonlocal stream_url
            if ".m3u8" in request.url and not stream_url:
                stream_url = request.url

        page.on("request", handle_request)

        print("Sayfa açılıyor ve akış bekleniyor...")
        try:
            await page.goto(CHANNEL_URL, timeout=60000)
            # Oynatıcının yüklenmesi için birkaç saniye bekleyelim
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"Yükleme hatası: {e}")

        await browser.close()

        if stream_url:
            print(f"Başarılı! Yakalanan m3u8: {stream_url}")
            m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-name="{CHANNEL_NAME}" group-title="Otomatik Boss", {CHANNEL_NAME}
{stream_url}
"""
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write(m3u_content)
        else:
            print("Ağ trafiğinde .m3u8 adresi yakalanamadı.")

if __name__ == "__main__":
    asyncio.run(run())
