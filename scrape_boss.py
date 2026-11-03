import asyncio
from playwright.async_api import async_playwright

# Taranacak kanalların listesi (İsim ve URL çiftleri)
CHANNELS = [
    {
        "name": "Boss Sports - Tflix",
        "url": "https://bosssports1074.com/?channel=channel%3Atflix-MDJjNzUwY2JiYTUzYTZlZg",
        "group": "Spor Kanalları"
    },
    # Yeni kanalları buraya aynı formatta ekleyebilirsiniz:
    {
        "name": "Boss Sports - Örnek Kanal 2",
        "url": "https://bosssports1074.com/?channel=channel%3Aornek-kanal-kodu",
        "group": "Spor Kanalları"
    }
]

OUTPUT_FILE = "playlist.m3u"

async def get_stream_url(page, channel_url):
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and not stream_url:
            stream_url = request.url

    page.on("request", handle_request)

    try:
        print(f"Yükleniyor: {channel_url}")
        await page.goto(channel_url, timeout=45000)
        await page.wait_for_timeout(5000) # Oynatıcının ve isteğin tetiklenmesi için bekle
    except Exception as e:
        print(f"Yükleme hatası ({channel_url}): {e}")

    # Dinleyiciyi kaldır
    page.remove_listener("request", handle_request)
    return stream_url

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        m3u_lines = ["#EXTM3U\n"]

        for channel in CHANNELS:
            print(f"\nİşleniyor: {channel['name']}")
            url = await get_stream_url(page, channel["url"])
            
            if url:
                print(f" Başarılı! Bulunan link: {url}")
                # TiviMate ve IPTV oynatıcıları için uyumlu M3U satırı
                extinf = f'#EXTINF:-1 tvg-name="{channel["name"]}" group-title="{channel["group"]}", {channel["name"]}\n'
                m3u_lines.append(extinf)
                m3u_lines.append(f"{url}\n")
            else:
                print(f" Akış adresi yakalanamadı: {channel['name']}")

        await browser.close()

        # Toplu halde playlist.m3u dosyasına yaz
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.writelines(m3u_lines)
        
        print(f"\nTüm işlemler tamamlandı. {OUTPUT_FILE} dosyası güncellendi!")

if __name__ == "__main__":
    asyncio.run(main())
