import os
import re
import urllib.request

# Kanal haritası
channelsMap = {
    "Bein Sports 1-BS": "https://elif.eromaxe.com/zeynep/bein1tr",
    "Bein Sports 2-BS": "https://elif.eromaxe.com/zeynep/bein2tr",
    "Bein Sports 3-BS": "https://elif.eromaxe.com/zeynep/bein3tr",
    "Bein Sports 4-BS": "https://elif.eromaxe.com/zeynep/bein4tr",
    "Bein Sports 5-BS": "https://elif.eromaxe.com/zeynep/bein5tr",
    "Bein Sports Max 1-BS": "https://elif.eromaxe.com/zeynep/beinmax1tr",
    "Bein Sports Max 2-BS": "https://elif.eromaxe.com/zeynep/beinmax2tr",
    "Bein Haber": "https://elif.eromaxe.com/zeynep/beinhabertr",
    "S Sport 1-BS": "https://elif.eromaxe.com/zeynep/ssport1tr",
    "S Sport 2-BS": "https://elif.eromaxe.com/zeynep/ssport2tr",
    "A Sport-BS": "https://elif.eromaxe.com/zeynep/asport",
    "TRT Spor-BS": "https://elif.eromaxe.com/zeynep/trtsport",
    "Eurosport 1-BS": "https://elif.eromaxe.com/zeynep/eruosport1",
    "Eurosport 2-BS": "https://elif.eromaxe.com/zeynep/eruosport2",
    "Smart Spor-BS": "https://elif.eromaxe.com/zeynep/sportsmart",
    "Smart Spor 2-BS": "https://elif.eromaxe.com/zeynep/sportsmart2",
    "ATV-BS": "https://elif.eromaxe.com/zeynep/atv",
    "Tabii Spor": "https://elif.eromaxe.com/zeynep/tabiisport",
    "Tabii Spor 1": "https://elif.eromaxe.com/zeynep/tabiisport1",
    "Tabii Spor 2": "https://elif.eromaxe.com/zeynep/tabiisport2",
    "Tabii Spor 3": "https://elif.eromaxe.com/zeynep/tabiisport3",
    "Tabii Spor 4": "https://elif.eromaxe.com/zeynep/tabiisport4",
}

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
ua_suffix = f"|{user_agent}"

# Yeni linkleri geçici olarak saklayacağımız sözlük
updated_links = {}

for name, target_url in channelsMap.items():
    try:
        req = urllib.request.Request(target_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        match = re.search(r'(https?://[^\s<>"]+?\.m3u8[^\s<>"]*)', html)
        if match:
            raw_m3u8 = match.group(1)
            final_url = raw_m3u8 + ua_suffix
            updated_links[name] = final_url
            print(f"[BAŞARILI] {name} linki alındı.")
        else:
            print(f"[BULUNAMADI] {name} için .m3u8 linki bulunamadı.")
    except Exception as e:
        print(f"[HATA] {name}: {str(e)}")

# Mevcut tv247tr playlist dosyasını oku ve güncelle
playlist_filename = "tv247tr.m3u"

if os.path.exists(playlist_filename):
    with open(playlist_filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        if line.startswith("#EXTINF"):
            match_name = re.search(r",\s*(.+)$", line.strip())
            if match_name:
                channel_name = match_name.group(1).strip()
                if channel_name in updated_links and i + 1 < len(lines):
                    new_lines.append(updated_links[channel_name] + "\n")
                    i += 2
                    continue
        i += 1

    with open(playlist_filename, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print("Playlist başarıyla güncellendi!")
else:
    print(f"[HATA] {playlist_filename} dosyası bulunamadı!")
