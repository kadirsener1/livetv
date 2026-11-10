import asyncio
import concurrent.futures
import os
import requests
from playwright.async_api import async_playwright

# Ortak domain yapılandırması
BASE_PREFIX = "https://bosssports"
BASE_SUFFIX = ".com"
START_NUM = 1074
END_NUM = 2000

CACHE_FILE = "domain_cache.txt"
OUTPUT_FILE = "tv247tr.m3u"  # Çıktının yazılacağı dosya adı

# Güncellenecek kanallar ve M3U içindeki aranacak isimleri
CHANNELS_TO_UPDATE = [
    {
        "name": "BEİN SPORTS 1-BS",  # tv247tr.m3u içerisindeki kanal adı
        "path": "?channel=channel%3Atflix-MDJjNzUwY2JiYTUzYTZlZg"
    },
    {
        "name": "BEİN SPORTS 2-BS",  # tv247tr.m3u içerisindeki kanal adı
        "path": "?channel=channel%3Atflix-NjNlZmVjMzI1MGY3NzgyYg"
    },
    {
        "name": "BEİN SPORTS 3-BS",  # tv247tr.m3u içerisindeki kanal adı
        "path": "?channel=channel%3Atflix-MTA4MWJhNGE4MDFiMzFjZg"
    },
    {
        "name": "BEİN SPORTS 4-BS",  # tv247tr.m3u içerisindeki kanal adı
        "path": "?channel=channel%3Atflix-YzkwOWU3MzQ0ZjAxNmRjMA"
    },
    {
        "name": "BEİN SPORTS 5-BS",  # tv247tr.m3u içerisindeki kanal adı
        "path": "?channel=channel%3Atflix-Yjg5NTA1ZGE2M2YyYWZkYg"
    },
    {
        "name": "BEİN SPORTS MAX 1-BS",  # tv247tr.m3u içerisindeki kanal adı
        "path": "?channel=channel%3Atflix-MzY1NGU3NzgyN2FjZTFmYQ"
    },
    {
        "name": "BEİN SPORTS MAX 2-BS",  # tv247tr.m3u içerisindeki kanal adı
        "path": "?channel=channel%3Atflix-ZDdkZjZiNWZlNjdlMzIxMQ"
    },
    {
        "name": "BEİN SPORTS HABER-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-NTRmYzI4ZjMzMmZhZDc0Mg"
    },
    {
        "name": "S SPORT-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-NzI0NmY4MjdlOGI4YWQzNw"
    },
    {
        "name": "S SPORT 2-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-NzM1ZmIxZDU3MWI0ZWJmNA"
    },
    {
        "name": "EUROSPORT 1-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-NDVlOWE1YmNmYzc2NTI5NA"
    },
    {
        "name": "EUROSPORT 2-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-ZGQ5MDRhZjM0NGUzNmE4ZA"
    },
    {
        "name": "SPOR SMART-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-ZjRhZTVhYTY2NWViMWFhOQ"
    },
    {
        "name": "SPOR SMART 2-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-N2NhZGU3M2NjNTlkOGY0Yw"
    },
    {
        "name": "ATV-BS",  # tv247tr.m3u içerisindeki diğer kanal adı
        "path": "?channel=channel%3Atflix-MDY0NDRjNTZkY2RmMWUwMg"
    }
]

def test_url_is_active(url):
    try:
        response = requests.head(url, timeout=2.0, allow_redirects=True)
        return response.status_code < 400
    except requests.RequestException:
        return False

def check_single_domain_num(num):
    url = f"{BASE_PREFIX}{num}{BASE_SUFFIX}"
    if test_url_is_active(url):
        return url
    return None

def get_active_base_domain(max_workers=50):
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cached_url = f.read().strip()
            if cached_url and test_url_is_active(cached_url):
                print(f"Cache'teki domain aktif: {cached_url}")
                return cached_url

    print(f"Güncel ana domain aranıyor ({START_NUM}-{END_NUM} aralığı taranıyor)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_single_domain_num, num): num for num in range(START_NUM, END_NUM)}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                print(f"Yeni aktif ana domain bulundu: {result}")
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    f.write(result)
                return result

    print("Aktif ana domain bulunamadı!")
    return None

async def get_stream_url(page, full_url):
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and not stream_url:
            # Bulunan ham m3u8 linkinin başına Cloudflare Worker proxy ön eki ekleniyor
            proxy_prefix = "https://avva.magnitude.workers.dev/?url="
            stream_url = f"{proxy_prefix}{request.url}"

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
    active_base_url = get_active_base_domain()
    if not active_base_url:
        return

    # 1. Adım: Güncel m3u8 linklerini bul
    updated_links = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for ch in CHANNELS_TO_UPDATE:
            full_url = f"{active_base_url}{ch['path']}"
            print(f"\nTaranıyor: {ch['name']} ({full_url})")
            stream_url = await get_stream_url(page, full_url)
            if stream_url:
                print(f" Başarılı! Link alındı ve Worker eklendi.")
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
            # Kanal adının bulunduğu satırı ekle
            new_lines.append(line)
            i += 1

            # Aradaki tüm ek satırları (#EXTVLCOPT vb.) bozmadan aynen kopyala
            while i < len(lines) and lines[i].strip().startswith("#"):
                new_lines.append(lines[i])
                i += 1

            # Artık sırada eski akış linki var. Onu yeni link ile değiştir ve eskisini atla
            if i < len(lines):
                new_lines.append(f"{updated_links[matched_channel]}\n")
                i += 1  # Eski link satırını geç
        else:
            new_lines.append(line)
            i += 1

    # 3. Adım: Dosyayı kaydet
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"\nİşlem tamam! {OUTPUT_FILE} dosyası güncellendi.")

if __name__ == "__main__":
    asyncio.run(main())
