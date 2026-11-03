import asyncio
import concurrent.futures
import os
import requests
from playwright.async_api import async_playwright

# Ortak domain yapılandırması
BASE_PREFIX = "https://bosssports"
BASE_SUFFIX = ".com"
START_NUM = 1000
END_NUM = 2000

CACHE_FILE = "domain_cache.txt"
OUTPUT_FILE = "playlist.m3u"

# Kanalların yolları (path) ve isimleri
CHANNELS = [
    {
        "name": "Boss Sports - Tflix",
        "path": "/?channel=channel%3Atflix-MDJjNzUwY2JiYTUzYTZlZg",
        "group": "Spor Kanalları"
    },
    {
        "name": "Boss Sports - Örnek Kanal 2",
        "path": "/?channel=channel%3Aornek-kanal-kodu-2",
        "group": "Spor Kanalları"
    }
]

def test_url_is_active(url):
    """Verilen tam URL veya ana domain'in çalışıp çalışmadığını test eder"""
    try:
        response = requests.head(url, timeout=2.0, allow_redirects=True)
        return response.status_code < 400
    except requests.RequestException:
        return False

def check_single_domain_num(num):
    """Numaraya göre domain adresini test eder"""
    url = f"{BASE_PREFIX}{num}{BASE_SUFFIX}"
    if test_url_is_active(url):
        return url
    return None

def get_active_base_domain(max_workers=50):
    """
    Önce cache dosyasını kontrol eder. Cache'teki domain çalışıyorsa tarama yapmaz.
    Çalışmıyorsa geniş aralığı multi-threading ile tarayıp yeni domain'i bulur ve kaydeder.
    """
    # 1. Adım: Cache kontrolü
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cached_url = f.read().strip()
            if cached_url:
                print(f"Cache'ten domain okunuyor: {cached_url}")
                # Hızlıca cache'teki domain'in hala aktif olup olmadığını test et
                if test_url_is_active(cached_url):
                    print("Cache'teki domain aktif, tarama atlandı!")
                    return cached_url
                else:
                    print("Cache'teki domain süresi dolmuş/kapanmış, yeniden taranıyor...")

    # 2. Adım: Cache geçersizse multi-threading ile baştan tara
    print(f"Güncel ana domain aranıyor ({START_NUM}-{END_NUM} aralığı taranıyor)...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_single_domain_num, num): num for num in range(START_NUM, END_NUM)}
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                print(f" Yeni aktif ana domain bulundu: {result}")
                # Bulunan yeni domain'i cache dosyasına kaydet
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    f.write(result)
                return result
                
    print("Aktif ana domain bulunamadı!")
    return None

async def get_stream_url(page, full_url):
    """Playwright ile açılan sayfadan m3u8 akış adresini yakalar"""
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
    # 1. Adım: Önbellekli veya taramalı aktif domain'i al
    active_base_url = get_active_base_domain()
    
    if not active_base_url:
        return

    m3u_lines = ["#EXTM3U\n"]

    # 2. Adım: Bulunan domain ile kanalları sırayla tarayıp m3u8 linklerini al
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for channel in CHANNELS:
            full_url = f"{active_base_url}{channel['path']}"
            print(f"\nİşleniyor: {channel['name']} ({full_url})")
            
            stream_url = await get_stream_url(page, full_url)

            if stream_url:
                print(f" Başarılı! m3u8 linki alındı.")
                extinf = f'#EXTINF:-1 tvg-name="{channel["name"]}" group-title="{channel["group"]}", {channel["name"]}\n'
                m3u_lines.append(extinf)
                m3u_lines.append(f"{stream_url}\n")
            else:
                print(f" Akış adresi yakalanamadı: {channel['name']}")

        await browser.close()

    # 3. Adım: Sonuçları playlist.m3u dosyasına yaz
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(m3u_lines)
    
    print(f"\nTüm işlemler tamamlandı! {OUTPUT_FILE} güncellendi.")

if __name__ == "__main__":
    asyncio.run(main())
