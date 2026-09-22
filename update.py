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
        try:
            # Sitenin UTC olarak verdiği orijinal başlangıç tarihi (Örn: 06:00 Z -> TRT 09:00)
            dt_start_orig = datetime.strptime(event['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
            dt_start_local = dt_start_orig + timedelta(hours=3) # Türkiye saatine çevir
            
            base_year = dt_start_local.year
            base_month = dt_start_local.month
            
            # Etkinliğin günleri (Özel olarak bulunduysa onu, yoksa tek günü kullan)
            days_to_process = event.get('extracted_days', [dt_start_local.day])
            
            # Etkinliğin saatleri (Özel olarak bulunduysa onu, yoksa varsayılan 2 saati kullan)
            start_time_str = event.get('custom_start_time')
            end_time_str = event.get('custom_end_time')
            
            if start_time_str and end_time_str:
                sh, sm = map(int, start_time_str.split(':'))
                eh, em = map(int, end_time_str.split(':'))
            else:
                sh, sm = dt_start_local.hour, dt_start_local.minute
                eh, em = (dt_start_local + timedelta(hours=2)).hour, (dt_start_local + timedelta(hours=2)).minute
                
            base_uid = str(uuid.uuid4())
            
            for i, day in enumerate(days_to_process):
                lines.append("BEGIN:VEVENT")
                current_uid = f"{base_uid}-part{i}@istanbulbarosu.org.tr"
                lines.append(f"UID:{current_uid}")
                lines.append(f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
                
                try:
                    # Bulunan gün ve saati birleştirerek o günkü takvim bloğunu oluştur
                    local_start = datetime(base_year, base_month, day, sh, sm)
                    local_end = datetime(base_year, base_month, day, eh, em)
                    
                    # ICS formatı gereği tekrar UTC'ye çevirip kaydet (-3 saat)
                    utc_start = local_start - timedelta(hours=3)
                    utc_end = local_end - timedelta(hours=3)
                    
                    lines.append(f"DTSTART:{utc_start.strftime('%Y%m%dT%H%M%SZ')}")
                    lines.append(f"DTEND:{utc_end.strftime('%Y%m%dT%H%M%SZ')}")
                except ValueError:
                    # Olası bir tarih hatasında (örn ayın gününü aşarsa) orijinal tarihe dön
                    lines.append(f"DTSTART:{dt_start_orig.strftime('%Y%m%dT%H%M%SZ')}")
                    lines.append(f"DTEND:{(dt_start_orig + timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')}")
                    
                title = event['title'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
                lines.append(f"SUMMARY:{title}")
                
                url = f"https://istanbulbarosu.org.tr{event['url']}"
                desc_text = f"Detaylar için tıklayın: {url}"
                
                # Açıklama kısmına sistemin ne okuduğunu not düşelim
                if 'extracted_days' in event or 'custom_start_time' in event:
                    days_str = ", ".join(map(str, days_to_process))
                    month_name = event.get('extracted_month', '')
                    time_str = f"{start_time_str}-{end_time_str}" if start_time_str else f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
                    desc_text = f"Özel Takvim Taraması: {days_str} {month_name} | Saat: {time_str}\\n{desc_text}"
                
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    all_events = []
    page = 1
    print("Baro'nun etkinlik sayfaları taranıyor...")
    
    aylar = "ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık"
    
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
            else:
                continue 
                
            map_pin_svg = a_tag.find('svg', class_=lambda c: c and 'lucide-map-pin' in c)
            if map_pin_svg:
                parent_div = map_pin_svg.parent
                if parent_div:
                    loc_text = parent_div.text.strip()
                    if loc_text:
                        event_data['location'] = loc_text
            
            # --- DERİN TARAMA (DEEP SCRAPE) ---
            if event_data['url']:
                detail_url = f"https://istanbulbarosu.org.tr{event_data['url']}"
                try:
                    detail_response = requests.get(detail_url, headers=headers)
                    if detail_response.status_code == 200:
                        detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                        detail_text = detail_soup.text.lower()
                        
                        # 1. TARİH AVCISI (Örn: "7, 8, 14 ve 15 ekim" veya "26-27 eylül")
                        date_match = re.search(fr'\b(\d{{1,2}}(?:\s*(?:-|/|,|ve|ile)\s*\d{{1,2}})+)\s+({aylar})\b', detail_text)
                        if date_match:
                            days_str = date_match.group(1)
                            # İçindeki tüm sayıları listeye al
                            extracted_days = [int(d) for d in re.findall(r'\d+', days_str)]
                            # Tekrar eden günleri çıkar ve sırala
                            extracted_days = sorted(list(set(extracted_days)))
                            
                            if len(extracted_days) > 1:
                                event_data['extracted_days'] = extracted_days
                                event_data['extracted_month'] = date_match.group(2).capitalize()
                                print(f"-> Çoklu Gün Bulundu: {event_data['title']} ({extracted_days})")
                                
                        # 2. SAAT AVCISI (Örn: "09:00 - 17:00" veya "09.00-17.30")
                        time_match = re.search(r'(\d{1,2}[:.]\d{2})\s*-\s*(\d{1,2}[:.]\d{2})', detail_text)
                        if time_match:
                            event_data['custom_start_time'] = time_match.group(1).replace('.', ':')
                            event_data['custom_end_time'] = time_match.group(2).replace('.', ':')
                            print(f"-> Özel Saat Bulundu: {event_data['custom_start_time']} - {event_data['custom_end_time']}")
                            
                except Exception as e:
                    print(f"Detay sayfası okunamadı: {e}")
            
            # Sunucuyu yormamak için her detay sayfasında 0.5 saniye bekle
            time.sleep(0.5)
            all_events.append(event_data)
            
        page += 1
        
    if all_events:
        ics_content = create_ics(all_events)
        with open("baro_takvim.ics", "w", encoding="utf-8") as f:
            f.write(ics_content)
        print("\nTakvim başarıyla oluşturuldu!")

if __name__ == "__main__":
    update_calendar()
