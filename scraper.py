import asyncio
import json
import os
from playwright.async_api import async_playwright

CHANNELS_FILE = "channels.json"
OUTPUT_FILE = "playlist.m3u"
BASE_REFERER = "https://livelive24.com/"

async def get_stream_link(context, channel):
    """Verilen bir kanal için tek bir .m3u8 linki bulur."""
    page = await context.new_page()
    found_link = None
    link_found_event = asyncio.Event()

    async def intercept_response(response):
        nonlocal found_link
        if link_found_event.is_set():
            return
        
        url = response.url
        if ".m3u8" in url and url.startswith("http"):
            found_link = url
            print(f"  [+] Link bulundu: {url[:80]}...")
            link_found_event.set()

    page.on("response", intercept_response)

    try:
        print(f"\n[*] Kanal aranıyor: {channel['name']}")
        await page.goto(channel['url'], wait_until="domcontentloaded", timeout=45000)
        
        # Oynatıcıyı tetiklemek için tıklama denemesi
        try:
            await page.click("button, .vjs-big-play-button, #player", timeout=3000)
        except Exception:
            pass
        
        # Maksimum 15 saniye link için bekle
        try:
            await asyncio.wait_for(link_found_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            print(f"  [-] '{channel['name']}' için link bulunamadı (timeout).")

    except Exception as e:
        print(f"  [!] '{channel['name']}' işlenirken hata: {str(e)[:100]}")
    finally:
        await page.close()

    return found_link


async def main():
    # 1. Kanal listesini oku
    if not os.path.exists(CHANNELS_FILE):
        print(f"[HATA] {CHANNELS_FILE} dosyası bulunamadı!")
        return
    
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        channels = json.load(f)
    
    print(f"[*] Toplam {len(channels)} kanal işlenecek.")
    
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={"Referer": BASE_REFERER}
        )

        # Her kanalı sırayla işle
        for channel in channels:
            stream_link = await get_stream_link(context, channel)
            if stream_link:
                results.append({
                    "name": channel["name"],
                    "group": channel.get("group", "Diğer"),
                    "logo": channel.get("logo", ""),
                    "stream": stream_link
                })

        await browser.close()

    # 2. Sonuçları M3U dosyasına yaz
    if results:
        print(f"\n[*] {len(results)} kanal başarıyla bulundu. Dosya yazılıyor...")
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            
            for item in results:
                # EXTINF satırı: logo, grup ve isim bilgilerini içerir
                f.write(
                    f'#EXTINF:-1 tvg-logo="{item["logo"]}" '
                    f'group-title="{item["group"]}",{item["name"]}\n'
                )
                # Yayın linkini oynatabilmek için Referer bilgisi (VLC/Kodi için)
                f.write(f'#EXTVLCOPT:http-referrer={BASE_REFERER}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n')
                f.write(f"{item['stream']}\n")
        
        print(f"[BAŞARILI] '{OUTPUT_FILE}' dosyası güncellendi.")
    else:
        print("[-] Kaydedilecek link bulunamadı, dosya güncellenmedi.")


if __name__ == "__main__":
    asyncio.run(main())
