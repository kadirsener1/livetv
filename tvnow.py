import asyncio
import os
from playwright.async_api import async_playwright

# Doğrudan güncel domaini buraya sabitliyoruz
ACTIVE_BASE_URL = "https://tvnow247.top/"

OUTPUT_FILE = "tv247tr.m3u"

CHANNELS_TO_UPDATE = [
    {
        "name": "BEİN SPORTS 1-TV",
        "path": "embed-r4/bein-sports-1-turkey"
    },
    {
        "name": "BEİN SPORTS 2-TV",
        "path": "embed-r4/bein-sports-2-turkey"
    },
    {
        "name": "BEİN SPORTS 3-TV",
        "path": "embed-r4/bein-sports-3-turkey"
    },
    {
        "name": "BEİN SPORTS 4-TV",
        "path": "embed-r4/bein-sports-4-turkey"
    },
    {
        "name": "BEİN SPORTS 5-TV",
        "path": "embed-r4/bein-sports-5-turkey"
    }
]

async def get_stream_url(page, full_url):
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and not stream_url:
            stream_url = request.url

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
    print(f"Kullanılan Ana Domain: {ACTIVE_BASE_URL}")

    # 1. Adım: Güncel m3u8 linklerini bul
    updated_links = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for ch in CHANNELS_TO_UPDATE:
            full_url = f"{ACTIVE_BASE_URL}{ch['path']}"
            print(f"\nTaranıyor: {ch['name']} ({full_url})")
            stream_url = await get_stream_url(page, full_url)
            if stream_url:
                print(" Başarılı! Doğrudan .m3u8 linki alındı.")
                updated_links[ch['name']] = stream_url
            else:
                print(" Link alınamadı, eski link korunacak.")

        await browser.close()

    # 2. Adım: tv247tr.m3u dosyasını oku ve linkleri güncelle
    if not os.path.exists(OUTPUT_FILE):
        print(f"Hata: {OUTPUT_FILE} dosyası bulunamadı!")
        return

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
                new_lines.append(f"{updated_links[matched_channel]}\n")
                i += 1
        else:
            new_lines.append(line)
            i += 1

    # 3. Adım: Dosyayı kaydet
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    print(f"\nİşlem tamam! {OUTPUT_FILE} dosyası güncellendi.")

if __name__ == "__main__":
    asyncio.run(main())
