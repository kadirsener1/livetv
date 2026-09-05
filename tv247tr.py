import asyncio
import json
import os
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "tv247tr.json"
OUTPUT_FILE = "tv247tr.m3u"
LIVETV_DIR = "tv247tr"

# HIZ AYARLARI
# Bilgisayarınız ve internetiniz iyiyse bunu 12-15 yapabilirsiniz. Standart PC için 8-10 idealdir.
MAX_CONCURRENT_TASKS = 3 
MAX_RETRIES = 1  # 2 yerine 1 yapıldı (Ölü kanallarda vakit kaybetmemek için)

# Engellenecek reklam ve gereksiz domainler
AD_DOMAINS = [
    "doubleclick", "google-analytics", "googlesyndication", "adservice", 
    "adsterra", "propellerads", "popads", "juicyads", "exoclick", "onclickads",
    "daisypath", "histats", "amung", "statcounter", "addthis", "sharethis",
    "facebook", "twitter", "instagram"
]

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

async def scan_channel(context, channel, semaphore):
    for attempt in range(1, MAX_RETRIES + 2):
        async with semaphore:
            try:
                result = await get_stream_link(context, channel, attempt)
                if result:
                    return result
            except Exception:
                pass
            
            if attempt < MAX_RETRIES + 1:
                await asyncio.sleep(0.5) # Bekleme süresi 2sn'den 0.5sn'ye düşürüldü
    return None

async def get_stream_link(context, channel, attempt):
    target_url = channel['url']
    referer = get_base_url(target_url)
    
    page = await context.new_page()
    found_link = None
    stream_referer = referer
    link_found_event = asyncio.Event()

    # Link kontrol fonksiyonu
    def check_and_set_link(url, req_headers=None):
        nonlocal found_link, stream_referer
        if link_found_event.is_set():
            return
        
        clean_url = url.split("#")[0].split("?")[0] if "?" in url else url
        if any(ext in clean_url.lower() for ext in [".m3u8", "m3u8", "/hls/", "playlist"]):
            if not any(bad in clean_url.lower() for bad in ["ad.", "ads.", "tracking", "beacon"]):
                found_link = url
                if req_headers and "referer" in req_headers:
                    stream_referer = req_headers["referer"]
                link_found_event.set()

    # Turbo Hız: CSS, Font, Resim ve Medyayı TAMAMEN iptal et (Sayfa aşırı hızlı yüklenir)
    async def route_interceptor(route):
        req = route.request
        url = req.url.lower()
        if req.resource_type in ["image", "font", "stylesheet", "media", "imageset"] or any(ad in url for ad in AD_DOMAINS):
            return await route.abort()
        
        # İstek anında URL kontrolü
        check_and_set_link(req.url, req.headers)
        return await route.continue_()

    await page.route("**/*", route_interceptor)
    page.on("popup", lambda popup: popup.close())
    page.on("response", lambda res: check_and_set_link(res.url, res.request.headers))

    try:
        # Timeoutlar kısaltıldı (Hızlı sonuç almak için)
        timeout_limit = 8000 if attempt == 1 else 12000
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.open = function() { return null; }; 
            window.onbeforeunload = function() { return null; };
        """)

        # Sayfaya git
        try:
            await page.goto(target_url, wait_until="commit", timeout=timeout_limit)
        except Exception:
            pass

        # 1. Aşama: Link hemen ağ trafiğine düştü mü? (Maksimum 2 saniye bekle)
        try:
            await asyncio.wait_for(link_found_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # 2. Aşama: Bulunamadıysa hızlıca JS buton tetiklemesi yap
        if not link_found_event.is_set():
            try:
                # Tüm frame'lerdeki play butonlarına tek seferde hızlı JS click at
                await page.evaluate("""() => {
                    const selectors = ['video', '.jw-video', 'iframe', 'button[class*="play"]', '.vjs-big-play-button', '#player', '#play', '.play-btn', '.play'];
                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            try { el.click(); } catch(e){}
                        });
                    });
                }""")
            except Exception:
                pass

            # Tıklamadan sonra son 2.5 saniye bekle
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=2.5)
            except asyncio.TimeoutError:
                pass

    except Exception:
        pass
    finally:
        await page.close()

    if found_link:
        print(f"  [+] Yakalandı: {channel['name']}")
        return {
            "name": channel.get("name", "Kanal"),
            "group": channel.get("group", "Genel"),
            "logo": channel.get("logo", ""),
            "stream": found_link,
            "referer": stream_referer
        }
    else:
        if attempt == (MAX_RETRIES + 1):
            print(f"  [-] Başarısız: {channel['name']}")
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
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--renderer-process-limit=4" # Bellek şişmesini önler
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 800, "height": 600} # Küçük çözünürlük daha hızlıdır
        )

        print(f"[*] Toplam {len(channels)} kanal taranıyor (Eşzamanlı: {MAX_CONCURRENT_TASKS})...")
        tasks = [scan_channel(context, ch, semaphore) for ch in channels]
        results_raw = await asyncio.gather(*tasks)
        results = [res for res in results_raw if res is not None]

        await browser.close()

    if results:
        # Toplu Genel IPTV M3U Dosyası Yazma
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in results:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                f.write(f"{item['stream']}\n\n")
        
        # Bireysel M3U8 Dosyalarını İstenen Formatta Yazma
        print(f"\n[*] Bireysel m3u8 dosyaları oluşturuluyor ({len(results)} kanal)...")
        for item in results:
            safe_name = sanitize_filename(item["name"])
            channel_file_path = os.path.join(LIVETV_DIR, f"{safe_name}.m3u8")
            
            with open(channel_file_path, "w", encoding="utf-8") as cf:
                cf.write("#EXTM3U\n")
                cf.write("#EXT-X-VERSION:3\n")
                cf.write("#EXT-X-STREAM-INF:BANDWIDTH=8000000\n")
                cf.write(f"{item['stream']}\n")
                
        print(f"[+] Tamamlandı! {len(results)} adet aktif yayın kaydedildi.")
    else:
        print("\n[-] Hiçbir aktif yayın tespit edilemedi.")

if __name__ == "__main__":
    asyncio.run(main())
