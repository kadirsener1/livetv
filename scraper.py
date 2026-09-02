import asyncio
import json
import os
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "channels.json"
OUTPUT_FILE = "playlist.m3u"

# channels.json yoksa varsayılan olarak taranacak liste
DEFAULT_CHANNELS = [
    {
        "name": "Hoofoot Canlı Kanal",
        "group": "Spor",
        "logo": "",
        "url": "https://hoofoot.ru/iptv/channel?id=6303492"
    }
]

def get_base_url(url):
    """URL'den referer adresi üretir."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

async def get_stream_link(context, channel):
    """Kanal sayfasından ve alt iframe'lerden .m3u8 linkini yakalar."""
    target_url = channel['url']
    referer = get_base_url(target_url)
    
    page = await context.new_page()
    
    # Sayfa tıklandığında açılan reklam sekmelerini otomatik kapat
    page.on("popup", lambda popup: popup.close())

    found_link = None
    stream_referer = referer
    link_found_event = asyncio.Event()

    # Ağ isteklerini dinle
    async def intercept_request(request):
        nonlocal found_link, stream_referer
        if link_found_event.is_set():
            return
        
        url = request.url
        # .m3u8 veya playlist uzantılı akışları filtrele
        if (".m3u8" in url or "playlist" in url) and url.startswith("http"):
            # Reklam segmentlerini veya takip scriptlerini atla
            if not any(bad in url.lower() for bad in ["ad.", "ads.", "tracking", "telemetry"]):
                found_link = url
                # İsteğin kendi gönderdiği Referer başlığını al (oynatma için önemlidir)
                req_headers = request.headers
                stream_referer = req_headers.get("referer", referer)
                print(f"  [+] Link yakalandi: {url[:80]}...")
                link_found_event.set()

    page.on("request", intercept_request)

    try:
        print(f"\n[*] Taranıyor: {channel['name']} -> ({target_url})")
        
        await page.set_extra_http_headers({
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        
        # Sayfayı aç
        await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)  # Dinamik içeriklerin ve iframe'lerin yüklenmesi için kısa bekleme

        # Ana sayfa ve tüm iframe'lerdeki oynat butonlarına tıklamayı dene
        for frame in page.frames:
            try:
                selectors = [
                    ".vjs-big-play-button", 
                    "#play", 
                    ".play", 
                    "button", 
                    "video", 
                    ".jw-display-icon-container", 
                    ".play-btn"
                ]
                for sel in selectors:
                    loc = frame.locator(sel).first
                    if await loc.is_visible(timeout=500):
                        await loc.click(force=True, timeout=1000)
                        break
            except Exception:
                pass

        # Linkin yakalanması için maksimum 15 saniye bekle
        try:
            await asyncio.wait_for(link_found_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            print(f"  [-] '{channel['name']}' icin .m3u8 yakalanamadi (Zaman asimi).")

    except Exception as e:
        print(f"  [!] '{channel['name']}' acilirken hata: {str(e)[:100]}")
    finally:
        await page.close()

    return found_link, stream_referer


async def main():
    # Kanal listesini yükle
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            try:
                channels = json.load(f)
            except json.JSONDecodeError as err:
                print(f"[HATA] {CHANNELS_FILE} dosyasında JSON format hatası: {err}")
                return
    else:
        print(f"[*] '{CHANNELS_FILE}' bulunamadı, varsayılan test linki kullanılıyor.")
        channels = DEFAULT_CHANNELS

    print(f"[*] Toplam {len(channels)} kanal taranacak.")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for channel in channels:
            stream_link, referer = await get_stream_link(context, channel)
            if stream_link:
                results.append({
                    "name": channel.get("name", "Kanal"),
                    "group": channel.get("group", "Canlı TV"),
                    "logo": channel.get("logo", ""),
                    "stream": stream_link,
                    "referer": referer
                })

        await browser.close()

    # M3U Dosyasını Oluştur
    if results:
        print(f"\n[*] {len(results)} kanal '{OUTPUT_FILE}' dosyasına yazılıyor...")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            
            for item in results:
                f.write(
                    f'#EXTINF:-1 tvg-logo="{item["logo"]}" '
                    f'group-title="{item["group"]}",{item["name"]}\n'
                )
                # VLC / TiviMate / IPTV oynatıcıları için Header bilgileri
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n')
                f.write(f'#EXTHTTP:{{"Referer":"{item["referer"]}","User-Agent":"Mozilla/5.0"}}\n')
                f.write(f"{item['stream']}\n\n")
        
        print(f"[BAŞARILI] '{OUTPUT_FILE}' başarıyla güncellendi.")
    else:
        print("[-] Hiçbir kanaldan akış (.m3u8) alınamadı.")


if __name__ == "__main__":
    asyncio.run(main())
