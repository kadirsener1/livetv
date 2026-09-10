#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

# ─── KANAL LİSTESİ ────────────────────────────────────────────────────────────
KANAL_SABLONLARI = [
    {
        "name": "BBC News Channel HD",
        "path": "/live/349?name=BBC%20News%20Channel%20HD&tab=channels",
        "group": "UK"
    },
    # İstediğiniz diğer kanalları buraya ekleyebilirsiniz:
    # {"name": "Kanal Adi", "path": "/live/...", "group": "TR"},
]

SEED_DOMAINS = [
    "https://opstream.fun"
]

# Taranacak Sunucu / Gezegen İsimleri
SERVERS_TO_SCAN = ["Auto", "Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn"]

# ─── AYARLAR ──────────────────────────────────────────────────────────────────
OUTPUT_DIR_NAME = "opstream_output"
DEBUG_FILE = "debug_failed.json"
MAX_CONCURRENT = 1              # Kararlılık için 1 sekme
PAGE_TIMEOUT = 35000            # Sayfa yüklenme zaman aşımı (35 sn)
SERVER_SCAN_TIMEOUT = 10.0      # Her sunucu için bekleme süresi (10 sn)

# ──────────────────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.replace(" ", "_").strip()


def is_stream_url(url: str) -> bool:
    """URL'nin geçerli bir m3u8 veya video akışı olup olmadığını doğrular."""
    if not url:
        return False
    url_low = url.lower().split("?")[0]
    
    # Canlı yayın akış uzantıları
    valid_exts = [".m3u8", ".mpd", "manifest", "playlist", "master", "index"]
    if any(ext in url_low for ext in valid_exts):
        # Sahte veya analiz isteklerini hariç tut
        if not any(ad in url_low for ad in ["google", "analytics", "stat", "logger", "tracker", "beacon"]):
            return True
    return False


async def discover_active_domain() -> str:
    print("🔍 Aktif alan adı sorgulanıyor...")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        active_domain = SEED_DOMAINS[0]
        
        for seed in SEED_DOMAINS:
            try:
                resp = await page.goto(seed, timeout=15000, wait_until="commit")
                if resp and resp.status < 400:
                    match = re.match(r'(https?://[^/]+)', page.url)
                    if match:
                        active_domain = match.group(1)
                        print(f"🎯 Aktif Domain: {active_domain}")
                        break
            except Exception:
                continue
                
        await browser.close()
        return active_domain


async def force_play_player(page):
    """Hem ana sayfadaki hem iframe'lerdeki playerları oynatmaya zorlar."""
    for frame in page.frames:
        try:
            await frame.evaluate("""() => {
                // Tüm video etiketlerini oynat
                document.querySelectorAll('video').forEach(v => {
                    v.muted = true;
                    v.play().catch(()=>{});
                });

                // Bulunabilecek tüm play/unmute butonlarına tıkla
                const selectors = [
                    '.vjs-big-play-button', '.jw-display-icon-container', 
                    '.play-icon', '#player', 'button[class*="play" i]', 
                    '.plyr__control--overlaid', '#play-btn', '.clappr-play-button'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(b => b.click());
                });
            }""")
        except Exception:
            pass


async def click_server_button(page, server_name: str) -> bool:
    """Sayfadaki gezegen/server butonunu bulup tıklar."""
    for frame in page.frames:
        try:
            clicked = await frame.evaluate("""(srv) => {
                const elements = Array.from(document.querySelectorAll('button, a, div, span, li'));
                for (let el of elements) {
                    const txt = (el.innerText || el.textContent || "").trim();
                    
                    // Tam olarak sunucu ismini içeriyor mu? (Örn: Saturn veya Mercury)
                    const regex = new RegExp('^' + srv + '($|\\\\s|OFFLINE)', 'i');
                    if (regex.test(txt) && el.offsetWidth > 0 && el.offsetHeight > 0) {
                        if (txt.toUpperCase().includes('OFFLINE')) {
                            return "OFFLINE";
                        }
                        el.click();
                        return "CLICKED";
                    }
                }
                return "NOT_FOUND";
            }""", server_name)

            if clicked == "CLICKED":
                return True
            elif clicked == "OFFLINE":
                return False
        except Exception:
            pass
    return False


async def get_channel_streams(browser, channel_url: str) -> dict:
    found_streams = {}
    current_target = "Auto"
    server_found_event = asyncio.Event()

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
        ignore_https_errors=True,
    )

    page = await context.new_page()

    # Anti-Bot bypass
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)

    # Ağ isteklerini ve yanıtlarını dinle
    async def intercept_response(response):
        nonlocal current_target
        try:
            url = response.url
            ct = response.headers.get("content-type", "").lower()
            
            # M3U8, MPD veya mpegurl içeriklerini yakala
            if is_stream_url(url) or "mpegurl" in ct or "application/vnd.apple.mpegurl" in ct:
                if current_target not in found_streams:
                    if url not in found_streams.values():
                        found_streams[current_target] = url
                        server_found_event.set()
        except Exception:
            pass

    page.on("response", intercept_response)

    try:
        # Sayfayı aç
        await page.goto(channel_url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        await asyncio.sleep(4.0)  # İframe ve player JS'lerinin yüklenmesi için başlangıç beklemesi

        for srv in SERVERS_TO_SCAN:
            current_target = srv
            server_found_event.clear()

            is_active_btn = True
            if srv != "Auto":
                is_active_btn = await click_server_button(page, srv)
                await asyncio.sleep(2.0)

            # Eğer buton offline değilse yayını tetiklemeyi dene
            if is_active_btn:
                await force_play_player(page)
                try:
                    await asyncio.wait_for(server_found_event.wait(), timeout=SERVER_SCAN_TIMEOUT)
                except asyncio.TimeoutError:
                    pass

    except Exception as e:
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

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--mute-audio"
            ]
        )

        for idx, ch in enumerate(channels, 1):
            name = ch["name"]
            group = ch.get("group", "GENEL")
            url = f"{active_domain}{ch['path']}"
            prefix = f"[{idx:02d}/{total}]"

            async with semaphore:
                streams = await get_channel_streams(browser, url)

            if streams:
                log_txt = []
                for srv_name, stream_url in streams.items():
                    log_txt.append(f"{srv_name} ✅")
                    success.append({
                        "channel_name": name,
                        "file_name": f"{sanitize_filename(name)}_{srv_name}",
                        "group": group,
                        "server": srv_name,
                        "stream_url": stream_url
                    })
                print(f"  ✅ {prefix} {name} → {' | '.join(log_txt)}")
            else:
                print(f"  ❌ {prefix} {name} → Yayın bulunamadı (Sunucular deneniyor veya yayın kapalı).")
                failed.append({"name": name, "page_url": url})

        await browser.close()

    return success, failed


def save_output(items: list, output_dir: str):
    base_path = Path(__file__).parent.resolve()
    target_dir = base_path / output_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 Dosyalar Kaydediliyor: {target_dir}")

    # 1. Tekil m3u8 dosyaları
    for ch in items:
        file_path = target_dir / f"{ch['file_name']}.m3u8"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                f.write("#EXT-X-VERSION:3\n")
                f.write(f"#EXTINF:-1 group-title=\"{ch['group']}\",{ch['channel_name']} ({ch['server']})\n")
                f.write(f"{ch['stream_url']}\n")
            print(f"   💾 Kaydedildi: {file_path.name}")
        except Exception as e:
            print(f"   ❌ Hata ({file_path.name}): {e}")

    # 2. Toplu m3u listesi
    if items:
        playlist_file = target_dir / "tum_kanallar.m3u"
        with open(playlist_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in items:
                f.write(f'#EXTINF:-1 group-title="{ch["group"]}",{ch["channel_name"]} ({ch["server"]})\n')
                f.write(f"{ch['stream_url']}\n")
        print(f"\n   🌟 Toplu Playlist Oluşturuldu: {playlist_file.name}")


async def main():
    print("=" * 65)
    print("   📺 OPSTREAM.FUN GELİŞMİŞ YAYIN YAKALAYICI")
    print("=" * 65 + "\n")

    active_domain = await discover_active_domain()
    print(f"🔗 Aktif Adres: {active_domain}\n")

    success, failed = await process_all(KANAL_SABLONLARI, active_domain)

    save_output(success, OUTPUT_DIR_NAME)

    with open(DEBUG_FILE, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 65}")
    print(f"📊 ÖZET RAPOR:")
    print(f"  Toplam Yakalanan Yayın: {len(success)}")
    print(f"  Başarısız Kanal Sayısı: {len(failed)}")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    asyncio.run(main())
