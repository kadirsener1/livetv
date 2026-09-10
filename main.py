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

# Sadece zararlı/yavaşlatıcı reklamlar engellenir, yayın scriptlerine dokunulmaz
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
    page.on("popup", lambda popup: asyncio.create_task(popup.close()))

    async def route_interceptor(route):
        req = route.request
        url = req.url.lower()
        if req.resource_type in ["image", "font"] or any(ad in url for ad in AD_DOMAINS):
            return await route.abort()
        return await route.continue_()

    await page.route("**/*", route_interceptor)

    found_link = None
    stream_referer = referer
    link_found_event = asyncio.Event()

    def set_found_link(url, ref=None):
        nonlocal found_link, stream_referer
        if not link_found_event.is_set():
            found_link = url
            if ref:
                stream_referer = ref
            link_found_event.set()

    # Ağ istek ve yanıtlarını derinlemesine dinleme
    async def handle_response(res):
        if link_found_event.is_set():
            return
        
        url = res.url
        clean_url = url.split("?")[0].lower()

        # 1. Doğrudan URL kontrolü
        if any(ext in clean_url for ext in [".m3u8", "/hls/", "playlist.m3u8", "master.m3u8", "chunklist"]):
            if not any(bad in clean_url for bad in ["ad.", "ads.", "tracking", "beacon"]):
                set_found_link(url, res.request.headers.get("referer", referer))
                return

        # 2. Content-Type HLS kontrolü
        ct = res.headers.get("content-type", "").lower()
        if any(hls_type in ct for hls_type in ["mpegurl", "application/vnd.apple.mpegurl", "x-mpegurl"]):
            set_found_link(url, res.request.headers.get("referer", referer))
            return

        # 3. JSON / API Yanıtlarının içindeki gizli m3u8 taraması
        if any(t in ct for t in ["json", "javascript", "text/plain"]):
            try:
                text = await res.text()
                if ".m3u8" in text:
                    matches = re.findall(r'(https?://[^"\'\s<>\\]+?\.m3u8[^"\'\s<>\\]*)', text)
                    if matches:
                        clean_found = matches[0].replace(r'\/', '/')
                        set_found_link(clean_found, res.request.headers.get("referer", referer))
            except Exception:
                pass

    page.on("response", handle_response)
    page.on("request", lambda req: (
        set_found_link(req.url, req.headers.get("referer", referer))
        if any(ext in req.url.split("?")[0].lower() for ext in [".m3u8", "master.m3u8"]) 
        and not any(bad in req.url.lower() for bad in ["ad.", "ads."])
        else None
    ))

    try:
        timeout_limit = 25000 if attempt == 1 else 30000
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        print(f"[*] Sayfa yükleniyor: {channel['name']}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_limit)
        await asyncio.sleep(2.5)

        # 1. "Servers" / "Sunucular" sekmesini aç
        try:
            tab_selectors = [
                "button:has-text('Servers')", "a:has-text('Servers')", 
                "button:has-text('Server')", "a:has-text('Server')",
                "[data-tab='servers']", "#servers-tab"
            ]
            for t_sel in tab_selectors:
                tab_btn = page.locator(t_sel).first
                if await tab_btn.count() > 0 and await tab_btn.is_visible():
                    await tab_btn.click(force=True)
                    await asyncio.sleep(1.0)
                    break
        except Exception:
            pass

        # 2. Aktif Sunucuları Tespit Et
        server_names = ["AUTO", "MERCURY", "VENUS", "EARTH", "MARS", "JUPITER", "SATURN", "SERVER"]
        elements = await page.locator("button, a, div[role='button'], li").all()
        active_servers = []

        for el in elements:
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.text_content() or "").strip().upper()
                if any(k in txt for k in server_names):
                    if "OFFLINE" not in txt and "DISABLED" not in txt:
                        active_servers.append((txt, el))
            except Exception:
                continue

        # "AUTO" veya "EARTH" sunucularını listenin en başına koy
        active_servers.sort(key=lambda x: 0 if "AUTO" in x[0] else (1 if "EARTH" in x[0] else 2))
        print(f"  [*] Tespit edilen aktif sunucu sayısı: {len(active_servers)}")

        # 3. Her Aktif Sunucuya Tıkla ve Video Oynatıcıyı Çalıştır
        for srv_name, srv_el in active_servers:
            if link_found_event.is_set():
                break

            short_name = srv_name.split()[0]
            print(f"  [>] Aktif sunucu deneniyor: {short_name}")
            try:
                await srv_el.click(force=True)
            except Exception:
                pass

            await asyncio.sleep(2.0)

            # Player / Video alanlarına fiziksel tıklama yap (Autoplay engelini aşmak için)
            for frame in page.frames:
                try:
                    # Video etiketine veya oynatıcı katmanına tıkla
                    video_el = frame.locator("video, #player, .player-container, .jw-video, .vjs-tech, iframe").first
                    if await video_el.count() > 0:
                        await video_el.click(force=True, timeout=1500)
                except Exception:
                    pass

            # Linkin yakalanması için bekle (Maksimum 5 sn)
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

        # 4. Son Kontrol: HTML Kaynak Kodlarında m3u8 Regex Taraması
        if not link_found_event.is_set():
            for frame in page.frames:
                try:
                    content = await frame.content()
                    matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
                    for m in matches:
                        set_found_link(m, frame.url)
                        break
                except Exception:
                    continue

    except Exception as e:
        if attempt == (MAX_RETRIES + 1):
            print(f"  [-] Link bulunamadı: {channel['name']}")
    finally:
        await page.close()

    if found_link:
        print(f"  [+] BAŞARILI: {channel['name']} -> Yayın linki yakalandı!")
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
                "--autoplay-policy=no-user-gesture-required"
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
                
        print(f"[+] İşlem tamamlandı! {len(results)} yayın kaydedildi.")
    else:
        print("\n[-] Aktif yayın bağlantısı tespit edilemedi.")

if __name__ == "__main__":
    asyncio.run(main())
