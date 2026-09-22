import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import uuid
import re

def create_ics(events):
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
        try:
            # Örnek datetime formatı: "2026-09-26T06:00:00.000Z"
            dt_start = datetime.strptime(event['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
            
            date_text = event.get('date_text', '')
            extra_days = 0
            
            # Sitede yazan metinden gün farkını bul (Örn: "26-27")
            match = re.search(r'(\d{1,2})\s*-\s*(\d{1,2})', date_text)
            if match:
                day1 = int(match.group(1))
                day2 = int(match.group(2))
                if day2 > day1:
                    extra_days = day2 - day1
                else:
                    extra_days = 1 # Aydan aya sarkma durumu
            
            base_uid = str(uuid.uuid4())
            
            # Etkinlik kaç gün sürüyorsa o kadar gün için ayrı blok (VEVENT) oluştur
            for i in range(extra_days + 1):
                lines.append("BEGIN:VEVENT")
                
                # Her blok için UID'nin farklı olması lazım ki telefon birini diğerinin üstüne yazmasın
                current_uid = f"{base_uid}-day{i}@istanbulbarosu.org.tr"
                lines.append(f"UID:{current_uid}")
                lines.append(f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
                
                # O günkü başlangıç ve bitiş saati (Her güne +1 gün ekleyerek ilerler, saat aynı kalır)
                current_start = dt_start + timedelta(days=i)
                current_end = current_start + timedelta(hours=2) # 2 saatlik etkinlik süresi
                
                lines.append(f"DTSTART:{current_start.strftime('%Y%m%dT%H%M%SZ')}")
                lines.append(f"DTEND:{current_end.strftime('%Y%m%dT%H%M%SZ')}")
                
                title = event['title'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
                lines.append(f"SUMMARY:{title}")
                
                url = f"https://istanbulbarosu.org.tr{event['url']}"
                desc_text = f"Sitedeki Tarih: {event.get('date_text', '')}\\nDetaylar için tıklayın: {url}"
                lines.append(f"DESCRIPTION:{desc_text}")
                lines.append(f"URL:{url}")
                
                if event.get('location'):
                    loc = event['location'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
                    lines.append(f"LOCATION:{loc}")
                    
                lines.append("END:VEVENT")
                
        except ValueError:
            continue
            
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
        except requests.exceptions.RequestException:
            break
            
        soup = BeautifulSoup(response.text, 'html.parser')
        event_links = soup.find_all('a', class_=lambda c: c and 'group' in c and 'bg-card' in c)
        
        if not event_links:
            break
            
        for a_tag in event_links:
            event_data = {}
            event_data['url'] = a_tag.get('href', '')
            
            h3_tag = a_tag.find('h3')
            event_data['title'] = h3_tag.text.strip() if h3_tag else "İsimsiz Etkinlik"
            
            time_tag = a_tag.find('time')
            if time_tag and time_tag.has_attr('datetime'):
                event_data['datetime'] = time_tag['datetime']
                event_data['date_text'] = time_tag.text.strip()
            else:
                continue 
                
            map_pin_svg = a_tag.find('svg', class_=lambda c: c and 'lucide-map-pin' in c)
            if map_pin_svg:
                parent_div = map_pin_svg.parent
                if parent_div:
                    loc_text = parent_div.text.strip()
                    if loc_text:
                        event_data['location'] = loc_text
            
            all_events.append(event_data)
        page += 1
        
    if all_events:
        ics_content = create_ics(all_events)
        with open("baro_takvim.ics", "w", encoding="utf-8") as f:
            f.write(ics_content)
        print("Takvim başarıyla oluşturuldu!")

if __name__ == "__main__":
    update_calendar()
