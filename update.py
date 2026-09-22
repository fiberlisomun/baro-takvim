import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import uuid
import re
import time
import calendar

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
            
            # Etkinliğin kaç günlük ofsetleri olduğu (Örn: 2 günlükse [0, 1] gelir)
            offsets_to_process = event.get('extracted_offsets', [0])
            
            start_time_str = event.get('custom_start_time')
            end_time_str = event.get('custom_end_time')
            
            if start_time_str and end_time_str:
                sh, sm = map(int, start_time_str.split(':'))
                eh, em = map(int, end_time_str.split(':'))
            else:
                sh, sm = dt_start_local.hour, dt_start_local.minute
                eh, em = (dt_start_local + timedelta(hours=2)).hour, (dt_start_local + timedelta(hours=2)).minute
                
            base_uid = str(uuid.uuid4())
            
            for i, offset in enumerate(offsets_to_process):
                lines.append("BEGIN:VEVENT")
                current_uid = f"{base_uid}-part{i}@istanbulbarosu.org.tr"
                lines.append(f"UID:{current_uid}")
                lines.append(f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
                
                try:
                    # Ana tarihe gün farkını (offset) ekleyerek o günkü tarihi bul
                    current_date_local = dt_start_local + timedelta(days=offset)
                    
                    local_start = current_date_local.replace(hour=sh, minute=sm)
                    local_end = current_date_local.replace(hour=eh, minute=em)
                    
                    # ICS formatı gereği tekrar UTC'ye çevirip kaydet (-3 saat)
                    utc_start = local_start - timedelta(hours=3)
                    utc_end = local_end - timedelta(hours=3)
                    
                    lines.append(f"DTSTART:{utc_start.strftime('%Y%m%dT%H%M%SZ')}")
                    lines.append(f"DTEND:{utc_end.strftime('%Y%m%dT%H%M%SZ')}")
                except ValueError:
                    lines.append(f"DTSTART:{dt_start_orig.strftime('%Y%m%dT%H%M%SZ')}")
                    lines.append(f"DTEND:{(dt_start_orig + timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')}")
                    
                title = event['title'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
                lines.append(f"SUMMARY:{title}")
                
                url = f"https://istanbulbarosu.org.tr{event['url']}"
                desc_text = f"Detaylar için tıklayın: {url}"
                
                # Açıklamaya tarama detaylarını ekle
                if 'extracted_offsets' in event or 'custom_start_time' in event:
                    time_str = f"{start_time_str}-{end_time_str}" if start_time_str else "Standart Saat"
                    desc_text = f"Özel Takvim Taraması: {len(offsets_to_process)} Günlük Etkinlik | Saat: {time_str}\\n{desc_text}"
                
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
                # Ana sayfadaki gerçek (orijinal) günü kaydediyoruz
                dt_start_orig = datetime.strptime(event_data['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
                base_day = (dt_start_orig + timedelta(hours=3)).day
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
                        
                        # 1. TARİH AVCISI (Sadece orijinal günü barındıran tarih aralıklarını kabul eder)
                        date_matches = re.finditer(fr'\b(\d{{1,2}}(?:\s*(?:-|/|,|ve|ile|–)\s*\d{{1,2}})+)\s+({aylar})\b', detail_text)
                        
                        for match in date_matches:
                            days_str = match.group(1)
                            found_numbers = [int(d) for d in re.findall(r'\d+', days_str)]
                            is_range = bool(re.search(r'-|–|ile', days_str)) and len(found_numbers) == 2
                            
                            # EĞER BULUNAN TARİH GRUBU ANA GÜNÜ (Örn: 26) İÇERİYORSA KABUL ET!
                            if base_day in found_numbers or (is_range and found_numbers[0] <= base_day <= found_numbers[1]):
                                if is_range:
                                    days_list = list(range(found_numbers[0], found_numbers[1] + 1))
                                else:
                                    days_list = sorted(list(set(found_numbers)))
                                    
                                offsets = []
                                for d in days_list:
                                    if d >= base_day:
                                        offsets.append(d - base_day)
                                    else:
                                        # Aydan aya sarkma hesaplaması (Örn: 30'undan 1'ine)
                                        _, month_len = calendar.monthrange(dt_start_orig.year, dt_start_orig.month)
                                        offsets.append((month_len - base_day) + d)
                                        
                                event_data['extracted_offsets'] = offsets
                                print(f"-> Çoklu Gün Doğrulandı: {event_data['title']} ({days_list})")
                                break # Yanlış tarihleri (örn 10,11 Ekim) bulmamak için doğruyu bulunca çık
                                
                        # 2. SAAT AVCISI
                        time_match = re.search(r'(\d{1,2}[:.]\d{2})\s*(?:-|–)\s*(\d{1,2}[:.]\d{2})', detail_text)
                        if time_match:
                            event_data['custom_start_time'] = time_match.group(1).replace('.', ':')
                            event_data['custom_end_time'] = time_match.group(2).replace('.', ':')
                            print(f"-> Özel Saat Bulundu: {event_data['custom_start_time']} - {event_data['custom_end_time']}")
                            
                except Exception as e:
                    print(f"Detay sayfası okunamadı: {e}")
            
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
