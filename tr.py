from Kekik.cli import konsol
from httpx     import Client
from parsel    import Selector
import re
from urllib.parse import urlparse

class TRGoals:
    def __init__(self, m3u_dosyasi):
        self.m3u_dosyasi = m3u_dosyasi
        self.httpx       = Client(timeout=10, verify=False)

    def referer_domainini_al(self):
        referer_deseni = r'#EXTVLCOPT:http-referrer=(https?://[^/]*trgoals[^/]*\.[^\s/]+)'
        with open(self.m3u_dosyasi, "r") as dosya:
            icerik = dosya.read()
        if eslesme := re.search(referer_deseni, icerik):
            return eslesme[1]
        else:
            raise ValueError("M3U dosyasında 'trgoals' içeren referer domain bulunamadı!")

    # 🔹 HTML içindeki meta veya JS redirect'leri yakala
    def meta_refresh_bul(self, html):
        meta = re.search(r'<meta\s+http-equiv=["\']refresh["\'][^>]*content=["\'][^"\']*;URL=([^"\']+)["\']', html, re.I)
        if meta:
            return meta.group(1)
        js = re.search(r'location\.replace\(["\']([^"\']+)["\']', html)
        if js:
            return js.group(1)
        return None

    # 🔹 Derin redirect takibi (t.co, bit.ly, meta refresh)
    def redirect_gec(self, url: str, max_depth=5):
        konsol.log(f"[cyan][~] redirect_gec çağrıldı: {url}")
        current = url
        for i in range(max_depth):
            try:
                response = self.httpx.get(current, follow_redirects=True)
            except Exception as e:
                raise ValueError(f"Redirect sırasında hata oluştu: {e}")

            # geçmiş + son URL’leri tara
            for u in [*map(str, [r.url for r in response.history]), str(response.url)]:
                if "trgoals" in u and not u.endswith("trgoalsgiris.xyz"):
                    konsol.log(f"[green][+] TRGoals domain bulundu: {u}")
                    return u.strip("/")

            # HTML içi yönlendirme varsa takip et
            next_url = self.meta_refresh_bul(response.text)
            if next_url:
                if next_url.startswith("/"):
                    p = urlparse(current)
                    next_url = f"{p.scheme}://{p.netloc}{next_url}"
                elif not next_url.startswith("http"):
                    p = urlparse(current)
                    next_url = f"{p.scheme}://{p.netloc}/{next_url.lstrip('/')}"
                konsol.log(f"[yellow][~] Meta/JS redirect bulundu: {next_url}")
                current = next_url
                continue

            # t.co zincirleri
            if "t.co/" in str(response.url):
                current = str(response.url)
                konsol.log(f"[yellow][~] t.co yönlendirmesi tekrar denenecek: {current}")
                continue

            break

        raise ValueError("Redirect zincirinde 'trgoals' içeren bir link bulunamadı!")

    def trgoals_domaini_al(self):
        konsol.log("[cyan][~] bit.ly üzerinden domain aranıyor...")
        try:
            domain = self.redirect_gec("https://bit.ly/m/taraftarium24w")
            if "trgoals" in domain:
                return domain
        except Exception as e:
            konsol.log(f"[red][!] bit.ly başarısız: {e}")

        konsol.log("[yellow][~] Yedek linke geçiliyor...")
        try:
            return self.redirect_gec("https://t.co/lU6t0lkPKD")  # 🟢 bu çalışan link
        except Exception as e:
            konsol.log(f"[red][!] t.co/lU6t0lkPKD başarısız: {e}")
            return self.redirect_gec("https://t.co/MTLoNVkGQN")

    def yeni_domaini_al(self, eldeki_domain: str) -> str:
        try:
            yeni_domain = self.redirect_gec(eldeki_domain)
        except Exception:
            konsol.log("[red][!] `redirect_gec(eldeki_domain)` başarısız, bit.ly deneniyor.")
            try:
                yeni_domain = self.trgoals_domaini_al()
            except Exception:
                konsol.log("[red][!] bit.ly ve yedekler başarısız, rakam tahmini yapılıyor.")
                rakam = int(re.search(r'trgoals(\d+)', eldeki_domain).group(1)) + 1
                yeni_domain = f"https://trgoals{rakam}.xyz"
        return yeni_domain

    def m3u_guncelle(self):
        eldeki_domain = self.referer_domainini_al()
        konsol.log(f"[yellow][~] Bilinen Domain : {eldeki_domain}")

        yeni_domain = self.yeni_domaini_al(eldeki_domain)
        konsol.log(f"[green][+] Yeni Domain    : {yeni_domain}")

        kontrol_url = f"{yeni_domain}/channel.html?id=yayin1"
        with open(self.m3u_dosyasi, "r") as dosya:
            m3u_icerik = dosya.read()

        if not (eski_yayin_url := re.search(r'https?:\/\/[^\/]+\.(workers\.dev|shop|click|lat|sbs)\/?', m3u_icerik)):
            raise ValueError("M3U dosyasında eski yayın URL'si bulunamadı!")

        eski_yayin_url = eski_yayin_url[0]
        konsol.log(f"[yellow][~] Eski Yayın URL : {eski_yayin_url}")

        response = self.httpx.get(kontrol_url, follow_redirects=True)
        if not (yayin_ara := re.search(r'(?:var|let|const)\s+baseurl\s*=\s*"(https?://[^"]+)"', response.text)):
            secici = Selector(response.text)
            baslik = secici.xpath("//title/text()").get()
            if baslik == "404 Not Found":
                yayin_url = eski_yayin_url
                konsol.log("[yellow][!] 404 hatası, eski değerler korunuyor")
            else:
                raise ValueError("Base URL bulunamadı!")
        else:
            yayin_url = yayin_ara[1]
            konsol.log(f"[green][+] Yeni Yayın URL : {yayin_url}")

        yeni_m3u_icerik = m3u_icerik.replace(eski_yayin_url, yayin_url)
        yeni_m3u_icerik = yeni_m3u_icerik.replace(eldeki_domain, yeni_domain)
        with open(self.m3u_dosyasi, "w") as dosya:
            dosya.write(yeni_m3u_icerik)
        konsol.log("[green][✓] M3U dosyası başarıyla güncellendi!")

if __name__ == "__main__":
    guncelleyici = TRGoals("k.m3u")
    guncelleyici.m3u_guncelle()
