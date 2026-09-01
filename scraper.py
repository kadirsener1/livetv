import asyncio
from playwright.async_api import async_playwright

# Hedef adres
TARGET_URL = "https://livelive24.com/?channel=espn-1-netherlands"
OUTPUT_FILE = "playlist.m3u"

async def extract_and_save_m3u():
    extracted_m3u8_links = []
    # İlk link bulunduğunda süreci durdurmak için bir sinyal (Event) oluşturuyoruz
    link_found_event = asyncio.Event()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Referer": "https://livelive24.com/"
            }
        )

        page = await context.new_page()

        # Ağ trafiğini dinleyen fonksiyon
        async def intercept_response(response):
            # Eğer zaten bir link bulup sinyali tetiklediysek, yeni gelen istekleri görmezden gel
            if link_found_event.is_set():
                return

            url = response.url
            if ".m3u8" in url and (url.startswith("http://") or url.startswith("https://")):
                extracted_m3u8_links.append(url)
                print(f"[+] İlk .m3u8 Linki Yakalandı: {url}")
                # Sinyali tetikle (Böylece bekleme döngüsü sonlanacak)
                link_found_event.set()

        # Ağ dinleyicisini tanımla
        page.on("response", intercept_response)

        print(f"[*] Sayfaya bağlanılıyor: {TARGET_URL}")
        try:
            # Sayfayı aç
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Olası oynatıcı butonlarına tıklayarak yayını tetikle
            try:
                await page.click("button, .vjs-big-play-button, #player", timeout=3000)
            except Exception:
                pass

            # Sinyalin tetiklenmesini (yani linkin bulunmasını) maksimum 15 saniye bekle.
            # Link 2. saniyede bulunursa, 15 saniye beklenmez, anında bir sonraki adıma geçilir.
            try:
                await asyncio.wait_for(link_found_event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                print("[-] 15 saniye içinde uygun .m3u8 akışı tespit edilemedi.")

        except Exception as e:
            print(f"[!] Bir hata oluştu: {e}")
        finally:
            # İşlem bittiğinde tarayıcıyı güvenli bir şekilde kapat
            await browser.close()

    # Sadece bulunan ilk linki dosyaya kaydet
    if extracted_m3u8_links:
        first_link = extracted_m3u8_links[0]
        print(f"\n[*] Dosyaya yazılıyor: {first_link}")
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            f.write("#EXTINF:-1,Canli Yayin - Stream 1\n")
            f.write(f"{first_link}\n")
                
        print(f"[BAŞARILI] '{OUTPUT_FILE}' dosyası güncellendi.")
    else:
        print("[-] Kaydedilecek link bulunamadı.")

if __name__ == "__main__":
    asyncio.run(extract_and_save_m3u())
