import asyncio
import concurrent.futures
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import requests
from playwright.async_api import async_playwright

# Ortak domain yapılandırması
BASE_PREFIX = "https://bosssports"
BASE_SUFFIX = ".com"
START_NUM = 1074
END_NUM = 2000

CACHE_FILE = "domain_cache1.txt"
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

def append_ref_param(stream_url, ref_base_url):
    ref_value = f"{ref_base_url.rstrip('/')}/"
    parts = urlsplit(stream_url)
    query_items = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "ref"]
    query_items.append(("ref", ref_value))
    new_query = urlencode(query_items)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

async def get_stream_url(page, full_url):
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and not stream_url:
            # Bulunan ham m3u8 linkinin başına Cloudflare Worker proxy ön eki ekleniyor
            proxy_prefix = ""
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

    # 2. Adım: Bulunan linkleri boss/<kanaladi>.m3u8 dosyalarına ayrı ayrı yaz
    boss_dir = os.path.abspath("boss")
    os.makedirs(boss_dir, exist_ok=True)

    written_count = 0
    for ch_name, stream_url in updated_links.items():
        safe_name = ch_name.replace("/", "_").replace("\\", "_")
        channel_file = os.path.join(boss_dir, f"{safe_name}.m3u8")
        link_with_ref = append_ref_param(stream_url, active_base_url)
        content = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=8000000\n"
            f"{link_with_ref}\n"
        )
        with open(channel_file, "w", encoding="utf-8") as f:
            f.write(content)
        if os.path.exists(channel_file):
            written_count += 1

    print(f"\nİşlem tamam! {written_count} kanal linki '{boss_dir}' klasörüne yazıldı.")

if __name__ == "__main__":
    asyncio.run(main())
