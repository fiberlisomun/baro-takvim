import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import uuid

def create_ics(events):
    """Toplanan etkinlikleri ICS formatına dönüştürür"""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Istanbul Barosu//Etkinlik Takvimi//TR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:İstanbul Barosu Etkinlikleri",
        "X-WR-TIMEZONE:Europe/Istanbul"
    ]
    
    for event in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uuid.uuid4()}@istanbulbarosu.org.tr")
        lines.append(f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
        
        # Zaman hesaplaması (Etkinliklerin genelde 2 saat sürdüğünü varsayıyoruz)
        try:
            # Örnek format: 2026-10-01T10:30:00.000Z
            dt_start = datetime.strptime(event['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
            dt_end = dt_start + timedelta(hours=2)
            
            lines.append(f"DTSTART:{dt_start.strftime('%Y%m%dT%H%M%SZ')}")
            lines.append(f"DTEND:{dt_end.strftime('%Y%m%dT%H%M%SZ')}")
        except ValueError:
            # Eğer saat formatı farklıysa atla
            continue
            
        # Başlık ve Açıklama (Güvenli format)
        title = event['title'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
        lines.append(f"SUMMARY:{title}")
        
        url = f"https://istanbulbarosu.org.tr{event['url']}"
        desc = f"Detaylar için tıklayın: {url}"
        lines.append(f"DESCRIPTION:{desc}")
        lines.append(f"URL:{url}")
        
        # Konum (varsa)
        if event.get('location'):
            loc = event['location'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
            lines.append(f"LOCATION:{loc}")
            
        lines.append("END:VEVENT")
        
    lines.append("END:VCALENDAR")
    return "\n".join(lines)

def update_calendar():
    base_url = "https://istanbulbarosu.org.tr/etkinlikler"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    all_events = []
    page = 1
    
    print("Baro'nun etkinlik sayfaları taranıyor...")
    
    while True:
        url = f"{base_url}?page={page}"
        print(f"Taranıyor: Sayfa {page}")
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Sayfa {page} yüklenirken hata oluştu: {e}")
            break
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Etkinlikleri içeren <a> etiketlerini bul (HTML yapısına uygun)
        event_links = soup.find_all('a', class_=lambda c: c and 'group' in c and 'bg-card' in c)
        
        if not event_links:
            # Bu sayfada etkinlik yoksa, son sayfaya gelmişiz demektir
            print("Tarama tamamlandı, başka etkinlik bulunamadı.")
            break
            
        for a_tag in event_links:
            event_data = {}
            
            # 1. URL
            event_data['url'] = a_tag.get('href', '')
            
            # 2. Başlık
            h3_tag = a_tag.find('h3')
            event_data['title'] = h3_tag.text.strip() if h3_tag else "İsimsiz Etkinlik"
            
            # 3. Tarih/Saat bilgisi (datetime attribute'undan)
            time_tag = a_tag.find('time')
            if time_tag and time_tag.has_attr('datetime'):
                event_data['datetime'] = time_tag['datetime']
            else:
                continue # Tarih/saat yoksa takvime ekleyemeyiz
                
            # 4. Konum (En alttaki map-pin ikonunun yanındaki span)
            # Konum span'ını bulmak için class'ında 'line-clamp-1' olanı ve içinde ikon olan div'i arıyoruz
            loc_div = a_tag.find('div', class_='mt-auto')
            if loc_div:
                loc_span = loc_div.find('span')
                if loc_span:
                    event_data['location'] = loc_span.text.strip()
            
            all_events.append(event_data)
            
        # Sonraki sayfaya geç
        page += 1
        
    print(f"Toplam {len(all_events)} etkinlik bulundu.")
    
    if all_events:
        ics_content = create_ics(all_events)
        with open("baro_takvim.ics", "w", encoding="utf-8") as f:
            f.write(ics_content)
        print("Takvim dosyası (baro_takvim.ics) başarıyla oluşturuldu!")
    else:
        print("Hiç etkinlik bulunamadığı için takvim oluşturulmadı.")

if __name__ == "__main__":
    update_calendar()
