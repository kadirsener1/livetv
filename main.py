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

    # Sadece gereksiz resim ve reklamları filtrele
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
            clean = url.strip().replace(r'\/', '/')
            # Reklam segmentlerini ele
            if not any(bad in clean.lower() for bad in ["ad.", "ads.", "statcounter", "beacon"]):
                found_link = clean
                if ref:
                    stream_referer = ref
                link_found_event.set()

    # JavaScript Tarafından Çağrılacak Köprü Fonksiyon
    await page.expose_function("__onStreamCaught", lambda u: set_found_link(u, page.url))

    # Tarayıcı Motoruna Enjekte Edilen Sniffer (XHR / Fetch / Hls.js / Video Hook)
    await page.add_init_script("""
        (function() {
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            function checkUrl(u) {
                if (!u || typeof u !== 'string') return;
                if (u.includes('.m3u8') || u.includes('/hls/') || u.includes('master.m3u8') || u.includes('playlist.m3u8')) {
                    try { window.__onStreamCaught(u); } catch(e){}
                }
            }

            // Hook XMLHttpRequest
            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url) {
                checkUrl(url);
                return origOpen.apply(this, arguments);
            };

            // Hook Fetch API
            const origFetch = window.fetch;
            window.fetch = function(input, init) {
                const url = (typeof input === 'string') ? input : (input ? input.url : '');
                checkUrl(url);
                return origFetch.apply(this, arguments);
            };

            // Hook HTMLMediaElement (Video player src)
            const videoSrcDesc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
            if (videoSrcDesc && videoSrcDesc.set) {
                const origSet = videoSrcDesc.set;
                Object.defineProperty(HTMLMediaElement.prototype, 'src', {
                    set: function(val) {
                        checkUrl(val);
                        return origSet.call(this, val);
                    }
                });
            }
        })();
    """)

    # Ağ yanıtlarını izleme
    async def handle_response(res):
        if link_found_event.is_set():
            return
        url = res.url
        clean_url = url.split("?")[0].lower()
        
        if any(ext in clean_url for ext in [".m3u8", "master.m3u8", "playlist.m3u8", "/hls/"]):
            set_found_link(url, res.request.headers.get("referer", referer))
            return

        ct = res.headers.get("content-type", "").lower()
        if any(t in ct for t in ["mpegurl", "application/vnd.apple.mpegurl"]):
            set_found_link(url, res.request.headers.get("referer", referer))
            return

        if any(t in ct for t in ["json", "javascript", "text/plain"]):
            try:
                text = await res.text()
                if ".m3u8" in text:
                    matches = re.findall(r'(https?://[^\s"\'<>\\]+?\.m3u8[^\s"\'<>\\]*)', text)
                    if matches:
                        set_found_link(matches[0], res.request.headers.get("referer", referer))
            except Exception:
                pass

    page.on("response", handle_response)
    page.on("request", lambda req: set_found_link(req.url, req.headers.get("referer", referer)) if ".m3u8" in req.url.split("?")[0].lower() else None)

    try:
        timeout_limit = 25000 if attempt == 1 else 30000
        print(f"[*] Sayfa yükleniyor: {channel['name']}")
        
        # Sayfaya git
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_limit)
        await asyncio.sleep(2.0)

        # 1. ADIM: "Servers" Sekmesini Aktifleştir
        await page.evaluate("""
            () => {
                const elements = Array.from(document.querySelectorAll('button, a, div, li, span'));
                const srvTab = elements.find(el => {
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    return txt === 'servers' || txt === 'server' || txt === 'sunucular';
                });
                if (srvTab) srvTab.click();
            }
        """)
        await asyncio.sleep(1.5)

        # 2. ADIM: Sayfadaki Aktif Sunucuları Tespit Et
        active_server_names = await page.evaluate("""
            () => {
                const keywords = ["AUTO", "EARTH", "MERCURY", "VENUS", "MARS", "JUPITER", "SATURN", "SERVER"];
                const candidates = Array.from(document.querySelectorAll('button, a, div[role="button"], li, .server-btn, [class*="server"]'));
                const list = [];
                
                candidates.forEach(el => {
                    const txt = (el.innerText || el.textContent || "").trim().toUpperCase();
                    if (keywords.some(k => txt.includes(k))) {
                        if (!txt.includes("OFFLINE") && !txt.includes("DISABLED") && !el.disabled) {
                            list.push(txt.split('\\n')[0].trim());
                        }
                    }
                });
                return [...new Set(list)];
            }
        """)

        # Auto veya Earth sunucusunu öne al
        active_server_names.sort(key=lambda x: 0 if "AUTO" in x else (1 if "EARTH" in x else 2))
        print(f"  [*] Tespit edilen aktif sunucu sayısı: {len(active_server_names)}")

        # 3. ADIM: Sırayla Sunuculara Tıkla ve Video Başlat
        for srv_name in active_server_names:
            if link_found_event.is_set():
                break

            short_name = srv_name.split()[0]
            print(f"  [>] Aktif sunucu deneniyor: {short_name}")
            
            # Sunucu butonuna JavaScript ile tıkla
            await page.evaluate("""
                (name) => {
                    const candidates = Array.from(document.querySelectorAll('button, a, div[role="button"], li, .server-btn, [class*="server"]'));
                    for (const el of candidates) {
                        const txt = (el.innerText || el.textContent || "").trim().toUpperCase();
                        if (txt.includes(name) && !txt.includes("OFFLINE")) {
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            el.click();
                            break;
                        }
                    }
                }
            """, srv_name)

            await asyncio.sleep(2.0)

            # Video Oynatıcıyı ve Frame'leri Oynatmaya Zorla
            for frame in page.frames:
                try:
                    await frame.evaluate("""
                        () => {
                            document.querySelectorAll('video').forEach(v => {
                                v.muted = true;
                                v.play().catch(e => {});
                            });
                            const selectors = ['.jw-display-icon-container', '.vjs-big-play-button', 'button[aria-label="Play"]', '.play-btn'];
                            selectors.forEach(sel => {
                                const btn = document.querySelector(sel);
                                if (btn) btn.click();
                            });
                        }
                    """)
                except Exception:
                    pass

            # Linkin yakalanması için bekle
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=4.5)
            except asyncio.TimeoutError:
                pass

        # 4. ADIM: Frame İçeriklerinde Regex Kontrolü (Yayın doğrudan frame'deyse)
        if not link_found_event.is_set():
            for frame in page.frames:
                try:
                    content = await frame.content()
                    matches = re.findall(r'["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', content)
                    if matches:
                        set_found_link(matches[0], frame.url)
                        break
                except Exception:
                    continue

    except Exception as e:
        if attempt == (MAX_RETRIES + 1):
            print(f"  [-] Link bulunamadı: {channel['name']}")
    finally:
        await page.close()

    if found_link:
        print(f"  [+] BAŞARILI: {channel['name']} -> Link yakalandı!")
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
            viewport={"width": 1280, "height": 720},
            bypass_csp=True,
            ignore_https_errors=True
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
