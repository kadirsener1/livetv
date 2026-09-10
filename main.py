#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import asyncio
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright

# ─── KANAL LİSTESİ ────────────────────────────────────────────────────────────
# İstediğiniz diğer Opstream kanallarını bu listeye ekleyebilirsiniz.
KANAL_SABLONLARI = [
    {
        "name": "BBC News Channel HD",
        "path": "/live/349?name=BBC%20News%20Channel%20HD&tab=channels",
        "group": "UK"
    },
    # Örnek ilave kanal formatı:
    # {"name": "Sky Sports Main Event", "path": "/live/123?name=Sky%20Sports&tab=channels", "group": "UK"},
]

SEED_DOMAINS = [
    "https://opstream.fun"
]

# Taranacak Gezegen Sunucuları
SERVERS_TO_SCAN = ["Auto", "Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn"]

# ─── SİSTEM AYARLARI ──────────────────────────────────────────────────────────
OUTPUT_DIR_NAME = "opstream_output"
DEBUG_FILE = "debug_failed.json"
MAX_CONCURRENT = 1              # Kararlılık için 1 önerilir
PAGE_TIMEOUT = 30000            # Sayfa ilk yükleme aşımı (30 sn)
SERVER_SCAN_TIMEOUT = 6.0       # Her bir sunucu için yayın bekleme süresi (6 sn)

# Reklam engelleyici listesi
AD_BLOCK_LIST = [
    "google-analytics", "doubleclick", "adservice", "popads", "popcash",
    "histats", "adsterra", "exoclick", "onclickads", "propush", "monetag",
    "mgid", "yandex", "facebook", "twitter", "analytics", "adskeeper",
    "vidoomy", "ezodn", "witnessonmy", "adnxs", "jads", "banner"
]
BLOCKED_RESOURCES = {"image", "font"}

# ──────────────────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Dosya adlarını geçersiz karakterlerden temizler."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.replace(" ", "_").strip()


def is_valid_m3u8(url: str) -> bool:
    """Gelen isteğin geçerli bir m3u8 veya mpd video linki olup olmadığını denetler."""
    if not url or not isinstance(url, str):
        return False
    url_low = url.lower().split("?")[0]
    if any(ad in url_low for ad in AD_BLOCK_LIST):
        return False
    if url_low.endswith(".m3u8") or ".m3u8" in url_low or url_low.endswith(".mpd") or ".mpd" in url_low:
        return True
    return False


async def discover_active_domain() -> str:
    print("🔍 Aktif Opstream domaini sorgulanıyor...")
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
                        print(f"🎯 Aktif Domain Tespit Edildi: {active_domain}")
                        break
            except Exception:
                continue
        
        await browser.close()
        if not active_domain:
            active_domain = SEED_DOMAINS[0]
            print(f"⚠️ Varsayılan domain kullanılıyor: {active_domain}")
        return active_domain


async def try_trigger_play(page):
    """Player içindeki gizli oynat butonlarını tetikler."""
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
                    '.vjs-big-play-button, .jw-display-icon-container, .play-icon, #player, button[class*="play" i], .plyr__control--overlaid'
                );
                btns.forEach(btn => btn.click());
            }""")
        except Exception:
            pass


async def switch_server_on_page(page, server_name: str) -> bool:
    """
    Sunucu butonunu bulur. 
    Eğer buton 'OFFLINE' olarak işaretlenmişse tıklamayı atlayarak zaman kazanır.
    """
    switched = False
    for frame in page.frames:
        try:
            result = await frame.evaluate("""(name) => {
                const elements = Array.from(document.querySelectorAll('button, a, div, li, span'));
                const rx = new RegExp('^\\\\s*' + name, 'i');
                
                for (let el of elements) {
                    const text = (el.innerText || el.textContent || "").trim();
                    if (rx.test(text) && el.offsetWidth > 0 && el.offsetHeight > 0) {
                        // Eğer OFFLINE yazıyorsa tıklama
                        if (text.toUpperCase().includes("OFFLINE")) {
                            return "OFFLINE";
                        }
                        el.click();
                        return "CLICKED";
                    }
                }
                return "NOT_FOUND";
            }""", server_name)
            
            if result == "CLICKED":
                return True
            elif result == "OFFLINE":
                return False
        except Exception:
            pass
            
    return switched


async def get_channel_all_servers(browser, page_url: str) -> dict:
    """Tüm sunucuları gezerek canlı .m3u8 akış linklerini yakalar."""
    found_streams = {}
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
            if not ("mpegurl" in ct or "application/x-mpegurl" in ct or "video" in ct):
                return

        if current_server_target not in found_streams:
            if url not in found_streams.values():
                found_streams[current_server_target] = url
                server_event.set()

    page.on("response", handle_response)

    try:
        await page.goto(page_url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)

        for server in SERVERS_TO_SCAN:
            current_server_target = server
            server_event.clear()
            
            switched = True
            if server != "Auto":
                switched = await switch_server_on_page(page, server)
                await asyncio.sleep(1.5)

            if switched:
                await try_trigger_play(page)
                try:
                    await asyncio.wait_for(server_event.wait(), timeout=SERVER_SCAN_TIMEOUT)
                except asyncio.TimeoutError:
                    pass

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
            group = ch.get("group", "GENEL")
            url = f"{active_domain}{ch['path']}"

            async with semaphore:
                streams_dict = await get_channel_all_servers(browser, url)

            async with lock:
                done_count += 1
                prefix = f"[{done_count:02d}/{total}]"

                if streams_dict:
                    log_text = []
                    for s_name, s_url in streams_dict.items():
                        log_text.append(f"{s_name} ✅")
                        success.append({
                            "channel_name": name,
                            "file_name": f"{sanitize_filename(name)}_{s_name}",
                            "group": group,
                            "server": s_name,
                            "stream_url": s_url
                        })
                    print(f"  ✅ {prefix} {name} → {' | '.join(log_text)}")
                else:
                    print(f"  ❌ {prefix} {name} → Hiçbir aktif sunucu linki yakalanamadı.")
                    failed.append({"name": name, "page_url": url})

        await asyncio.gather(*[handle(ch) for ch in channels], return_exceptions=True)
        await browser.close()

    return success, failed


def save_playlists(items: list, output_dir: str):
    """
    1. Her sunucu için ayrı .m3u8 dosyası üretir.
    2. Tüm kanalları tek bir tum_kanallar.m3u dosyasına toplar.
    """
    base_path = Path(__file__).parent.resolve()
    target_dir = base_path / output_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 Kaydetme Başlatıldı: {target_dir}")

    # 1. Tekil Dosyalar
    for ch in items:
        file_path = target_dir / f"{ch['file_name']}.m3u8"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                f.write("#EXT-X-VERSION:3\n")
                f.write(f"#EXTINF:-1 group-title=\"{ch['group']}\",{ch['channel_name']} ({ch['server']})\n")
                f.write(f"{ch['stream_url']}\n")
            print(f"   💾 Yazıldı: {file_path.name}")
        except Exception as e:
            print(f"   ❌ Hata ({file_path.name}): {e}")

    # 2. Toplu M3U Dosyası (IPTV Oynatıcıları İçin)
    all_playlist_path = target_dir / "tum_kanallar.m3u"
    try:
        with open(all_playlist_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in items:
                f.write(f'#EXTINF:-1 group-title="{ch["group"]}",{ch["channel_name"]} ({ch["server"]})\n')
                f.write(f"{ch['stream_url']}\n")
        print(f"\n   🌟 Toplu Playlist Oluşturuldu: {all_playlist_path.name}")
    except Exception as e:
        print(f"   ❌ Toplu dosya hatası: {e}")


async def main():
    print("=" * 65)
    print("   📺 OPSTREAM.FUN - YAYIN VE SUNUCU YAKALAYICI")
    print("=" * 65 + "\n")

    active_domain = await discover_active_domain()
    print(f"🔗 Aktif Adres: {active_domain}\n")

    success, failed = await process_all(KANAL_SABLONLARI, active_domain)

    save_playlists(success, OUTPUT_DIR_NAME)

    with open(DEBUG_FILE, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 65}")
    print(f"📊 ÖZET RAPOR:")
    print(f"  Taranan Kanal Sayısı  : {len(KANAL_SABLONLARI)}")
    print(f"  Yakalanan Yayın Sayısı: {len(success)}")
    print(f"  Başarısız Sayısı      : {len(failed)}")
    print(f"  Kayıt Klasörü         : ./{OUTPUT_DIR_NAME}/")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    asyncio.run(main())
