import re
import urllib.request

# Kanal haritası
channelsMap = {
    "Bein Sports 1 TR": "https://elif.eromaxe.com/zeynep/bein1tr",
    "Bein Sports 2 TR": "https://elif.eromaxe.com/zeynep/bein2tr",
    "Bein Sports 3 TR": "https://elif.eromaxe.com/zeynep/bein3tr",
    "Bein Sports 4 TR": "https://elif.eromaxe.com/zeynep/bein4tr",
    "Bein Sports 5 TR": "https://elif.eromaxe.com/zeynep/bein5tr",
    "Bein Sports Max 1": "https://elif.eromaxe.com/zeynep/beinmax1tr",
    "Bein Sports Max 2": "https://elif.eromaxe.com/zeynep/beinmax2tr",
    "Bein Haber": "https://elif.eromaxe.com/zeynep/beinhabertr",
    "S Sport 1 TR": "https://elif.eromaxe.com/zeynep/ssport1tr",
    "S Sport 2 TR": "https://elif.eromaxe.com/zeynep/ssport2tr",
    "A Sport": "https://elif.eromaxe.com/zeynep/asport",
    "TRT Spor": "https://elif.eromaxe.com/zeynep/trtsport",
    "Eurosport 1": "https://elif.eromaxe.com/zeynep/eruosport1",
    "Eurosport 2": "https://elif.eromaxe.com/zeynep/eruosport2",
    "Smart Spor": "https://elif.eromaxe.com/zeynep/sportsmart",
    "Smart Spor 2": "https://elif.eromaxe.com/zeynep/sportsmart2",
    "ATV": "https://elif.eromaxe.com/zeynep/atv",
    "Tabii Spor": "https://elif.eromaxe.com/zeynep/tabiisport",
    "Tabii Spor 1": "https://elif.eromaxe.com/zeynep/tabiisport1",
    "Tabii Spor 2": "https://elif.eromaxe.com/zeynep/tabiisport2",
    "Tabii Spor 3": "https://elif.eromaxe.com/zeynep/tabiisport3",
    "Tabii Spor 4": "https://elif.eromaxe.com/zeynep/tabiisport4",
    "DAZN 1 Germany": "https://tim-streams.com/channel/dazn-1-germany",
}

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
ua_suffix = f"|{user_agent}"

m3u_content = '#EXTM3U\n'

for name, target_url in channelsMap.items():
    try:
        req = urllib.request.Request(target_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        match = re.search(r'(https?://[^\s<>"]+?\.m3u8[^\s<>"]*)', html)
        if match:
            raw_m3u8 = match.group(1)
            final_url = raw_m3u8 + ua_suffix
            m3u_content += f'#EXTINF:-1 tvg-name="{name}",{name}\n{final_url}\n'
            print(f"[BAŞARILI] {name} eklendi.")
        else:
            print(f"[BULUNAMADI] {name} için .m3u8 linki bulunamadı.")
    except Exception as e:
        print(f"[HATA] {name}: {str(e)}")

# Playlist dosyasını kaydet
with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write(m3u_content)

print("Playlist başarıyla güncellendi!")
