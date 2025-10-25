import re, json
import cloudscraper
from Kekik.cli import konsol as log  

class MonoTV:
    def __init__(self, m3u_dosyasi):
        self.m3u_dosyasi = m3u_dosyasi
        # 🔹 Cloudflare'i otomatik aşan oturum:
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )

    def yayin_urlini_al(self):
        json_endpoint = "https://sportsobama.com/domain.php"
        log.log(f"[cyan][~] domain.php çağrılıyor: {json_endpoint}")
        try:
            response = self.scraper.get(json_endpoint)
            text = response.text.strip()
            print(text)
            if not text or text.startswith("<"):
                raise ValueError("HTML döndü, Cloudflare veya erişim hatası.")

            json_data = json.loads(text)
            yayin_url = json_data["baseurl"].replace("\\/", "/").rstrip("/")
            log.log(f"[green][+] Yayın URL bulundu: {yayin_url}")
            return yayin_url
        except Exception as e:
            raise ValueError(f"Yayın URL'si alınamadı: {e}")

    def m3u_guncelle(self):
        with open(self.m3u_dosyasi, "r", encoding="utf-8") as f:
            m3u_icerik = f.read()

        yeni_yayin_url = self.yayin_urlini_al()

        pattern = re.compile(
            r'(#EXTVLCOPT:http-referrer=(https?://[^/]*monotv[^/]*\.[^\s/]+).+?\n)(https?://[^ \n\r]+)',
            re.IGNORECASE
        )

        eslesmeler = list(pattern.finditer(m3u_icerik))
        if not eslesmeler:
            raise ValueError("Referer'i monotv olan yayınlar bulunamadı!")

        log.log(f"[yellow][~] Toplam {len(eslesmeler)} adet yayın bulundu, kontrol ediliyor...")

        degisti_mi = False
        yeni_icerik = m3u_icerik

        for eslesme in eslesmeler:
            eski_link = eslesme[3]
            path_kismi = '/' + '/'.join(eski_link.split('/')[3:])
            yeni_link = yeni_yayin_url + path_kismi
            yeni_link = re.sub(r'(?<!:)//+', '/', yeni_link)
            if eski_link != yeni_link:
                log.log(f"[blue]• Güncellendi: {eski_link} → {yeni_link}")
                yeni_icerik = yeni_icerik.replace(eski_link, yeni_link)
                degisti_mi = True
            else:
                log.log(f"[gray]• Zaten güncel: {eski_link}")

        if degisti_mi:
            with open(self.m3u_dosyasi, "w", encoding="utf-8") as f:
                f.write(yeni_icerik)
            log.log(f"[green][✓] M3U dosyası güncellendi.")
        else:
            log.log(f"[green][✓] Tüm yayınlar zaten günceldi, dosya yazılmadı.")

if __name__ == "__main__":
    guncelle = MonoTV("k.m3u")
    guncelle.m3u_guncelle()
