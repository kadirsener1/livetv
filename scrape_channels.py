import asyncio
import os
import requests
from playwright.async_api import async_playwright

OUTPUT_FILE = "playlist.m3u"  # Çıktının yazılacağı dosya adı güncellendi
API_URL = "https://tflix-document-channels.cloudvix001.workers.dev/api/channels"
PROXY_PREFIX = "https://avva.magnitude.workers.dev/?url="

def fetch_channels_from_api():
    try:
        print("API'den kanal listesi alınıyor...")
        response = requests.get(API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            channels = []
            items = data if isinstance(data, list) else data.get("channels", data.get("data", []))
            for item in items:
                name = item.get("name") or item.get("title")
                path = item.get("path") or item.get("url") or item.get("code")
                if name and path:
                    channels.append({"name": name, "url": path})
            print(f"API'den toplam {len(channels)} kanal başarıyla çekildi.")
            return channels
    except Exception as e:
        print(f"API'den kanal listesi alınırken hata oluştu: {e}")
    return []

async def get_stream_url(page, full_url):
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and not stream_url:
            stream_url = f"{PROXY_PREFIX}{request.url}"

    page.on("request", handle_request)

    try:
        print(f"Yükleniyor: {full_url}")
        await page.goto(full_url, timeout=45000)
        await page.wait_for_timeout(6000)
    except Exception as e:
        print(f"Yükleme hatası: {e}")

    page.remove_listener("request", handle_request)
    return stream_url

async def main():
    channels_to_update = fetch_channels_from_api()
    if not channels_to_update:
        print("Taranacak kanal bulunamadı!")
        return

    # 1. Adım: Güncel m3u8 linklerini bul ve Worker proxy ekle
    updated_links = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for ch in channels_to_update:
            full_url = ch['url']
            print(f"\nTaranıyor: {ch['name']} ({full_url})")
            stream_url = await get_stream_url(page, full_url)
            if stream_url:
                print(f" Başarılı! Link alındı.")
                updated_links[ch['name']] = stream_url
            else:
                print(f" Link alınamadı, eski link korunacak.")

        await browser.close()

    # 2. Adım: playlist.m3u dosyasını oku ve EXTVLCOPT satırlarını koruyarak güncelle
    if not os.path.exists(OUTPUT_FILE):
        print(f"Hata: {OUTPUT_FILE} dosyası bulunamadı! Yeni dosya oluşturuluyor...")
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
            
            # Aradaki tüm ek satırları (#EXTVLCOPT vb.) bozmadan aynen kopyala
            while i < len(lines) and lines[i].strip().startswith("#"):
                new_lines.append(lines[i])
                i += 1
            
            # Eski akış linkini atla, yeni proxy'li linki yaz
            if i < len(lines):
                new_lines.append(f"{updated_links[matched_channel]}\n")
                i += 1
        else:
            new_lines.append(line)
            i += 1

    # Eğer listede hiç olmayan yeni kanallar varsa dosyanın sonuna ekle
    existing_content = "".join(new_lines)
    for ch_name, link in updated_links.items():
        if ch_name not in existing_content:
            new_lines.append(f'\n#EXTINF:-1 tvg-name="{ch_name}" group-title="SPOR",{ch_name}\n')
            new_lines.append("#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\n")
            new_lines.append("#EXTVLCOPT:network-caching=5000\n")
            new_lines.append("#EXTVLCOPT:live-caching=5000\n")
            new_lines.append(f"{link}\n")

    # 3. Adım: Dosyayı kaydet
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    print(f"\nİşlem tamam! {OUTPUT_FILE} dosyası güncellendi.")

if __name__ == "__main__":
    asyncio.run(main())
