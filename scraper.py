import asyncio
import json
import os
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "channels.json"
OUTPUT_FILE = "playlist.m3u"

DEFAULT_CHANNELS = [
    {
        "name": "Hoofoot Kanal",
        "group": "Spor",
        "logo": "",
        "url": "https://hoofoot.ru/iptv/channel?id=6303492"
    }
]

def get_base_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

async def get_stream_link(context, channel):
    target_url = channel['url']
    referer = get_base_url(target_url)
    
    page = await context.new_page()
    
    # Reklam sekmelerini engelle
    page.on("popup", lambda popup: popup.close())

    found_link = None
    stream_referer = referer
    link_found_event = asyncio.Event()

    # 1. Ağ Yanıtlarını ve MIME Türlerini Dinle
    async def intercept_response(response):
        nonlocal found_link, stream_referer
        if link_found_event.is_set():
            return

        url = response.url
        content_type = response.headers.get("content-type", "").lower()

        # URL'de m3u8/hls araması veya Content-Type HLS kontrolü
        is_hls_url = any(ext in url.lower() for ext in [".m3u8", "m3u8", "/hls/", "playlist"])
        is_hls_mime = any(mime in content_type for mime in ["application/vnd.apple.mpegurl", "application/x-mpegurl"])

        if (is_hls_url or is_hls_mime) and url.startswith("http"):
            # Reklam/segment dışı filtreleme
            if not any(bad in url.lower() for bad in ["ad.", "ads.", "tracking", "beacon"]):
                found_link = url
                req_headers = response.request.headers
                stream_referer = req_headers.get("referer", referer)
                print(f"  [+] Ağ üzerinden yakalandı: {url[:90]}...")
                link_found_event.set()

    page.on("response", intercept_response)

    try:
        print(f"\n[*] Taranıyor: {channel['name']} -> ({target_url})")

        # Headless tespitini engellemek için tarayıcı değişkenlerini gizle
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        await page.goto(target_url, wait_until="load", timeout=45000)
        
        # JS kodlarının çalışması için kısa bir bekleme
        await asyncio.sleep(3)

        # 2. Sayfa ve Frame'lerin Kaynak Kodlarında/JS Değişkenlerinde URL Arama
        for frame in page.frames:
            try:
                # Sayfadaki inline JS içeriklerini incele
                content = await frame.content()
                # Regex ile kaynak kodu içindeki m3u8 veya stream bağlantılarını ara
                matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
                if matches and not found_link:
                    found_link = matches[0]
                    stream_referer = frame.url
                    print(f"  [+] JS/HTML içinden ayıklandı: {found_link[:90]}...")
                    link_found_event.set()
                    break

                # Oynatıcı tetikleyicilerine tıklama denemeleri
                selectors = [
                    "button", ".play", "#play", "video", 
                    ".vjs-big-play-button", ".jw-display-icon-container"
                ]
                for sel in selectors:
                    loc = frame.locator(sel).first
                    if await loc.is_visible(timeout=300):
                        await loc.click(force=True, timeout=1000)
                        break
            except Exception:
                pass

        # Link henüz gelmediyse ağ trafiğini dinlemeye devam et
        if not link_found_event.is_set():
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=12.0)
            except asyncio.TimeoutError:
                print(f"  [-] '{channel['name']}' için akış adresi yakalanamadı.")

    except Exception as e:
        print(f"  [!] Hata oluştu: {str(e)[:100]}")
    finally:
        await page.close()

    return found_link, stream_referer

async def main():
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            try:
                channels = json.load(f)
            except Exception as e:
                print(f"[HATA] JSON okunamadı: {e}")
                channels = DEFAULT_CHANNELS
    else:
        channels = DEFAULT_CHANNELS

    results = []

    async with async_playwright() as p:
        # Gerçek bir kullanıcı gibi davranması için tarayıcı argümanları
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for ch in channels:
            stream_link, referer = await get_stream_link(context, ch)
            if stream_link:
                results.append({
                    "name": ch.get("name", "Kanal"),
                    "group": ch.get("group", "Genel"),
                    "logo": ch.get("logo", ""),
                    "stream": stream_link,
                    "referer": referer
                })

        await browser.close()

    if results:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in results:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                f.write(f"{item['stream']}\n\n")
        print(f"\n[+] '{OUTPUT_FILE}' başarıyla oluşturuldu.")
    else:
        print("\n[-] Uygun yayın linki bulunamadı.")

if __name__ == "__main__":
    asyncio.run(main())
