import asyncio
import json
import os
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "channels.json"
OUTPUT_FILE = "playlist.m3u"
MAX_CONCURRENT_TASKS = 4  # Aynı anda taranacak kanal sayısı (Sistem gücüne göre 3-8 arası ayarlanabilir)

DEFAULT_CHANNELS = [
    {
        "name": "Abc usa",
        "group": "Spor",
        "logo": "",
        "url": "https://tvnow247.top/watch/abc-usa/"
    }
]

def get_base_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

async def get_stream_link(context, channel, semaphore):
    async with semaphore:
        target_url = channel['url']
        referer = get_base_url(target_url)
        
        page = await context.new_page()
        
        # Gereksiz kaynakları (resim, font, medya vb.) engelleyerek hız kazandır
        await page.route(
            "**/*",
            lambda route: route.abort() if route.request.resource_type in ["image", "media", "font", "imageset"] else route.continue_()
        )
        
        # Reklam sekmelerini doğrudan kapat
        page.on("popup", lambda popup: popup.close())

        found_link = None
        stream_referer = referer
        link_found_event = asyncio.Event()

        # 1. Ağ Trafiğini Dinle
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

            # 'domcontentloaded' sayfa iskeleti geldiğinde devam eder (çok daha hızlıdır)
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            # Eğer ağ trafiğinden hemen link gelmediyse kısa bir süre bekle ya da frame'leri tara
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

            # Link henüz bulunamadıysa frame ve butonları kontrol et
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

                        # Oynatıcı tetikleyicilerine hızlı tıklama denemesi
                        selectors = [".play", "#play", "video", ".vjs-big-play-button", ".jw-display-icon-container"]
                        for sel in selectors:
                            loc = frame.locator(sel).first
                            if await loc.count() > 0:
                                await loc.click(force=True, timeout=500)
                                break
                    except Exception:
                        pass

            # Tıklamadan sonra ağ yanıtı için son kısa bekleme
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

        # Tüm kanalları eşzamanlı olarak tara
        tasks = [get_stream_link(context, ch, semaphore) for ch in channels]
        results_raw = await asyncio.gather(*tasks)

        # Başarılı sonuçları filtrele
        results = [res for res in results_raw if res is not None]

        await browser.close()

    if results:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in results:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                f.write(f"{item['stream']}\n\n")
        print(f"\n[+] Toplam {len(results)} kanal ile '{OUTPUT_FILE}' başarıyla oluşturuldu.")
    else:
        print("\n[-] Uygun yayın linki bulunamadı.")

if __name__ == "__main__":
    asyncio.run(main())
