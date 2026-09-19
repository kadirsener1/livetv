import os
import sys
import time
from playwright.sync_api import sync_playwright


def yayin_yakala_ve_kaydet(hedef_url, cikis_dosyasi="playlist.m3u", bekleme_suresi=15):
    bulunan_yayinlar = set()

    def response_dinle(response):
        url = response.url
        medya_kaliplari = [".m3u8", ".mpd", "m3u8", "chunklist"]

        if any(kalip in url for kalip in medya_kaliplari):
            # Parça (segment/ts) dosyalarını hariç tut, ana manifest dosyasını al
            if not url.endswith(".ts"):
                if url not in bulunan_yayinlar:
                    bulunan_yayinlar.add(url)
                    print(f"[+] Akış Tespit Edildi: {url}")

    print(f"[*] Sayfaya bağlanılıyor: {hedef_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        page = context.new_page()
        page.on("response", response_dinle)

        try:
            page.goto(hedef_url, timeout=30000, wait_until="domcontentloaded")
            print(f"[*] Ağ trafiği dinleniyor ({bekleme_suresi} saniye)...")
            time.sleep(bekleme_suresi)
        except Exception as e:
            print(f"[!] Hata oluştu: {e}")
        finally:
            browser.close()

    # M3U Formatında Dosyaya Yazma
    if bulunan_yayinlar:
        print(f"[*] {len(bulunan_yayinlar)} adet akış '{cikis_dosyasi}' dosyasına kaydediliyor...")
        with open(cikis_dosyasi, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for idx, link in enumerate(bulunan_yayinlar, 1):
                f.write(f'#EXTINF:-1 tvg-id="Kanal_{idx}" group-title="Yayinlar", Yayin {idx}\n')
                f.write(f"{link}\n")
        print(f"[✓] Kayıt tamamlandı: {cikis_dosyasi}")
    else:
        print("[-] Herhangi bir akış bağlantısı bulunamadı, dosya oluşturulmadı.")


if __name__ == "__main__":
    HEDEF = "https://cdnapp.viphunter.top/watch.php?62"
    yayin_yakala_ve_kaydet(HEDEF, cikis_dosyasi="playlist.m3u")
