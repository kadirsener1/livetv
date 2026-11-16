import asyncio
import os
import re
from playwright.async_api import async_playwright

# Kanal haritası (Doğrudan tam URL'leri içerir, cache/numara taraması yapılmaz)
channelsMap = {
    "Bein Sports 1-BS": "https://elif.eromaxe.com/zeynep/bein1tr",
    "Bein Sports 2-BS": "https://elif.eromaxe.com/zeynep/bein2tr",
    "Bein Sports 3-BS": "https://elif.eromaxe.com/zeynep/bein3tr",
    "Bein Sports 4-BS": "https://elif.eromaxe.com/zeynep/bein4tr",
    "Bein Sports 5-BS": "https://elif.eromaxe.com/zeynep/bein5tr",
    "Bein Sports Max 1-BS": "https://elif.eromaxe.com/zeynep/beinmax1tr",
    "Bein Sports Max 2-BS": "https://elif.eromaxe.com/zeynep/beinmax2tr",
    "Bein Haber": "https://elif.eromaxe.com/zeynep/beinhabertr",
    "S Sport 1-BS": "https://elif.eromaxe.com/zeynep/ssport1tr",
    "S Sport 2-BS": "https://elif.eromaxe.com/zeynep/ssport2tr",
    "A Sport-BS": "https://elif.eromaxe.com/zeynep/asport",
    "TRT Spor-BS": "https://elif.eromaxe.com/zeynep/trtsport",
    "Eurosport 1-BS": "https://elif.eromaxe.com/zeynep/eruosport1",
    "Eurosport 2-BS": "https://elif.eromaxe.com/zeynep/eruosport2",
    "Smart Spor-BS": "https://elif.eromaxe.com/zeynep/sportsmart",
    "Smart Spor 2-BS": "https://elif.eromaxe.com/zeynep/sportsmart2",
    "ATV-BS": "https://elif.eromaxe.com/zeynep/atv",
    "Tabii Spor": "https://elif.eromaxe.com/zeynep/tabiisport",
    "Tabii Spor 1": "https://elif.eromaxe.com/zeynep/tabiisport1",
    "Tabii Spor 2": "https://elif.eromaxe.com/zeynep/tabiisport2",
    "Tabii Spor 3": "https://elif.eromaxe.com/zeynep/tabiisport3",
    "Tabii Spor 4": "https://elif.eromaxe.com/zeynep/tabiisport4",
}

OUTPUT_FILE = "tv247tr.m3u"  # Çıktının ve güncellenecek dosyanın adı
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
ua_suffix = f"|{user_agent}"

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
    # 1. Adım: Playwright ile haritadaki her bir linki ziyaret edip .m3u8 uzantılı akış linkini yakala
    updated_links = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for name, target_url in channelsMap.items():
            print(f"\nTaranıyor: {name} ({target_url})")
            raw_m3u8 = await get_stream_url(page, target_url)
            if raw_m3u8:
                final_url = raw_m3u8 + ua_suffix
                updated_links[name] = final_url
                print(f"[BAŞARILI] {name} linki alındı.")
            else:
                print(f"[BULUNAMADI] {name} için .m3u8 linki bulunamadı, eski link korunacak.")

        await browser.close()

    # 2. Adım: tv247tr.m3u dosyasını oku ve sadece kanal adlarıyla birebir eşleşen satırların linklerini güncelle
    if not os.path.exists(OUTPUT_FILE):
        print(f"[HATA] {OUTPUT_FILE} dosyası bulunamadı!")
        return

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        if line.startswith("#EXTINF"):
            match_name = re.search(r",\s*(.+)$", line.strip())
            if match_name:
                channel_name = match_name.group(1).strip()
                if channel_name in updated_links and i + 1 < len(lines):
                    # Yeni bulunan m3u8 linkini ekle ve eski link satırını atla
                    new_lines.append(updated_links[channel_name] + "\n")
                    i += 2
                    continue
        i += 1

    # 3. Adım: Güncellenmiş listeyi dosyaya kaydet
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"\nİşlem tamam! {OUTPUT_FILE} başarıyla güncellendi.")

if __name__ == "__main__":
    asyncio.run(main())
