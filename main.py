#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

# ─── KANAL LİSTESİ (OPSTREAM UYUMLU) ──────────────────────────────────────────
KANAL_SABLONLARI = [
    {"name": "opstream_349", "path": "/live/349", "group": "TR"},
    # Buraya diğer kanallarınızı ekleyebilirsiniz:
    # {"name": "kanal_adi", "path": "/live/kanal-id", "group": "TR"},
]

SEED_DOMAINS = [
    "https://opstream.fun"
]

# ─── GEZEGEN/SERVER LİSTESİ ───────────────────────────────────────────────────
SERVERS_TO_SCAN = ["Auto", "Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn"]

# ─── SİSTEM AYARLARI ──────────────────────────────────────────────────────────
OUTPUT_DIR_NAME = "opstream_streams"
DEBUG_FILE = "debug_failed.json"
MAX_CONCURRENT = 1              # Kararlılık için opstream'de eşzamanlı sekme sayısı 1-2 olmalıdır
PAGE_TIMEOUT = 25000            # Sayfa ilk yükleme zaman aşımı (25 sn)
SERVER_SCAN_TIMEOUT = 7.0       # Her bir planet server için bekleme süresi (7 sn)

# Reklam engelleyici
AD_BLOCK_LIST = [
    "google-analytics", "doubleclick", "adservice", "popads", "popcash",
    "histats", "adsterra", "exoclick", "onclickads", "propush", "monetag",
    "mgid", "yandex", "facebook", "twitter", "analytics", "adskeeper",
    "vidoomy", "ezodn", "witnessonmy", "adnxs", "jads", "banner"
]
BLOCKED_RESOURCES = {"image", "font"}

# ──────────────────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def is_valid_m3u8(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url_low = url.lower().split("?")[0]
    if any(ad in url_low for ad in AD_BLOCK_LIST):
        return False
    if url_low.endswith(".m3u8") or ".m3u8" in url_low or url_low.endswith(".mpd") or ".mpd" in url_low:
        return True
    return False


async def discover_active_domain() -> str:
    print("🔍 Aktif alan adı (domain) sorgulanıyor...")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        active_domain = ""
        for seed in SEED_DOMAINS:
            try:
                response = await page.goto(seed, timeout=12000, wait_until="commit")
                if response and response.status < 400:
                    final_url = page.url
                    match = re.match(r'(https?://[^/]+)', final_url)
                    if match:
                        active_domain = match.group(1)
                        print(f"🎯 Güncel Aktif Domain Tespit Edildi: {active_domain}")
                        break
            except Exception:
                continue
        
        await browser.close()
        if not active_domain:
            active_domain = SEED_DOMAINS[0]
            print(f"⚠️ Aktif domain tespit edilemedi! Varsayılan kullanılıyor: {active_domain}")
        return active_domain


async def try_trigger_play(page):
    """Video oynatıcısını programatik olarak sessize alıp oynatır."""
    try:
        await page.mouse.click(512, 384)
    except Exception:
        pass

    for frame in page.frames:
        try:
            await frame.evaluate("""() => {
                document.querySelectorAll('video').forEach(v => {
                    v.muted = true;
                    v.play().catch(()=>{});
                });
                const btns = document.querySelectorAll(
                    '.vjs-big-play-button, .jw-display-icon-container, .play-icon, #player, button[class*="play" i]'
                );
                btns.forEach(btn => btn.click());
            }""")
        except Exception:
            pass


async def switch_server_on_page(page, server_name: str) -> bool:
    """Sayfadaki Gezegen isimli butonlara (Mercury, Venus vb.) tıklar."""
    switched = False
    for frame in page.frames:
        try:
            success = await frame.evaluate("""(name) => {
                const elements = Array.from(document.querySelectorAll('button, a, div, li, span, h1, h2, h3'));
                // Case-insensitive olarak gezegen ismini ara (Örn: "Mercury" veya "MercuryOFFLINE")
                const rx = new RegExp(name, 'i');
                
                for (let el of elements) {
                    const text = (el.innerText || el.textContent || "").trim();
                    if (rx.test(text) && el.offsetWidth > 0 && el.offsetHeight > 0) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""", server_name)
            if success:
                switched = True
                break
        except Exception:
            pass
            
    return switched


async def get_channel_all_servers(browser, page_url: str) -> dict:
    """Belirtilen gezegen sunucularını sırayla gezerek aktif yayınları yakalar."""
    found_streams = {} # {"Auto": "...", "Saturn": "..."}
    
    current_server_target = "Auto"
    server_event = asyncio.Event()

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )

    page = await context.new_page()
    page.on("popup", lambda p: asyncio.create_task(p.close()))

    async def route_filter(route):
        req = route.request
        url_low = req.url.lower()
        if is_valid_m3u8(req.url):
            await route.continue_()
            return
        if any(ad in url_low for ad in AD_BLOCK_LIST) or req.resource_type in BLOCKED_RESOURCES:
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", route_filter)

    async def handle_response(response):
        nonlocal current_server_target
        url = response.url
        
        if not is_valid_m3u8(url):
            ct = response.headers.get("content-type", "").lower()
            if not ("mpegurl" in ct or "application/x-mpegurl" in ct or "dash" in ct or "video" in ct):
                return

        # Eğer bu sunucu için henüz link yakalanmadıysa kaydet
        if current_server_target not in found_streams:
            # Aynı linkin tekrar yakalanmasını önle (Farklı serverlar aynı linki üretiyor olabilir)
            if url not in found_streams.values():
                found_streams[current_server_target] = url
                server_event.set()

    page.on("response", handle_response)

    try:
        # Sayfayı aç
        await page.goto(page_url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)

        # Her bir sunucu (Gezegen) için tarama yap
        for server in SERVERS_TO_SCAN:
            current_server_target = server
            server_event.clear()
            
            # "Auto" haricindekilere tıklayarak geçiş yap
            switched = True
            if server != "Auto":
                switched = await switch_server_on_page(page, server)
                await asyncio.sleep(1.5)

            if switched:
                await try_trigger_play(page)
                try:
                    # Yayın linkinin gelmesini bekle
                    await asyncio.wait_for(server_event.wait(), timeout=SERVER_SCAN_TIMEOUT)
                except asyncio.TimeoutError:
                    pass # Timeout olursa (yayın offline ise) sonraki sunucuya geç

    except Exception:
        pass
    finally:
        await page.close()
        await context.close()

    return found_streams


async def process_all(channels: list, active_domain: str) -> tuple:
    success = []
    failed = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(channels)
    done_count = 0
    lock = asyncio.Lock()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--mute-audio"
            ]
        )

        async def handle(ch):
            nonlocal done_count
            name = ch["name"]
            url = f"{active_domain}{ch['path']}"

            async with semaphore:
                streams_dict = await get_channel_all_servers(browser, url)

            async with lock:
                done_count += 1
                prefix = f"[{done_count:02d}/{total}]"

                if streams_dict:
                    log_text = []
                    for server_name, stream_url in streams_dict.items():
                        log_text.append(f"{server_name} ✅")
                        # Her aktif sunucuyu kanaladi_sunucuadi formatında kaydet
                        success.append({
                            "name": f"{name}_{server_name}",
                            "stream_url": stream_url,
                            "server": server_name
                        })
                    print(f"  ✅ {prefix} {name} → {' | '.join(log_text)}")
                else:
                    print(f"  ❌ {prefix} {name} → Hiçbir gezegen sunucusunda aktif yayın bulunamadı.")
                    failed.append({"name": name, "page_url": url})

        await asyncio.gather(*[handle(ch) for ch in channels], return_exceptions=True)
        await browser.close()

    return success, failed


def write_to_m3u8_files(items: list, output_dir: str):
    """Her sunucu kaynağını ayrı .m3u8 dosyası olarak kaydeder."""
    base_path = Path(__file__).parent.resolve()
    target_dir = base_path / output_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 Kaydetme İşlemi Başlatıldı ({target_dir})")

    for ch in items:
        safe_name = sanitize_filename(ch["name"])
        file_path = target_dir / f"{safe_name}.m3u8"
        stream_link = ch["stream_url"]

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                f.write("#EXT-X-VERSION:3\n")
                f.write("#EXT-X-STREAM-INF:BANDWIDTH=8000000\n")
                f.write(f"{stream_link}\n")
            print(f"   💾 Yazıldı: {file_path.name}")
        except Exception as e:
            print(f"   ❌ Dosya Hatası ({safe_name}): {e}")


async def main():
    print("=" * 65)
    print("   📺 OPSTREAM - GEZEGEN SUNUCULARI YAYIN YAKALAYICI")
    print("=" * 65 + "\n")

    active_domain = await discover_active_domain()
    print(f"🔗 Kullanılacak Aktif Yayın Kaynağı: {active_domain}\n")

    success, failed = await process_all(KANAL_SABLONLARI, active_domain)

    write_to_m3u8_files(success, OUTPUT_DIR_NAME)

    with open(DEBUG_FILE, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 65}")
    print(f"📊 ÖZET RAPOR:")
    print(f"  Aktif Domain         : {active_domain}")
    print(f"  Taranan Kanal Sayısı : {len(KANAL_SABLONLARI)}")
    print(f"  Oluşturulan M3U8     : {len(success)} adet dosya")
    print(f"  Başarısız Kanallar   : {len(failed)}")
    print(f"  Klasör Yolu          : ./{OUTPUT_DIR_NAME}/")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    asyncio.run(main())
