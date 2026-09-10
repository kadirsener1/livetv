import asyncio
import json
import os
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

CHANNELS_FILE = "channels.json"
OUTPUT_FILE = "playlist.m3u"
LIVETV_DIR = "streams"

MAX_CONCURRENT_TASKS = 1 
MAX_RETRIES = 1 

USER_AGENT_SUFFIX = "|User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Engellenecek reklam domainleri (Yayın scriptlerini bozmayacak şekilde optimize edildi)
AD_DOMAINS = [
    "doubleclick.net", "google-analytics.com", "adservice.google", 
    "adsterra.com", "propellerads.com", "popads.net", "onclickads.net",
    "histats.com", "amung.us"
]

DEFAULT_CHANNELS = [
    {
        "name": "TV8 Turkey",
        "group": "Ulusal",
        "logo": "",
        "url": "https://opstream.fun/live/1005?name=TV8%20Turkey&tab=channels"
    }
]

def get_base_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

def sanitize_filename(name):
    clean_name = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean_name.strip().replace(" ", "_")

def update_existing_m3u(file_path, results):
    new_links = {
        item["name"].strip().lower(): item["stream"].strip() 
        for item in results if item.get("stream")
    }

    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in results:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                f.write(f"{item['stream']}\n\n")
        print(f"[+] '{file_path}' dosyası oluşturuldu.")
        return

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    updated_lines = []
    pending_new_stream = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#EXTINF"):
            pending_new_stream = None
            if "," in stripped:
                channel_name = stripped.rsplit(",", 1)[1].strip().lower()
                if channel_name in new_links:
                    pending_new_stream = new_links[channel_name]
            updated_lines.append(line)
        elif stripped.startswith("#") or not stripped:
            updated_lines.append(line)
        else:
            if pending_new_stream:
                updated_lines.append(pending_new_stream + "\n")
                pending_new_stream = None
            else:
                updated_lines.append(line)

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)
    print(f"[+] '{file_path}' dosyası güncellendi.")

async def scan_channel(context, channel, semaphore):
    for attempt in range(1, MAX_RETRIES + 2):
        async with semaphore:
            try:
                result = await get_stream_link(context, channel, attempt)
                if result:
                    return result
            except Exception as e:
                print(f"  [!] Hata ({channel['name']} - Deneme {attempt}): {str(e)[:70]}")
            
            if attempt < MAX_RETRIES + 1:
                await asyncio.sleep(2)
    return None

async def get_stream_link(context, channel, attempt):
    target_url = channel['url']
    referer = get_base_url(target_url)
    
    page = await context.new_page()
    
    # Popup reklamları otomatik kapat
    page.on("popup", lambda popup: asyncio.create_task(popup.close()))

    async def route_interceptor(route):
        req = route.request
        url = req.url.lower()
        if req.resource_type in ["image", "font", "imageset"] or any(ad in url for ad in AD_DOMAINS):
            return await route.abort()
        return await route.continue_()

    await page.route("**/*", route_interceptor)

    found_link = None
    stream_referer = referer
    link_found_event = asyncio.Event()

    def check_and_set_link(url, req_headers=None):
        nonlocal found_link, stream_referer
        if link_found_event.is_set():
            return
        
        # M3U8 ve HLS yayın linklerini yakala
        clean_url = url.split("#")[0]
        if any(ext in clean_url.lower() for ext in [".m3u8", "m3u8", "/hls/", "playlist.m3u8", "chunklist"]):
            if not any(bad in clean_url.lower() for bad in ["ad.", "ads.", "tracking", "beacon", "statcounter"]):
                found_link = url
                if req_headers and "referer" in req_headers:
                    stream_referer = req_headers["referer"]
                link_found_event.set()

    page.on("request", lambda req: check_and_set_link(req.url, req.headers))
    page.on("response", lambda res: check_and_set_link(res.url, res.request.headers))

    try:
        timeout_limit = 20000 if attempt == 1 else 25000
        
        # Anti-Bot Koruması
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.open = function() { return null; };
        """)

        print(f"[*] Sayfa yükleniyor: {channel['name']}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_limit)
        await asyncio.sleep(3)

        # 1. ADIM: "Servers" sekmesini bul ve tıkla
        try:
            server_tab_selectors = [
                "button:has-text('Servers')", "a:has-text('Servers')", 
                "button:has-text('Server')", "a:has-text('Server')",
                "[data-tab='servers']", "#tab-servers", ".servers-tab"
            ]
            for tab_sel in server_tab_selectors:
                tab_btn = page.locator(tab_sel).first
                if await tab_btn.count() > 0 and await tab_btn.is_visible():
                    print(f"  [>] 'Servers' sekmesine tıklandı.")
                    await tab_btn.click(force=True)
                    await asyncio.sleep(1.5)
                    break
        except Exception:
            pass

        # 2. ADIM: Aktif Sunucu Butonlarını Tara ve Tıkla
        if not link_found_event.is_set():
            all_elements = await page.locator("button, a, div[role='button'], li").all()
            active_servers = []

            for el in all_elements:
                try:
                    if not await el.is_visible():
                        continue
                    text = (await el.text_content() or "").strip()
                    text_upper = text.upper()

                    # Bilinen sunucu isimleri
                    server_keywords = ["AUTO", "MERCURY", "VENUS", "EARTH", "MARS", "JUPITER", "SATURN", "SERVER"]
                    if any(k in text_upper for k in server_keywords):
                        # OFFLINE olanları ele
                        if "OFFLINE" not in text_upper and "DISABLED" not in text_upper:
                            active_servers.append((text_upper, el))
                except Exception:
                    continue

            # "AUTO" veya "EARTH" sunucularını öne al
            active_servers.sort(key=lambda x: 0 if "AUTO" in x[0] else (1 if "EARTH" in x[0] else 2))

            print(f"  [*] Tespit edilen aktif sunucu sayısı: {len(active_servers)}")

            for srv_name, srv_el in active_servers:
                if link_found_event.is_set():
                    break
                print(f"  [>] Aktif sunucu deneniyor: {srv_name.split()[0]}")
                try:
                    await srv_el.click(force=True)
                except Exception:
                    pass

                # 3. ADIM: Oynatıcı / Play Butonu Tetikleme
                await asyncio.sleep(1.5)
                for frame in page.frames:
                    try:
                        play_btns = frame.locator("video, .jw-display-icon-container, .vjs-big-play-button, button[aria-label='Play'], #player, .play-btn")
                        if await play_btns.count() > 0:
                            await play_btns.first.click(force=True, timeout=1500)
                    except Exception:
                        continue

                # Linkin ağdan yakalanması için bekle
                try:
                    await asyncio.wait_for(link_found_event.wait(), timeout=3.5)
                except asyncio.TimeoutError:
                    pass

        # 4. ADIM: HTML ve Frame İçinde Direkt Regex Taraması (Eğer ağdan düşmediyse)
        if not link_found_event.is_set():
            for frame in page.frames:
                try:
                    content = await frame.content()
                    matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
                    for m in matches:
                        check_and_set_link(m)
                        stream_referer = frame.url
                        break
                except Exception:
                    continue

    except Exception as e:
        if attempt == (MAX_RETRIES + 1):
            print(f"  [-] Link bulunamadı: {channel['name']}")
    finally:
        await page.close()

    if found_link:
        print(f"  [+] BAŞARILI: {channel['name']} -> Link yakalandı.")
        full_stream_link = f"{found_link}{USER_AGENT_SUFFIX}"
        return {
            "name": channel.get("name", "Kanal"),
            "group": channel.get("group", "Genel"),
            "logo": channel.get("logo", ""),
            "stream": full_stream_link,
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
                "--autoplay-policy=no-user-gesture-required"  # Otomatik video oynatmaya izin ver
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        print(f"[*] Toplam {len(channels)} kanal taranıyor...")
        tasks = [scan_channel(context, ch, semaphore) for ch in channels]
        results_raw = await asyncio.gather(*tasks)
        results = [res for res in results_raw if res is not None]

        await browser.close()

    if results:
        update_existing_m3u(OUTPUT_FILE, results)
        
        print(f"\n[*] Bireysel m3u8 dosyaları oluşturuluyor ({len(results)} kanal)...")
        for item in results:
            safe_name = sanitize_filename(item["name"])
            channel_file_path = os.path.join(LIVETV_DIR, f"{safe_name}.m3u8")
            
            with open(channel_file_path, "w", encoding="utf-8") as cf:
                cf.write("#EXTM3U\n")
                cf.write("#EXT-X-VERSION:3\n")
                cf.write("#EXT-X-STREAM-INF:BANDWIDTH=8000000\n")
                cf.write(f"{item['stream']}\n")
                
        print(f"[+] İşlem tamamlandı. {len(results)} yayın kaydedildi.")
    else:
        print("\n[-] Aktif yayın bağlantısı tespit edilemedi.")

if __name__ == "__main__":
    asyncio.run(main())
