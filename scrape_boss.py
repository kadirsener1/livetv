import asyncio
from playwright.async_api import async_playwright
import re

# Kanalın sondaki sabit kod kısmı (değişmeyen parametre)
CHANNEL_PATH = "/?channel=channel%3Atflix-MDJjNzUwY2JiYTUzYTZlZg"
CHANNEL_NAME = "Boss Sports - Tflix"
OUTPUT_FILE = "playlist.m3u"

async def find_active_domain(page):
    """
    Muhtemel domain numaralarını (örneğin 1070 ile 1090 arası) test ederek 
    aktif ve çalışan alan adını otomatik bulur.
    """
    base_prefix = "https://bosssports"
    base_suffix = ".com"
    
    # Mevcut tahmin edilen numara etrafında bir aralık tarayalım
    # (İsterseniz bu listeyi veya mantığı genişletebilirsiniz)
    current_num = 1074
    test_numbers = [current_num] + list(range(current_num + 1, current_num + 10)) + list(range(current_num - 5, current_num))

    for num in test_numbers:
        candidate_url = f"{base_prefix}{num}{base_suffix}{CHANNEL_PATH}"
        try:
            print(f"Test ediliyor: {candidate_url}")
            response = await page.goto(candidate_url, timeout=10000, wait_until="domcontentloaded")
            
            # Eğer sayfa 200 dönüyorsa ve hata sayfasına (cloudflare/404) düşmüyorsa doğru domain'dir
            if response and response.status == 200:
                final_url = page.url
                # Eğer domain engellenip başka bir siteye yönlendirildiyse kontrol et
                if "bosssports" in final_url:
                    print(f" Aktif domain bulundu: {final_url}")
                    return final_url
        except Exception:
            continue
            
    return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        stream_url = None

        def handle_request(request):
            nonlocal stream_url
            if ".m3u8" in request.url and not stream_url:
                stream_url = request.url

        page.on("request", handle_request)

        # 1. Adım: Çalışan güncel domain adresini otomatik bul
        active_page_url = await find_active_domain(page)

        if not active_page_url:
            print("Hiçbir aktif domain bulunamadı!")
            await browser.close()
            return

        # 2. Adım: Bulunan güncel sayfadan m3u8 akış linkini yakala
        try:
            print(f"Yayın yükleniyor: {active_page_url}")
            await page.goto(active_page_url, timeout=45000)
            await page.wait_for_timeout(6000) # Oynatıcının tetiklenmesi için bekle
        except Exception as e:
            print(f"Yayın yükleme hatası: {e}")

        await browser.close()

        # 3. Adım: Playlist'e kaydet
        if stream_url:
            print(f" Başarılı! Bulunan m3u8 linki: {stream_url}")
            m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-name="{CHANNEL_NAME}" group-title="Otomatik Boss", {CHANNEL_NAME}
{stream_url}
"""
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write(m3u_content)
        else:
            print("Aktif sayfa açıldı ancak .m3u8 akış adresi yakalanamadı.")

if __name__ == "__main__":
    asyncio.run(main())
