import os
import re
import requests

# Hedef kanal URL'si
CHANNEL_URL = "https://bosssports1074.com/?channel=channel%3Atflix-MDJjNzUwY2JiYTUzYTZlZg"
CHANNEL_NAME = "Boss Sports - Tflix"
OUTPUT_FILE = "playlist.m3u"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://bosssports1074.com/"
}

def get_m3u8_link():
    try:
        response = requests.get(CHANNEL_URL, headers=headers, timeout=15)
        if response.status_code == 200:
            html_content = response.text
            
            # Sayfa içerisindeki m3u8 linkini regex ile arayalım
            # Genellikle player içinde veya script tag'leri arasında geçer
            match = re.search(r'https?://[^\s<>"]+?\.m3u8[^\s<>"]*', html_content)
            if match:
                return match.group(0)
                
            # Eğer doğrudan m3u8 bulunamazsa, embed veya api isteklerini yakalamak gerekebilir
            # Alternatif olarak sayfa içindeki kaynakları kontrol edelim
        print(f"Sayfa yüklenemedi veya m3u8 bulunamadı. Status: {response.status_code}")
    except Exception as e:
        print(f"Hata oluştu: {e}")
    return None

def update_playlist(stream_url):
    if not stream_url:
        print("Geçerli bir akış adresi bulunamadığı için playlist güncellenmedi.")
        return

    m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-name="{CHANNEL_NAME}" group-title="Otomatik Boss", {CHANNEL_NAME}
{stream_url}
"""
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)
    print(f"Başarılı! Güncel link playlist.m3u dosyasına yazıldı: {stream_url}")

if __name__ == "__main__":
    link = get_m3u8_link()
    update_playlist(link)
