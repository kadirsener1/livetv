import asyncio
import json
import os
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "tv247tr.json"
OUTPUT_FILE = "tv247tr.m3u"
LIVETV_DIR = "tv247tr"
MAX_CONCURRENT_TASKS = 8  # Sisteminizin gücüne göre 6-12 arası ayarlayabilirsiniz

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
    clean_name = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean_name.strip().replace(" ", "_")

async def get_stream_link(context, channel, semaphore):
    async with semaphore:
        target_url = channel['url']
        referer = get_base_url(target_url)
        
        page = await context.new_page()
        
        # Sadece medya ve görselleri engelle, script ve xhr akışına izin ver
        await page.route(
            "**/*",
            lambda route: route.abort() if route.request.resource_type in ["image", "font", "imageset"] else route.continue_()
        )
        
        page.on("popup", lambda popup: popup.close())

        found_link = None
        stream_referer = referer
        link_found_event = asyncio.Event()

        def check_and_set_link(url, req_headers=None):
            nonlocal found_link, stream_referer
            if link_found_event.is_set():
                return
            
            clean_url = url.split("#")[0]
            # m3u8 veya HLS akış parametrelerini yakala
            if any(ext in clean_url.lower() for ext in [".m3u8", "m3u8", "/hls/", "playlist.m3u8"]):
                if not any(bad in clean_url.lower() for bad in ["ad.", "ads.", "tracking", "beacon", "telemetry"]):
                    found_link = clean_url
                    if req_headers and "referer" in req_headers:
                        stream_referer = req_headers["referer"]
                    print(f"  [+] Yakalandı: {channel['name']} -> {found_link[:75]}...")
                    link_found_event.set()

        # İstek başladığı anda yakalamak için request dinleyicisi
        async def on_request(request):
            check_and_set_link(request.url, request.headers)

        # Yanıt MIME türünden yakalamak için response dinleyicisi
        async def on_response(response):
            if link_found_event.is_set():
                return
            content_type = response.headers.get("content-type", "").lower()
            if any(mime in content_type for mime in ["application/vnd.apple.mpegurl", "application/x-mpegurl"]):
                check_and_set_link(response.url, response.request.headers)

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            print(f"[*] Taranıyor: {channel['name']}")

            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.open = function() { return null; }; // İstenmeyen reklam sekmelerini engelle
            """)

            try:
                # domcontentloaded genelde yeterlidir
                await page.goto(target_url, wait_until="domcontentloaded", timeout=12000)
            except Exception:
                pass

            # Link hemen geldiyse beklemeden devam et (maksimum 2.5 sn dinle)
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=2.5)
            except asyncio.TimeoutError:
                pass

            # Link henüz yakalanamadıysa iframe ve tıklama kontrollerini çalıştır
            if not link_found_event.is_set():
                for frame in page.frames:
                    try:
                        # 1. Frame kaynak kodunu tara
                        content = await frame.content()
                        matches = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', content)
                        if matches:
                            check_and_set_link(matches[0])
                            stream_referer = frame.url
                            break

                        # 2. Oynatıcı tetikleyicilerine tıkla
                        selectors = [
                            "button[class*='play']", ".vjs-big-play-button", 
                            ".jw-display-icon-container", "video", "#player", 
                            "#play", ".play-btn", ".play"
                        ]
                        for sel in selectors:
                            loc = frame.locator(sel).first
                            if await loc.count() > 0:
                                await loc.click(force=True, timeout=800)
                                break
                    except Exception:
                        continue

            # Tıklamadan sonra isteğin gitmesi için kısa bir süre tanı
            if not link_found_event.is_set():
                try:
                    await asyncio.wait_for(link_found_event.wait(), timeout=4.0)
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
                "--disable-dev-shm-usage",
                "--blink-settings=imagesEnabled=false"  # Görsel yüklemelerini tarayıcı seviyesinde kes
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
        # Toplu M3U yazma
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in results:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                f.write(f"{item['stream']}\n\n")
        
        # Tekil M3U8 dosyalarını yazma
        print(f"\n[*] Bireysel m3u8 dosyaları oluşturuluyor ({len(results)} kanal)...")
        for item in results:
            safe_name = sanitize_filename(item["name"])
            channel_file_path = os.path.join(LIVETV_DIR, f"{safe_name}.m3u8")
            
            with open(channel_file_path, "w", encoding="utf-8") as cf:
                cf.write("#EXTM3U\n")
                cf.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                cf.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                cf.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                cf.write(f"{item['stream']}\n")
                
        print(f"[+] '{OUTPUT_FILE}' ve '{LIVETV_DIR}/' klasörü başarıyla güncellendi.")
    else:
        print("\n[-] Uygun yayın linki bulunamadı.")

if __name__ == "__main__":
    asyncio.run(main())
