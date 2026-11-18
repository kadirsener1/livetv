import asyncio
import os
import re
import requests
from playwright.async_api import async_playwright

OUTPUT_FILE = "tv247tr.m3u"
BOSS_DIR = "boss"
API_URL = "https://tflix-document-channels.cloudvix001.workers.dev/api/channels"
CONCURRENCY_LIMIT = 4  # Aynı anda taranacak kanal sayısı

def fetch_channels_from_api():
    try:
        print("API'den kanal listesi alınıyor...")
        response = requests.get(API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            channels = []
            items = data if isinstance(data, list) else data.get("channels", data.get("data", []))
            
            for item in items:
                # Sadece Turkey (Türkiye) bölgesine ait kanalları filtrele
                region = str(item.get("region", "")).lower()
                region_name = str(item.get("regionName", "")).lower()
                
                if "turkey" in region or "turkey" in region_name or "türkiye" in region_name:
                    name = item.get("name") or item.get("title")
                    path = item.get("path") or item.get("url") or item.get("code")
                    logo = item.get("logo", "")
                    
                    if name and path:
                        channels.append({"name": name, "url": path, "logo": logo})
                        
            print(f"API'den toplam {len(channels)} Türkiye kanalı başarıyla filtrelendi.")
            return channels
    except Exception as e:
        print(f"API'den kanal listesi alınırken hata oluştu: {e}")
    return []

async def get_stream_url(browser, ch):
    page = await browser.new_page()
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and not stream_url:
            stream_url = request.url

    page.on("request", handle_request)

    try:
        print(f"Taranıyor: {ch['name']} ({ch['url']})")
        await page.goto(ch['url'], timeout=45000)
        await page.wait_for_timeout(5000)
    except Exception as e:
        print(f"Yükleme hatası ({ch['name']}): {e}")

    await page.close()
    return ch['name'], ch['logo'], stream_url

async def main():
    channels_to_update = fetch_channels_from_api()
    if not channels_to_update:
        print("Taranacak Türkiye kanalı bulunamadı!")
        return

    updated_links = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def sem_task(ch):
            async with semaphore:
                return await get_stream_url(browser, ch)

        tasks = [sem_task(ch) for ch in channels_to_update]
        results = await asyncio.gather(*tasks)

        for name, logo, link in results:
            if link:
                print(f" Başarılı! {name} linki alındı.")
                updated_links[name] = {"link": link, "logo": logo}
            else:
                print(f" {name} için link alınamadı.")

        await browser.close()

    # 'boss' klasörünü oluştur (yoksa)
    os.makedirs(BOSS_DIR, exist_ok=True)

    # Dosya güncelleme adımı
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        matched_channel = None
        for ch_name in updated_links.keys():
            if ch_name in line:
                matched_channel = ch_name
                break

        if matched_channel:
            new_lines.append(line)
            i += 1
            while i < len(lines) and lines[i].strip().startswith("#"):
                new_lines.append(lines[i])
                i += 1
            if i < len(lines):
                new_lines.append(f"{updated_links[matched_channel]['link']}\n")
                i += 1
        else:
            new_lines.append(line)
            i += 1

    existing_content = "".join(new_lines)
    for ch_name, data in updated_links.items():
        logo_attr = f' tvg-logo="{data["logo"]}"' if data["logo"] else ''
        
        # Her kanal için 'boss' klasörüne .m3u8 dosyası olarak Tivimate uyumlu formatta kaydetme
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", ch_name) + ".m3u8"
        channel_file_path = os.path.join(BOSS_DIR, safe_filename)
        with open(channel_file_path, "w", encoding="utf-8") as cf:
            cf.write("#EXTM3U\n")
            cf.write(f'#EXTINF:-1 tvg-name="{ch_name}"{logo_attr} group-title="Spor-BS",{ch_name}\n')
            cf.write("#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\n")
            cf.write("#EXTVLCOPT:network-caching=5000\n")
            cf.write("#EXTVLCOPT:live-caching=5000\n")
            cf.write(f"{data['link']}\n")

        if ch_name not in existing_content:
            new_lines.append(f'\n#EXTINF:-1 tvg-name="{ch_name}"{logo_attr} group-title="Spor-BS",{ch_name}\n')
            new_lines.append("#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\n")
            new_lines.append("#EXTVLCOPT:network-caching=5000\n")
            new_lines.append("#EXTVLCOPT:live-caching=5000\n")
            new_lines.append(f"{data['link']}\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    print(f"\nİşlem tamam! Ana liste ve 'boss' klasöründeki .m3u8 dosyaları Tivimate uyumlu formatla güncellendi.")

if __name__ == "__main__":
    asyncio.run(main())
