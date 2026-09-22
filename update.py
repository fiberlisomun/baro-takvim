import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import uuid
import re
import time

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
        dt_start_orig = datetime.strptime(event['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
        base_date_local = dt_start_orig + timedelta(hours=3) 
        
        # Gün listesi (Varsayılan olarak sadece kendi gününü içerir)
        offsets = event.get('offsets', [0])
        
        # Saatleri ayarla (Bulunduysa özel saat, yoksa varsayılan 2 saat)
        if event.get('start_time'):
            sh, sm = map(int, event['start_time'].split(':'))
            eh, em = map(int, event['end_time'].split(':'))
        else:
            sh, sm = base_date_local.hour, base_date_local.minute
            eh, em = (base_date_local + timedelta(hours=2)).hour, (base_date_local + timedelta(hours=2)).minute
            
        base_uid = str(uuid.uuid4())
        
        for i, offset in enumerate(offsets):
            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{base_uid}-gun{i}@istanbulbarosu.org.tr")
            lines.append(f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
            
            # Yeni tarihi hesapla
            current_date = base_date_local + timedelta(days=offset)
            
            try:
                local_start = current_date.replace(hour=sh, minute=sm, second=0)
                local_end = current_date.replace(hour=eh, minute=em, second=0)
            except ValueError:
                local_start = current_date
                local_end = current_date + timedelta(hours=2)
            
            # UTC'ye çevir (-3 saat)
            utc_start = local_start - timedelta(hours=3)
            utc_end = local_end - timedelta(hours=3)
            
            lines.append(f"DTSTART:{utc_start.strftime('%Y%m%dT%H%M%SZ')}")
            lines.append(f"DTEND:{utc_end.strftime('%Y%m%dT%H%M%SZ')}")
            
            title = event['title'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
            lines.append(f"SUMMARY:{title}")
            
            url = f"https://istanbulbarosu.org.tr{event['url']}"
            desc_text = f"Detaylar için tıklayın: {url}"
            
            if 'start_time' in event or len(offsets) > 1:
                time_info = f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
                desc_text = f"✅ Sistem Taraması: {len(offsets)} Günlük | Saat: {time_info}\\n{desc_text}"
            
            lines.append(f"DESCRIPTION:{desc_text}")
            lines.append(f"URL:{url}")
            
            if event.get('location'):
                loc = event['location'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
                lines.append(f"LOCATION:{loc}")
                
            lines.append("END:VEVENT")
            
    lines.append("END:VCALENDAR")
    return "\n".join(lines)

def update_calendar():
    base_url = "https://istanbulbarosu.org.tr/etkinlikler"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    all_events = []
    print("Baro'nun etkinlik sayfaları taranıyor...")
    aylar = "ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık"
    
    page = 1
    while True:
        url = f"{base_url}?page={page}"
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except:
            break
            
        soup = BeautifulSoup(response.text, 'html.parser')
        event_links = soup.find_all('a', class_=lambda c: c and 'group' in c and 'bg-card' in c)
        
        if not event_links:
            break
            
        for a_tag in event_links:
            event_data = {'url': a_tag.get('href', '')}
            h3_tag = a_tag.find('h3')
            event_data['title'] = h3_tag.text.strip() if h3_tag else "İsimsiz Etkinlik"
            
            time_tag = a_tag.find('time')
            if time_tag and time_tag.has_attr('datetime'):
                event_data['datetime'] = time_tag['datetime']
            else:
                continue 
                
            map_pin = a_tag.find('svg', class_=lambda c: c and 'lucide-map-pin' in c)
            if map_pin and map_pin.parent:
                event_data['location'] = map_pin.parent.text.strip()
            
            event_data['offsets'] = [0]
            
            if event_data['url']:
                detail_url = f"https://istanbulbarosu.org.tr{event_data['url']}"
                try:
                    resp = requests.get(detail_url, headers=headers)
                    if resp.status_code == 200:
                        d_soup = BeautifulSoup(resp.text, 'html.parser')
                        
                        # Metni tek satır yapıp boşlukları temizle
                        text = d_soup.text.lower().replace('\n', ' ').replace('\r', ' ')
                        text = re.sub(r'\s+', ' ', text)
                        
                        dt_orig = datetime.strptime(event_data['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
                        base_day = (dt_orig + timedelta(hours=3)).day
                        extracted_days = {base_day}
                        
                        # YÖNTEM 1: Daha önce çalışan eski yöntem ("26-27 Eylül")
                        simple_pattern = fr'\b(\d{{1,2}})\s*(?:-|–|ile)\s*(\d{{1,2}})\s*(?:{aylar})'
                        for match in re.finditer(simple_pattern, text):
                            d1, d2 = int(match.group(1)), int(match.group(2))
                            if base_day in (d1, d2):
                                extracted_days.update(range(min(d1, d2), max(d1, d2) + 1))
                        
                        # YÖNTEM 2: Virgüllü aylar ("7, 8, 14 ve 15 Ekim")
                        list_pattern = fr'((?:\d{{1,2}}\s*(?:,|/|ve|ile|-|–)\s*)+\d{{1,2}})\s*(?:{aylar})'
                        for match in re.finditer(list_pattern, text):
                            nums = [int(x) for x in re.findall(r'\d+', match.group(1))]
                            if base_day in nums:
                                extracted_days.update(nums)
                        
                        # YÖNTEM 3: Uzak Mesafeli ("26 Eylül Cmt - 27 Eylül Pazar")
                        range_pattern = fr'\b{base_day}\b(?:[a-zçğıöşü0-9\s]{{0,40}}?)(?:-|–)\s*(\d{{1,2}})\b'
                        for match in re.finditer(range_pattern, text):
                            d2 = int(match.group(1))
                            if d2 > base_day and (d2 - base_day) <= 15:
                                extracted_days.update(range(base_day, d2 + 1))
                        
                        # Farkları kaydet
                        offsets = []
                        for d in sorted(list(extracted_days)):
                            if d >= base_day and (d - base_day) <= 15:
                                offsets.append(d - base_day)
                        event_data['offsets'] = sorted(list(set(offsets)))
                        
                        # SAAT AVCISI ("09:00 - 17:00")
                        time_match = re.search(r'\b(\d{1,2}[:.]\d{2})\s*(?:-|–|ile|ila|/)\s*(\d{1,2}[:.]\d{2})\b', text)
                        if time_match:
                            event_data['start_time'] = time_match.group(1).replace('.', ':')
                            event_data['end_time'] = time_match.group(2).replace('.', ':')
                            
                except Exception:
                    pass
            
            time.sleep(0.5)
            all_events.append(event_data)
            
        page += 1
        
    if all_events:
        with open("baro_takvim.ics", "w", encoding="utf-8") as f:
            f.write(create_ics(all_events))
        print("Takvim başarıyla oluşturuldu!")

if __name__ == "__main__":
    update_calendar()
