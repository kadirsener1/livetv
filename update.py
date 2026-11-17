import asyncio
import os
import re
import requests
from playwright.async_api import async_playwright

OUTPUT_FILE = "playlist.m3u"
API_URL = "https://tflix-document-channels.cloudvix001.workers.dev/api/channels"
CONCURRENCY_LIMIT = 4

def fetch_channels_from_api():
    try:
        print("API'den kanal listesi alınıyor...")
        response = requests.get(API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            channels = []
            items = data if isinstance(data, list) else data.get("channels", data.get("data", []))
            
            for item in items:
                region = str(item.get("region", "")).lower()
                region_name = str(item.get("regionName", "")).lower()
                
                if "turkey" in region or "turkey" in region_name or "türkiye" in region_name:
                    raw_name = item.get("name") or item.get("title")
                    path = item.get("path") or item.get("url") or item.get("code")
                    logo = item.get("logo", "")
                    
                    if raw_name and path:
                        # "TR" ifadesini temizle
                        clean_name = re.sub(r'\bTR\b', '', raw_name, flags=re.IGNORECASE).strip()
                        clean_name = re.sub(r'\s+', ' ', clean_name)
                        
                        if not clean_name.endswith("-BS"):
                            clean_name = f"{clean_name}-BS"
                            
                        channels.append({"name": clean_name, "url": path, "logo": logo})
                        
            print(f"API'den toplam {len(channels)} Türkiye kanalı filtrelendi.")
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

    # --- AKILLI DOSYA TEMİZLEME VE GÜNCELLEME ---
    # Mevcut m3u dosyasını oku (yoksa boş başlat)
    existing_lines = []
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    # Dosya hiç yoksa başlığı koy
    if not existing_lines:
        existing_lines = ["#EXTM3U\n"]

    # Yeni taranan/başarılı olan kanalları dosyadan tamamen siliyoruz (eski bozuk/silinmiş linkler kirlilik yapmasın diye)
    cleaned_lines = []
    skip_lines = 0
    i = 0
    while i < len(existing_lines):
        line = existing_lines[i]
        
        # Eğer satır bir kanal tanımı (#EXTINF) içeriyorsa ve güncellenen kanallarımızdan biriyse
        matched_ch = None
        for ch_name in updated_links.keys():
            if f'tvg-name="{ch_name}"' in line or line.strip().endswith(f",{ch_name}"):
                matched_ch = ch_name
                break
                
        if matched_ch:
            # Bu kanalın kendisine ait alt satırları (VLC opsiyonları ve m3u8 linki) atla
            i += 1
            while i < len(existing_lines) and (existing_lines[i].strip().startswith("#") or not existing_lines[i].strip().startswith("#EXTINF")):
                # Eğer yeni bir #EXTINF görmediysek ve önceki kanalın link satırındaysak atlamaya devam et
                if existing_lines[i].strip().startswith("#EXTINF") or existing_lines[i].strip() == "":
                    break
                # Eğer link satırı veya vlc opt satırı ise atla
                i += 1
            # Fazladan boşluk kalmaması için kontrol
            continue
        else:
            cleaned_lines.append(line)
            i += 1

    # Dosyanın en sonuna güncel ve taze linkleri ekle
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(cleaned_lines)
        
        # Eğer dosya sonunda yeni satır yoksa ekle
        if cleaned_lines and not cleaned_lines[-1].endswith("\n"):
            f.write("\n")

        # Yeni/güncellenmiş çalışan linkleri ekle
        for ch_name, data in updated_links.items():
            logo_attr = f' tvg-logo="{data["logo"]}"' if data["logo"] else ''
            f.write(f'\n#EXTINF:-1 tvg-name="{ch_name}"{logo_attr} group-title="Spor-BS",{ch_name}\n')
            f.write("#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\n")
            f.write("#EXTVLCOPT:network-caching=5000\n")
            f.write("#EXTVLCOPT:live-caching=5000\n")
            f.write(f"{data['link']}\n")
    
    print(f"\nİşlem tamam! {OUTPUT_FILE} dosyası güncel ve çalışan linklerle tamamen yenilendi.")

if __name__ == "__main__":
    asyncio.run(main())
