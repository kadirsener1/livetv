import asyncio
import json
import os
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "tv247tr.json"
OUTPUT_FILE = "tv247tr.m3u"
LIVETV_DIR = "tv247"  # Bireysel m3u8 dosyalarının kaydedileceği klasör
MAX_CONCURRENT_TASKS = 2

DEFAULT_CHANNELS = [
    {
        "name": "Abc",
        "group": "Spor",
        "logo": "",
        "url": "https://tvnow247.top/watch/abc-usa/"
    }
]

def get_base_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

def sanitize_filename(name):
    """Dosya adındaki geçersiz karakterleri temizler ve boşlukları alt çizgi yapar."""
    # Windows/Linux için yasaklı karakterleri temizle: \ / : * ? " < > |
    clean_name = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean_name.strip().replace(" ", "_")

async def get_stream_link(context, channel, semaphore):
    async with semaphore:
        target_url = channel['url']
        referer = get_base_url(target_url)
        
        page = await context.new_page()
        
        # Gereksiz kaynakları engelle
        await page.route(
            "**/*",
            lambda route: route.abort() if route.request.resource_type in ["image", "media", "font", "imageset"] else route.continue_()
        )
        
        page.on("popup", lambda popup: popup.close())

        found_link = None
        stream_referer = referer
        link_found_event = asyncio.Event()

        async def intercept_response(response):
            nonlocal found_link, stream_referer
            if link_found_event.is_set():
                return

            url = response.url
            content_type = response.headers.get("content-type", "").lower()

            is_hls_url = any(ext in url.lower() for ext in [".m3u8", "m3u8", "/hls/", "playlist"])
            is_hls_mime = any(mime in content_type for mime in ["application/vnd.apple.mpegurl", "application/x-mpegurl"])

            if (is_hls_url or is_hls_mime) and url.startswith("http"):
                if not any(bad in url.lower() for bad in ["ad.", "ads.", "tracking", "beacon"]):
                    found_link = url
                    req_headers = response.request.headers
                    stream_referer = req_headers.get("referer", referer)
                    print(f"  [+] Ağdan yakalandı: {channel['name']} -> {url[:75]}...")
                    link_found_event.set()

        page.on("response", intercept_response)

        try:
            print(f"[*] Taranıyor: {channel['name']}")

            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

            if not link_found_event.is_set():
                for frame in page.frames:
                    try:
                        content = await frame.content()
                        matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
                        if matches:
                            found_link = matches[0]
                            stream_referer = frame.url
                            print(f"  [+] Kaynak koddan ayıklandı: {channel['name']} -> {found_link[:75]}...")
                            link_found_event.set()
                            break

                        selectors = [".play", "#play", "video", ".vjs-big-play-button", ".jw-display-icon-container"]
                        for sel in selectors:
                            loc = frame.locator(sel).first
                            if await loc.count() > 0:
                                await loc.click(force=True, timeout=500)
                                break
                    except Exception:
                        pass

            if not link_found_event.is_set():
                try:
                    await asyncio.wait_for(link_found_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    print(f"  [-] Link bulunamadı: {channel['name']}")

        except Exception as e:
            print(f"  [!] Hata ({channel['name']}): {str(e)[:60]}")
        finally:
            await page.close()

        if found_link:
            return {
                "name": channel.get("name", "Kanal"),
                "group": channel.get("group", "Genel"),
                "logo": channel.get("logo", ""),
                "stream": found_link,
                "referer": stream_referer
            }
        return None

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

    # 'livetv' klasörü yoksa oluştur
    os.makedirs(LIVETV_DIR, exist_ok=True)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-gpu",
                "--disable-dev-shm-usage"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        tasks = [get_stream_link(context, ch, semaphore) for ch in channels]
        results_raw = await asyncio.gather(*tasks)
        results = [res for res in results_raw if res is not None]

        await browser.close()

    if results:
        # 1. Toplu tv247.m3u dosyasını yazdır
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in results:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                f.write(f"{item['stream']}\n\n")
        
        # 2. Her kanal için livetv klasörüne ayrı m3u8 dosyası oluştur
        print("\n[*] Bireysel m3u8 dosyaları oluşturuluyor...")
        for item in results:
            safe_name = sanitize_filename(item["name"])
            channel_file_path = os.path.join(LIVETV_DIR, f"{safe_name}.m3u8")
            
            with open(channel_file_path, "w", encoding="utf-8") as cf:
                cf.write("#EXTM3U\n")
                cf.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                cf.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                cf.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                cf.write(f"{item['stream']}\n")
                
        print(f"[+] Toplam {len(results)} kanal için '{LIVETV_DIR}/' altında bağımsız m3u8 dosyaları oluşturuldu.")
        print(f"[+] '{OUTPUT_FILE}' başarıyla güncellendi.")
    else:
        print("\n[-] Uygun yayın linki bulunamadı.")

if __name__ == "__main__":
    asyncio.run(main())
