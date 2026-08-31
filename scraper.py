import asyncio
import re
from playwright.async_api import async_playwright

TARGET_URL = "https://livelive24.com/?channel=espn-1-netherlands"

async def extract_stream():
    extracted_streams = []
    iframe_urls = []

    async with async_playwright() as p:
        # Gerçek bir tarayıcı profili ile başlatıyoruz (Cloudflare ve bot korumalarını aşmak için)
        browser = await p.chromium.launch(
            headless=True,  # Test ederken arka planda çalışanı görmek için False yapabilirsiniz
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

        # Ağ isteklerini dinle (.m3u8 veya stream linklerini yakala)
        def intercept_response(response):
            url = response.url
            if ".m3u8" in url or ".mpd" in url or "playlist" in url:
                if url not in extracted_streams:
                    extracted_streams.append(url)
                    print(f"\n[+] CANLI YAYIN LINKI (m3u8) BULUNDU:\n--> {url}\n")

        page.on("response", intercept_response)

        print(f"[*] Sayfaya bağlanılıyor: {TARGET_URL}")
        try:
            # Sayfayı aç ve ağ trafiğinin oturmasını bekle
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000) # Reklam ve JS yönlendirmeleri için bekle
        except Exception as e:
            print(f"[!] Sayfa yükleme uyarısı: {e}")

        # Sayfadaki tüm iframe linklerini tespit et
        frames = page.frames
        print(f"[*] Toplam tespit edilen Frame/Iframe sayısı: {len(frames)}")
        
        for frame in frames:
            if frame.url and frame.url != TARGET_URL and "about:blank" not in frame.url:
                if frame.url not in iframe_urls:
                    iframe_urls.append(frame.url)

        print("\n--- BULUNAN IFRAME ADRESLERİ ---")
        for idx, ifr in enumerate(iframe_urls, 1):
            print(f"{idx}. {ifr}")

        # Eğer yayın bir 'Play' butonuna basılınca başlıyorsa simüle edelim
        try:
            # Olası video/player oynatma butonlarını tıkla
            await page.click("button, .vjs-big-play-button, #player", timeout=3000)
            await page.wait_for_timeout(3000)
        except Exception:
            pass

        await browser.close()

    print("\n--- SONUÇ ÖZETİ ---")
    if extracted_streams:
        print("[BAŞARILI] Akış Linkleri:")
        for s in extracted_streams:
            print(s)
    else:
        print("[-] Doğrudan .m3u8 linki henüz başlamadı veya token bekliyor. Yukarıdaki iframe linklerini kontrol edin.")

if __name__ == "__main__":
    asyncio.run(extract_stream())
