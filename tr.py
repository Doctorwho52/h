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

    # 🔹 META ve JS redirect destekli yardımcı
    def meta_refresh_bul(self, html_content):
        meta_refresh_pattern = r'<meta\s+http-equiv=["\']refresh["\'][^>]*content=["\'][^"\']*;URL=([^"\']+)["\']'
        match = re.search(meta_refresh_pattern, html_content, re.IGNORECASE)
        if match:
            return match.group(1)
        js_redirect_pattern = r'location\.replace\(["\']([^"\']+)["\']'
        match = re.search(js_redirect_pattern, html_content)
        if match:
            return match.group(1)
        return None

    # 🔹 Asıl fark burada: derin redirect çözümü
    def redirect_gec(self, redirect_url: str, max_depth=5):
        konsol.log(f"[cyan][~] redirect_gec çağrıldı: {redirect_url}")
        current_url = redirect_url
        visited = set()

        for i in range(max_depth):
            if current_url in visited:
                break
            visited.add(current_url)

            try:
                response = self.httpx.get(current_url, follow_redirects=True)
            except Exception as e:
                raise ValueError(f"Redirect sırasında hata oluştu: {e}")

            # Tüm redirect geçmişi
            tum_url_listesi = [str(r.url) for r in response.history] + [str(response.url)]
            for url in tum_url_listesi:
                if "trgoals" in url and not url.endswith("trgoalsgiris.xyz"):
                    return url.strip("/")

            # HTML içinde meta veya JS redirect var mı?
            next_url = self.meta_refresh_bul(response.text)
            if next_url:
                # relative ise absolute yap
                if next_url.startswith("/"):
                    parsed = urlparse(current_url)
                    next_url = f"{parsed.scheme}://{parsed.netloc}{next_url}"
                elif not next_url.startswith("http"):
                    parsed = urlparse(current_url)
                    next_url = f"{parsed.scheme}://{parsed.netloc}/{next_url.lstrip('/')}"
                konsol.log(f"[yellow][~] Meta/JS redirect bulundu: {next_url}")
                current_url = next_url
                continue

            # Eğer t.co içindeyse bir tur daha dön
            if "t.co/" in str(response.url):
                current_url = str(response.url)
                konsol.log(f"[yellow][~] t.co yönlendirmesi tekrar denenecek: {current_url}")
                continue

            konsol.log(f"[yellow][~] Daha fazla redirect bulunamadı. Son URL: {response.url}")
            break

        raise ValueError("Redirect zincirinde 'trgoals' içeren bir link bulunamadı!")

    def trgoals_domaini_al(self):
        redirect_url = "https://bit.ly/m/taraftarium24w"
        deneme = 0
        while "bit.ly" in redirect_url and deneme < 5:
            try:
                redirect_url = self.redirect_gec(redirect_url)
            except Exception as e:
                konsol.log(f"[red][!] redirect_gec hata: {e}")
                break
            deneme += 1

        if "bit.ly" in redirect_url or "error" in redirect_url:
            konsol.log("[yellow][!] 5 denemeden sonra bit.ly çözülemedi, yedek linke geçiliyor...")
            try:
                redirect_url = self.redirect_gec("https://t.co/aOAO1eIsqE")
            except Exception as e:
                raise ValueError(f"Yedek linkten de domain alınamadı: {e}")

        return redirect_url

    def yeni_domaini_al(self, eldeki_domain: str) -> str:
        def check_domain(domain: str) -> str:
            if domain == "https://trgoalsgiris.xyz":
                raise ValueError("Yeni domain alınamadı")
            return domain

        try:
            yeni_domain = check_domain(self.redirect_gec(eldeki_domain))
        except Exception:
            konsol.log("[red][!] `redirect_gec(eldeki_domain)` fonksiyonunda hata oluştu.")
            try:
                yeni_domain = check_domain(self.trgoals_domaini_al())
            except Exception:
                konsol.log("[red][!] `trgoals_domaini_al` fonksiyonunda hata oluştu.")
                try:
                    yeni_domain = check_domain(self.redirect_gec("https://t.co/MTLoNVkGQN"))
                except Exception:
                    konsol.log("[red][!] `redirect_gec('https://t.co/MTLoNVkGQN')` fonksiyonunda hata oluştu.")
                    rakam = int(eldeki_domain.split("trgoals")[1].split(".")[0]) + 1
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
                yeni_domain = eldeki_domain
                yayin_url   = eski_yayin_url  
                konsol.log("[yellow][!] 404 hatası, eski değerler korunuyor")
            else:
                konsol.print(response.text)
                raise ValueError("Base URL bulunamadı!")
        else:
            yayin_url = yayin_ara[1]
            konsol.log(f"[green][+] Yeni Yayın URL : {yayin_url}")

        yeni_m3u_icerik = m3u_icerik.replace(eski_yayin_url, yayin_url)
        yeni_m3u_icerik = yeni_m3u_icerik.replace(eldeki_domain, yeni_domain)

        with open(self.m3u_dosyasi, "w") as dosya:
            dosya.write(yeni_m3u_icerik)

if __name__ == "__main__":
    guncelleyici = TRGoals("k.m3u")
    guncelleyici.m3u_guncelle()
