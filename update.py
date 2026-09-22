import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://istanbulbarosu.org.tr"
EVENTS_URL = f"{BASE_URL}/etkinlikler"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def update_calendar():
    response = requests.get(EVENTS_URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, 'html.parser')

    ics_url = None
    # Sayfadaki tüm linkleri tara
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.text.lower()
        # "takvim" yazısı içeren veya .ics uzantılı linki bul
        if '.ics' in href or 'takvim' in text:
            ics_url = urljoin(BASE_URL, href)
            break

    if not ics_url:
        print("Takvim linki bulunamadı.")
        return

    print(f"Takvim linki bulundu: {ics_url}")

    # Takvimi indir ve kaydet
    ics_response = requests.get(ics_url, headers=HEADERS)
    with open("baro_takvim.ics", "wb") as f:
        f.write(ics_response.content)
    print("Takvim başarıyla baro_takvim.ics olarak güncellendi.")

if __name__ == "__main__":
    update_calendar()
