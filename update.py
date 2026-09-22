import requests
from datetime import datetime
import calendar

def update_calendar():
    # Şu anki yılı ve ayı al
    now = datetime.now()
    year = now.year
    month = now.month

    # O ayın kaç gün sürdüğünü bul (örn: Eylül için 30, Ekim için 31)
    _, last_day = calendar.monthrange(year, month)

    # Başlangıç ve bitiş tarihlerini Baro'nun istediği formatta oluştur
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    # Baro'nun doğrudan ics dosyasını üreten gizli API linki
    download_url = f"https://istanbulbarosu.org.tr/api/events/export?startDate={start_date}&endDate={end_date}"
    
    print(f"Takvim şu adresten indiriliyor: {download_url}")

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/calendar"
    }

    try:
        # Dosyayı indir
        response = requests.get(download_url, headers=HEADERS)
        
        # Eğer indirme başarılıysa (200 OK) ve içi boş değilse
        if response.status_code == 200 and len(response.content) > 100:
            with open("baro_takvim.ics", "wb") as f:
                f.write(response.content)
            print("Harika! Takvim başarıyla baro_takvim.ics olarak indirildi.")
        else:
            print(f"Hata: Takvim indirilemedi. Sunucu kodu: {response.status_code}")
            
    except Exception as e:
        print(f"Bir hata oluştu: {e}")

if __name__ == "__main__":
    update_calendar()
