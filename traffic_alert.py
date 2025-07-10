import requests
from bs4 import BeautifulSoup
import smtplib
import os
import json
from datetime import datetime, timedelta
from email.message import EmailMessage

# ============ CONFIG ============

NEWS_SOURCES = [
    {
        "name": "iefimerida",
        "url": "https://www.iefimerida.gr/tag/kykloforiakes-rythmiseis",
        "state_file": "seen_iefimerida.json",
        "domain": "iefimerida.gr"
    },
    {
        "name": "kathimerini",
        "url": "https://www.kathimerini.gr/tag/kykloforiakes-rythmiseis/",
        "state_file": "seen_kathimerini.json",
        "domain": "kathimerini.gr"
    }
]
POLICE_URL = "https://www.astynomia.gr/kykloforia-stous-dromous/deltio-kykloforias-attiki/"
POLICE_STATE_FILE = "seen_police.json"

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# ============ EMAIL ============

def send_email(subject, body):
    if not (EMAIL_FROM and EMAIL_TO and EMAIL_PASSWORD):
        print("Λείπουν στοιχεία email.")
        return
    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
            smtp.send_message(msg)
    except Exception as e:
        print("Αποτυχία αποστολής email:", e)

# ============ DATE LOGIC ============

def get_greek_dates():
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    # Greek forms and numeric
    today_strs = [today.strftime("%d/%m/%Y"), today.strftime("%d-%m-%Y"), "Σήμερα"]
    yesterday_strs = [yesterday.strftime("%d/%m/%Y"), yesterday.strftime("%d-%m-%Y"), "Χθες"]
    return today_strs + yesterday_strs

GREEK_DATES = get_greek_dates()

# ============ STATE UTILS ============

def load_state(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_state(filename, items):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(list(items), f, ensure_ascii=False)

# ============ NEWS SCRAPERS ============

def check_iefimerida(source):
    try:
        resp = requests.get(source["url"], timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        for article in soup.find_all("div", class_="article"):
            a = article.find("a", href=True)
            date_span = article.find("span", class_="date")
            if a and a["href"]:
                url = a["href"] if a["href"].startswith("http") else f"https://www.iefimerida.gr{a['href']}"
                title = a.get_text(strip=True)
                date_text = date_span.get_text(strip=True) if date_span else ""
                articles.append((title, url, date_text))
        return articles
    except Exception as e:
        print(f"Σφάλμα στο iefimerida: {e}")
        return []

def check_kathimerini(source):
    try:
        resp = requests.get(source["url"], timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        for article in soup.find_all("article"):
            a = article.find("a", href=True)
            time_tag = article.find("time")
            if a and a["href"]:
                url = a["href"] if a["href"].startswith("http") else f"https://www.kathimerini.gr{a['href']}"
                title = a.get_text(strip=True)
                date_text = time_tag.get("datetime", "") if time_tag else ""
                articles.append((title, url, date_text))
        return articles
    except Exception as e:
        print(f"Σφάλμα στο kathimerini: {e}")
        return []

def check_news_source(source):
    if source["name"] == "iefimerida":
        return check_iefimerida(source)
    elif source["name"] == "kathimerini":
        return check_kathimerini(source)
    return []

def process_news_source(source):
    seen = load_state(source["state_file"])
    articles = check_news_source(source)
    triggered = []
    for title, url, date_text in articles:
        if url in seen:
            continue
        # Check for today/yesterday
        if any(date_kw in date_text for date_kw in GREEK_DATES):
            triggered.append((title, url, date_text))
            seen.add(url)
    if triggered:
        for title, url, date_text in triggered:
            subject = f"Νέο κυκλοφοριακό νέο στο {source['domain']}"
            body = f"Τίτλος: {title}\nΗμερομηνία: {date_text}\nΣύνδεσμος: {url}"
            send_email(subject, body)
            print(f"Απεστάλη: {title}")
        save_state(source["state_file"], seen)

# ============ POLICE SCRAPER ============

def process_police_table():
    seen = load_state(POLICE_STATE_FILE)
    try:
        resp = requests.get(POLICE_URL, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            print("Δε βρέθηκε πίνακας στην αστυνομία.")
            return
        triggered_rows = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            # Adjust the column index as needed!
            # E.g., status in col 3 (2-based index). Review page for correct column!
            status = cells[-1].get_text(strip=True)  # Assume status in last column; update if needed!
            if "πολύ αυξημένη" in status.lower():
                row_id = "|".join(cell.get_text(strip=True) for cell in cells)
                if row_id not in seen:
                    triggered_rows.append(row_id)
                    seen.add(row_id)
        if triggered_rows:
            subject = "Νέα ΠΟΛΥ ΑΥΞΗΜΕΝΗ κυκλοφορία στην Αστυνομία"
            body = "Εντοπίστηκαν τα εξής περιστατικά:\n\n"
            for row in triggered_rows:
                body += row.replace("|", " | ") + "\n"
            body += f"\nΔείτε τη σελίδα: {POLICE_URL}"
            send_email(subject, body)
            print("Απεστάλη ειδοποίηση για αστυνομία.")
            save_state(POLICE_STATE_FILE, seen)
    except Exception as e:
        print("Σφάλμα στην αστυνομία:", e)

# ============ MAIN ============

def main():
    for source in NEWS_SOURCES:
        process_news_source(source)
    process_police_table()

if __name__ == "__main__":
    main()
