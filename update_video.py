from datetime import datetime
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import requests

# 1. M3U Listenizi Çek ve Kanal Sayısını Hesapla
m3u_url = (
    "https://raw.githubusercontent.com/kadirsener1/livetv/refs/heads/main/tv247tr.m3u"
)
try:
  response = requests.get(m3u_url)
  content = response.text
  channel_count = content.count("#EXTINF")
except Exception as e:
  print(f"M3U okuma hatası: {e}")
  channel_count = 0

# 2. Güncelleme Zamanı (Türkiye Saati)
now = datetime.now().strftime("%d.%m.%Y - %H:%M")

# 3. Arkaplan Resmini Aç ve Yazıları Ekle
try:
  img = Image.open("bg.JPG").convert("RGB")
  img = img.resize((1280, 720))  # 720p HD standart boyut
except Exception as e:
  print(f"bg.JPG yüklenemedi: {e}")
  img = Image.new("RGB", (1280, 720), color=(15, 15, 15))

draw = ImageDraw.Draw(img)

# Metinler
text_title = "IPTV BILGILENDIRME KANALI"
text_channels = f"Listede Toplam {channel_count} Kanal Bulunmaktadir"
text_date = f"Son Guncelleme: {now}"

# Alt karartma kutusu
draw.rectangle([(0, 450), (1280, 720)], fill=(0, 0, 0, 200))

# Yazıları ortala
draw.text((640, 520), text_title, fill="#00FFCC", anchor="mm")
draw.text((640, 590), text_channels, fill="#FFFFFF", anchor="mm")
draw.text((640, 645), text_date, fill="#FFD700", anchor="mm")

# Geçici görsel kaydet
temp_image_path = "temp_frame.jpg"
img.save(temp_image_path)

# 4. 5 Saniyelik MP4 Video Oluştur
output_video = "bilgi.mp4"
fps = 30
duration = 5
total_frames = fps * duration

frame = cv2.imread(temp_image_path)
height, width, _ = frame.shape

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
video = cv2.VideoWriter(output_video, fourcc, fps, (width, height))

for _ in range(total_frames):
  video.write(frame)

video.release()

# 5. TiviMate İçin Otomatik .m3u8 Çalma Listesi Oluştur
m3u8_content = f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:5
#EXT-X-MEDIA-SEQUENCE:1
#EXTINF:5.0,
https://raw.githubusercontent.com/kadirsener1/tvmyeni/main/bilgi.mp4
#EXTINF:5.0,
https://raw.githubusercontent.com/kadirsener1/tvmyeni/main/bilgi.mp4
"""

with open("bilgi.m3u8", "w", encoding="utf-8") as f:
  f.write(m3u8_content)

print(
    f"Başarıyla güncellendi! Kanal Sayısı: {channel_count}, Zaman: {now} (mp4"
    " ve m3u8 oluşturuldu)"
)
