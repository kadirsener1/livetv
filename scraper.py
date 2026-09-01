import asyncio
import json
import os
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "channels.json"
OUTPUT_FILE = "playlist.m3u"

def get_base_url(url):
    """URL'den 'https://siteadi.com/' seklinde referer adresi uretir."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

async def get_stream_link(context, channel):
    """Verilen bir kanal URL'sinden ilk .m3u8 linkini yakalar."""
    target_url = channel['url']
    referer = get_base_url(target_url)
    
    page = await context.new_page()
    found_link = None
    link_found_event = asyncio.Event()

    # Ağ trafiğini dinle
    async def intercept_response(response):
        nonlocal found_link
        if link_found_event.is_set():
            return
        
        url = response.url
        # .m3u8 veya playlist linklerini yakala
        if (".m3u8" in url or "playlist" in url) and url.startswith("http"):
            # Reklam/segment harici ana oynatma listesini sec
            found_link = url
            print(f"  [+] Link yakalandi: {url[:90]}...")
            link_found_event.set()

    page.on("response", intercept_response)

    try:
        print(f"\n[*] Taranıyor: {channel['name']} -> ({target_url})")
        
        # Sayfaya git ve istek basliklarini siteye gore ayarla
        await page.set_extra_http_headers({"Referer": referer})
        await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        
        # Oynatici veya iframe icindeki play butonlarina tiklama denemesi
        try:
            # Genel oynatici secicileri
            selectors = ["button", ".vjs-big-play-button", "#player", "video", ".play-btn", "iframe"]
            for sel in selectors:
                if await page.locator(sel).first.is_visible():
                    await page.locator(sel).first.click(timeout=2000)
                    break
        except Exception:
            pass
        
        # Linkin yakalanmasi icin maksimum 15 saniye bekle
        try:
            await asyncio.wait_for(link_found_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            print(f"  [-] '{channel['name']}' icin .m3u8 bulunamadi (Zaman asimi).")

    except Exception as e:
        print(f"  [!] '{channel['name']}' acilirken hata: {str(e)[:100]}")
    finally:
        await page.close()

    return found_link, referer


async def main():
    if not os.path.exists(CHANNELS_FILE):
        print(f"[HATA] {CHANNELS_FILE} bulunamadi!")
        return
    
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        try:
            channels = json.load(f)
        except json.JSONDecodeError as err:
            print(f"[HATA] channels.json formatinda hata var:\n{err}")
            return
    
    print(f"[*] Toplam {len(channels)} kanal taranacak.")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for channel in channels:
            stream_link, referer = await get_stream_link(context, channel)
            if stream_link:
                results.append({
                    "name": channel.get("name", "Bilinmeyen Kanal"),
                    "group": channel.get("group", "Genel"),
                    "logo": channel.get("logo", ""),
                    "stream": stream_link,
                    "referer": referer
                })

        await browser.close()

    # M3U Dosyasini Olustur
    if results:
        print(f"\n[*] {len(results)} kanal listeye yaziliyor...")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            
            for item in results:
                f.write(
                    f'#EXTINF:-1 tvg-logo="{item["logo"]}" '
                    f'group-title="{item["group"]}",{item["name"]}\n'
                )
                # Her kanala ozel Referer basligi eklenir
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n')
                f.write(f"{item['stream']}\n\n")
        
        print(f"[BAŞARILI] '{OUTPUT_FILE}' basariyla guncellendi.")
    else:
        print("[-] Hicbir kanaldan link alinamadi.")


if __name__ == "__main__":
    asyncio.run(main())
