import asyncio
import json
import os
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "tv247ws.json"
OUTPUT_FILE = "tv247tr.m3u"
LIVETV_DIR = "tv247tr"

# 800 kanal için ideal kararlılık hızı. Sisteminiz ve internetiniz çok iyiyse 6 yapabilirsiniz.
# Çok yüksek sayı sitelerin sizi engellemesine (HTTP 429) yol açar.
MAX_CONCURRENT_TASKS = 3
MAX_RETRIES = 2  # Başarısız olan kanallar için ekstra deneme sayısı

# Engellenecek reklam ve takipçi domain kalıpları
AD_DOMAINS = [
    "doubleclick", "google-analytics", "googlesyndication", "adservice", 
    "adsterra", "propellerads", "popads", "juicyads", "exoclick", "onclickads",
    "daisypath", "histats", "amung", "statcounter", "addthis", "sharethis"
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
    """Kanalı kararlı hale getirmek için hata durumunda yeniden deneme (retry) mekanizması içeren ana fonksiyon."""
    for attempt in range(1, MAX_RETRIES + 2):
        async with semaphore:
            try:
                result = await get_stream_link(context, channel, attempt)
                if result:
                    return result
            except Exception as e:
                print(f"  [!] Hata ({channel['name']} - Deneme {attempt}): {str(e)[:50]}")
            
            if attempt < MAX_RETRIES + 1:
                # Yeniden denemeden önce kısa bir süre bekle (Sitenin kendine gelmesi için)
                await asyncio.sleep(2)
    return None

async def get_stream_link(context, channel, attempt):
    target_url = channel['url']
    referer = get_base_url(target_url)
    
    page = await context.new_page()
    
    # Reklamları, resimleri ve CSS dosyalarını engelleyerek hem hız kazanın hem de reklam yönlendirmelerini önleyin
    async def route_interceptor(route):
        req = route.request
        url = req.url.lower()
        # Görsel, yazı tipi veya reklam domaini ise engelle
        if req.resource_type in ["image", "font", "imageset"] or any(ad in url for ad in AD_DOMAINS):
            return await route.abort()
        return await route.continue_()

    await page.route("**/*", route_interceptor)
    
    # Popup (Yeni sekme açılmasını) anında kapat
    page.on("popup", lambda popup: popup.close())

    found_link = None
    stream_referer = referer
    link_found_event = asyncio.Event()

    # Link yakalama fonksiyonu
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

    # Ağ isteklerini (Requests) milisaniyelik seviyede dinle (En kesin yöntem)
    page.on("request", lambda req: check_and_set_link(req.url, req.headers))
    page.on("response", lambda res: check_and_set_link(res.url, res.request.headers))

    try:
        # Deneme sayısına göre dinamik zaman aşımı belirle (Sonraki denemelerde süreyi artır)
        timeout_limit = 15000 if attempt == 1 else 22000
        
        # Sayfanın reklamlar yüzünden başka yere yönlenmesini JS ile sabitle
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.open = function() { return null; }; 
            window.onbeforeunload = function() { return null; };
        """)

        # Sayfayı yükle
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_limit)
        
        # İlk 3 saniye ağ trafiğinde m3u8 aranıyor
        try:
            await asyncio.wait_for(link_found_event.wait(), timeout=3.5)
        except asyncio.TimeoutError:
            pass

        # Eğer hala bulunamadıysa, tüm Iframe'lerin içine sız ve tetikle
        if not link_found_event.is_set():
            frames = page.frames
            for frame in frames:
                try:
                    # 1. Adım: Frame içindeki HTML kodundan Regex ile m3u8 ayıkla
                    content = await frame.content()
                    matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
                    if matches:
                        check_and_set_link(matches[0])
                        stream_referer = frame.url
                        break
                    
                    # 2. Adım: Oynatıcı butonlarını JavaScript ile tetikle (Overlay/Reklam engelini aşar)
                    selectors = [
                        "video", ".jw-video", "iframe", "button[class*='play']", 
                        ".vjs-big-play-button", ".jw-display-icon-container", 
                        "#player", "#play", ".play-btn", ".play"
                    ]
                    for sel in selectors:
                        locator = frame.locator(sel).first
                        if await locator.count() > 0:
                            # Standart click yerine JS click kullanarak reklam katmanını delip geçiyoruz
                            await locator.evaluate("el => el.click()")
                            break
                except Exception:
                    continue

        # Tıklamadan sonra ağın tepki vermesi için son bekleme
        if not link_found_event.is_set():
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=6.0)
            except asyncio.TimeoutError:
                pass

    except Exception as e:
        if attempt == (MAX_RETRIES + 1):
            print(f"  [-] Link bulunamadı: {channel['name']} (Tüm denemeler başarısız)")
    finally:
        await page.close()

    if found_link:
        print(f"  [+] Yakalandı ({attempt}. Denemede): {channel['name']}")
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
        # Chromium tarayıcıyı gelişmiş iframe sızma argümanlarıyla başlatıyoruz
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--blink-settings=imagesEnabled=false",
                # Aşağıdaki iki satır cross-origin iframe kısıtlamalarını tamamen kaldırır!
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        print(f"[*] Toplam {len(channels)} kanal taranıyor. Kararlılık modu aktif...")
        tasks = [scan_channel(context, ch, semaphore) for ch in channels]
        results_raw = await asyncio.gather(*tasks)
        results = [res for res in results_raw if res is not None]

        await browser.close()

    if results:
        # Toplu M3U Yazma
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in results:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0\n')
                f.write(f"{item['stream']}\n\n")
        
        # Bireysel M3U8 Dosyalarını Yazma
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
                
        print(f"[+] Başarıyla tamamlandı! {len(results)} adet aktif yayın dosyalandı.")
    else:
        print("\n[-] Hiçbir aktif yayın tespit edilemedi.")

if __name__ == "__main__":
    asyncio.run(main())
