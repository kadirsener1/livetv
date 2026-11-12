import asyncio
import os
from playwright.async_api import async_playwright

OUTPUT_FILE = "tv247tr.m3u"  # Çıktının yazılacağı dosya adı

# Güncellenecek kanallar ve doğrudan taranacak tam linkler
CHANNELS_TO_UPDATE = [
    {
        "name": "Test-TV",  # tv247tr.m3u içerisindeki kanal adı
        "url": "https://tvgarden.world/tv/tr/dnDnH0o46ue2tm"
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
    # 1. Adım: Doğrudan verilen linkleri tara ve .m3u8 adreslerini bul
    updated_links = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for ch in CHANNELS_TO_UPDATE:
            full_url = ch['url']
            print(f"\nTaranıyor: {ch['name']} ({full_url})")
            stream_url = await get_stream_url(page, full_url)
            if stream_url:
                print(f" Başarılı! Doğrudan .m3u8 linki alındı.")
                updated_links[ch['name']] = stream_url
            else:
                print(f" Link alınamadı, eski link korunacak.")

        await browser.close()

    # 2. Adım: tv247tr.m3u dosyasını oku ve #EXTVLCOPT satırlarına dokunmadan linkleri güncelle
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