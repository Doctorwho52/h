from Kekik.cli import konsol
from httpx import Client
from parsel import Selector
from urllib.parse import urlparse
import re

class TRGoals:
    def __init__(self, m3u_dosyasi):
        self.m3u_dosyasi = m3u_dosyasi
        self.httpx = Client(timeout=10, verify=False)

    def extract_trgoals_num(self, url: str):
        m = re.search(r'trgoals(\d+)', url)
        return int(m.group(1)) if m else None

    def meta_refresh_bul(self, html):
        meta = re.search(r'<meta\s+http-equiv=["\']refresh["\'][^>]*content=["\'][^"\']*;URL=([^"\']+)["\']', html, re.I)
        if meta:
            return meta.group(1)
        js = re.search(r'location\.replace\(["\']([^"\']+)["\']', html)
        if js:
            return js.group(1)
        return None

    def check_channel_ok(self, domain: str) -> bool:
        try:
            r = self.httpx.get(f"{domain.rstrip('/')}/channel.html?id=yayin1", follow_redirects=True, timeout=10)
            if r.status_code == 404:
                return False
            if re.search(r'(?:var|let|const)\s+baseurl\s*=\s*"(https?://[^"]+)"', r.text) or \
               re.search(r'player\(\s*\[\s*\{"file":"https?://[^"]+"', r.text):
                return True
            title = re.search(r'<title[^>]*>(.*?)</title>', r.text, re.I|re.S)
            if title and "404" in title.group(1):
                return False
            return len(r.text) > 300
        except Exception:
            return False

    def redirect_gec(self, url: str, max_depth=5):
        konsol.log(f"[cyan][~] redirect_gec çağrıldı: {url}")
        current = url
        for i in range(max_depth):
            try:
                response = self.httpx.get(current, follow_redirects=True)
            except Exception as e:
                raise ValueError(f"Redirect sırasında hata oluştu: {e}")

            for u in [*map(str, [r.url for r in response.history]), str(response.url)]:
                if "trgoals" in u and not u.endswith("trgoalsgiris.xyz"):
                    konsol.log(f"[green][+] TRGoals domain bulundu: {u}")
                    return u.strip("/")

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

            if "t.co/" in str(response.url):
                current = str(response.url)
                konsol.log(f"[yellow][~] t.co yönlendirmesi tekrar denenecek: {current}")
                continue

            break

        raise ValueError("Redirect zincirinde 'trgoals' içeren bir link bulunamadı!")

    def trgoals_domaini_al(self):
        konsol.log("[cyan][~] bit.ly üzerinden domain aranıyor...")
        try:
            d = self.redirect_gec("https://bit.ly/m/taraftarium24w")
            if "trgoals" in d:
                return d
        except Exception as e:
            konsol.log(f"[red][!] bit.ly başarısız: {e}")

        konsol.log("[yellow][~] Yedek linke geçiliyor...")
        return self.redirect_gec("https://t.co/lU6t0lkPKD")

    def yeni_domaini_al(self, eldeki_domain: str) -> str:
        adaylar = []

        for link in [
            "https://bit.ly/m/taraftarium24w",
            "https://t.co/lU6t0lkPKD"
        ]:
            try:
                d = self.redirect_gec(link)
                if d and "trgoals" in d and not d.endswith("trgoalsgiris.xyz"):
                    adaylar.append(d.rstrip("/"))
            except Exception:
                pass

        try:
            d = self.redirect_gec(eldeki_domain)
            if d and "trgoals" in d and not d.endswith("trgoalsgiris.xyz"):
                adaylar.append(d.rstrip("/"))
        except Exception:
            pass

        if not adaylar:
            n = self.extract_trgoals_num(eldeki_domain)
            if n:
                for g in [n+1, n+2, n+3, n-1]:
                    adaylar.append(f"https://trgoals{g}.xyz")

        uniq = list(dict.fromkeys(adaylar))
        uniq.sort(key=lambda u: self.extract_trgoals_num(u) or 0, reverse=True)

        for u in uniq:
            if self.check_channel_ok(u):
                konsol.log(f"[green][+] Geçerli domain bulundu: {u}")
                return u

        konsol.log(f"[yellow][!] Geçerli domain bulunamadı, ilk adayı kullanıyor: {uniq[0]}")
        return uniq[0]

    def referer_domainini_al(self):
        pattern = r'#EXTVLCOPT:http-referrer=(https?://[^/]*trgoals[^/]*\.[^\s/]+)'
        with open(self.m3u_dosyasi, "r") as dosya:
            icerik = dosya.read()
        if eslesme := re.search(pattern, icerik):
            return eslesme[1]
        raise ValueError("M3U dosyasında 'trgoals' içeren referer domain bulunamadı!")

    def m3u_guncelle(self):
        eldeki = self.referer_domainini_al()
        konsol.log(f"[yellow][~] Bilinen Domain : {eldeki}")

        yeni = self.yeni_domaini_al(eldeki)
        konsol.log(f"[green][+] Yeni Domain    : {yeni}")

        kontrol_url = f"{yeni}/channel.html?id=yayin1"
        with open(self.m3u_dosyasi, "r") as dosya:
            m3u = dosya.read()

        if not (match := re.search(r'https?:\/\/[^\/]+\.(workers\.dev|shop|click|lat|sbs)\/?', m3u)):
            raise ValueError("M3U dosyasında eski yayın URL'si bulunamadı!")

        eski_yayin = match[0]
        konsol.log(f"[yellow][~] Eski Yayın URL : {eski_yayin}")

        r = self.httpx.get(kontrol_url, follow_redirects=True)
        if not (m := re.search(r'(?:var|let|const)\s+baseurl\s*=\s*"(https?://[^"]+)"', r.text)):
            player = re.search(r'player\(\s*\[\s*\{"file":"(https?://[^"]+)"', r.text)
            if player:
                yayin = player.group(1)
                konsol.log(f"[green][+] Yeni Yayın URL (player): {yayin}")
            else:
                konsol.log("[yellow][!] Base URL veya player bulunamadı, eski değer korunuyor")
                yayin = eski_yayin
        else:
            yayin = m[1]
            konsol.log(f"[green][+] Yeni Yayın URL : {yayin}")

        yeni_icerik = m3u.replace(eski_yayin, yayin).replace(eldeki, yeni)
        with open(self.m3u_dosyasi, "w") as dosya:
            dosya.write(yeni_icerik)
        konsol.log("[green][✓] M3U dosyası başarıyla güncellendi!")

if __name__ == "__main__":
    guncelleyici = TRGoals("k.m3u")
    guncelleyici.m3u_guncelle()
