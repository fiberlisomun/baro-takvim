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
        # Sitenin UTC olarak gönderdiği orijinal saat
        dt_start_orig = datetime.strptime(event['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
        base_date_local = dt_start_orig + timedelta(hours=3) # Türkiye saatine çevir
        
        offsets = event.get('offsets', [0])
        start_time_str = event.get('start_time')
        end_time_str = event.get('end_time')
        
        if start_time_str and end_time_str:
            sh, sm = map(int, start_time_str.split(':'))
            eh, em = map(int, end_time_str.split(':'))
        else:
            sh, sm = base_date_local.hour, base_date_local.minute
            eh, em = (base_date_local + timedelta(hours=2)).hour, (base_date_local + timedelta(hours=2)).minute
            
        base_uid = str(uuid.uuid4())
        
        for i, offset in enumerate(offsets):
            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{base_uid}-gun{i}@istanbulbarosu.org.tr")
            lines.append(f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
            
            # Etkinliğin o günkü yerel (Türkiye) tarihi ve saati
            current_date_local = base_date_local + timedelta(days=offset)
            
            try:
                local_start = current_date_local.replace(hour=sh, minute=sm, second=0)
                local_end = current_date_local.replace(hour=eh, minute=em, second=0)
            except ValueError:
                local_start = current_date_local
                local_end = current_date_local + timedelta(hours=2)
            
            # ICS standardı için tekrar UTC'ye (-3 saat) çevir
            utc_start = local_start - timedelta(hours=3)
            utc_end = local_end - timedelta(hours=3)
            
            lines.append(f"DTSTART:{utc_start.strftime('%Y%m%dT%H%M%SZ')}")
            lines.append(f"DTEND:{utc_end.strftime('%Y%m%dT%H%M%SZ')}")
            
            title = event['title'].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
            lines.append(f"SUMMARY:{title}")
            
            url = f"https://istanbulbarosu.org.tr{event['url']}"
            desc_text = f"Detaylar için tıklayın: {url}"
            
            if 'offsets' in event or 'start_time' in event:
                time_info = f"{start_time_str}-{end_time_str}" if start_time_str else f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
                desc_text = f"✅ Takvim Botu: {len(offsets)} Gün | Saat: {time_info}\\n{desc_text}"
            
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
            event_data['offsets'] = [0]
            if event_data['url']:
                detail_url = f"https://istanbulbarosu.org.tr{event_data['url']}"
                try:
                    detail_response = requests.get(detail_url, headers=headers)
                    if detail_response.status_code == 200:
                        detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                        
                        # Enter/Alt satır hatalarını yok etmek için metni tek satıra indirgiyoruz
                        detail_text = detail_soup.text.lower().replace('\n', ' ').replace('\r', ' ')
                        
                        dt_start_orig = datetime.strptime(event_data['datetime'], "%Y-%m-%dT%H:%M:%S.%fZ")
                        base_date_local = dt_start_orig + timedelta(hours=3)
                        base_day = base_date_local.day
                        extracted_days = {base_day}
                        
                        # YÖNTEM 1: "26 Eylül 2026 Cumartesi - 27 Eylül 2026 Pazar" formatını avla
                        # İki ay kelimesi arasında en fazla 40 karakter ve bir tire/bağlaç olmasına izin veriyoruz.
                        pattern_full_date = fr'\b(\d{{1,2}})\s+(?:{aylar}).{{0,40}}?(?:-|–|ila|ile)\s*(\d{{1,2}})\s+(?:{aylar})\b'
                        for match in re.finditer(pattern_full_date, detail_text):
                            d1, d2 = int(match.group(1)), int(match.group(2))
                            if base_day in (d1, d2) and abs(d1 - d2) <= 15:
                                extracted_days.update(range(min(d1, d2), max(d1, d2) + 1))
                                
                        # YÖNTEM 2: "26-27 Eylül" veya "7, 8, 14 ve 15 Ekim" formatını avla
                        pattern_compact = fr'((?:\b\d{{1,2}}\b\s*(?:-|–|/|,|ve|ile)\s*)*\b\d{{1,2}}\b)\s*(?:{aylar})\b'
                        for match in re.finditer(pattern_compact, detail_text):
                            nums = [int(x) for x in re.findall(r'\d+', match.group(1))]
                            if base_day in nums:
                                extracted_days.update(nums)
                                if ("-" in match.group(1) or "–" in match.group(1)) and len(nums) >= 2:
                                    extracted_days.update(range(min(nums), max(nums) + 1))
                        
                        # Günleri takvim formatı için ofset (fark) günlerine dönüştür
                        offsets = []
                        _, month_len = calendar.monthrange(base_date_local.year, base_date_local.month)
                        for d in sorted(list(extracted_days)):
                            if d >= base_day:
                                offsets.append(d - base_day)
                            elif d < base_day and (month_len - base_day + d) <= 15: 
                                offsets.append(month_len - base_day + d)
                                
                        # 15 günden fazla atlamaları (yanlış tarihleri) engelle
                        event_data['offsets'] = [off for off in sorted(list(set(offsets))) if 0 <= off <= 15]
                        
                        # YÖNTEM 3: Saat Avcısı (09:00 - 17:00 veya 09.00-17.30)
                        time_match = re.search(r'\b(\d{1,2}[:.]\d{2})\s*(?:-|–|ile|ila|/)\s*(\d{1,2}[:.]\d{2})\b', detail_text)
                        if time_match:
                            event_data['start_time'] = time_match.group(1).replace('.', ':')
                            event_data['end_time'] = time_match.group(2).replace('.', ':')
                            
                except Exception as e:
                    print(f"Detay sayfası okunamadı: {e}")
            
            # Sunucuyu yormamak için kısa bekleme
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
