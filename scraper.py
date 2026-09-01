import asyncio
import os
from playwright.async_api import async_playwright

# Hedef adresi buraya tanımlayabilirsiniz (Örnek amaçlı genel yapı kullanılmıştır)
TARGET_URL = "https://livelive24.com/?channel=espn-1-netherlands"
OUTPUT_FILE = "playlist.m3u"

async def extract_and_save_m3u():
    extracted_m3u8_links = []

    async with async_playwright() as p:
        # Tarayıcıyı başlat (Cloudflare vb. korumaları aşmak için uygun başlıklarla)
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

        # Ağ trafiğini dinle ve sadece .m3u8 uzantılı linkleri yakala
        def intercept_response(response):
            url = response.url
            # Linkin m3u8 içerip içermediğini ve geçerli bir URL şeması olduğunu kontrol et
            if ".m3u8" in url and (url.startswith("http://") or url.startswith("https://")):
                if url not in extracted_m3u8_links:
                    extracted_m3u8_links.append(url)
                    print(f"[+] .m3u8 Linki Yakalandı: {url}")

        page.on("response", intercept_response)

        print(f"[*] Sayfa yükleniyor: {TARGET_URL}")
        try:
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(7000)  # Akışın ve reklamların yüklenmesi için bekleme süresi
        except Exception as e:
            print(f"[!] Sayfa yükleme hatası/uyarısı: {e}")

        # Olası oynat düğmelerine tıklayarak yayını tetiklemeyi dene
        try:
            await page.click("button, .vjs-big-play-button, #player", timeout=3000)
            await page.wait_for_timeout(3000)
        except Exception:
            pass

        await browser.close()

    # Yakalanan linkleri M3U formatında dosyaya yazdır
    if extracted_m3u8_links:
        print(f"\n[*] {len(extracted_m3u8_links)} adet m3u8 linki bulundu. Dosya yazılıyor...")
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            # Standart M3U başlığı
            f.write("#EXTM3U\n")
            
            for idx, link in enumerate(extracted_m3u8_links, 1):
                # Her kanal için etiket ekle (GSE veya VLC için)
                f.write(f"#EXTINF:-1,Canli Yayin - Stream {idx}\n")
                f.write(f"{link}\n")
                
        print(f"[BAŞARILI] Linkler '{OUTPUT_FILE}' dosyasına kaydedildi.")
    else:
        print("[-] Aktif .m3u8 yayını bulunamadı. Sayfa yüklenirken akış başlamamış olabilir.")

if __name__ == "__main__":
    asyncio.run(extract_and_save_m3u())
