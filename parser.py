import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import cloudscraper

# Настройки из GitHub Secrets
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.yandex.ru")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 465))
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

DB_FILE = "last_id.txt"


def get_last_saved_id():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0
    return 0


def save_last_id(post_id):
    with open(DB_FILE, "w") as f:
        f.write(str(post_id))


def send_email(post_id, date_str, category, text, img_url=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Подслушано"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    # Формирование тела письма по ТЗ: ID на самом верху, ниже дата, категория и сам пост
    html = f"""
    <html>
      <body>
        <p><b>ID:</b> {post_id}</p>
        <p><b>Дата публикации:</b> {date_str}</p>
        <p><b>Категория:</b> {category}</p>
        <hr>
        <p style="white-space: pre-wrap;">{text}</p>
    """
    if img_url:
        html += f'<br><br><img src="{img_url}" alt="Post Image" style="max-width:100%;">'

    html += """
      </body>
    </html>
    """

    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print(f"Письмо для поста {post_id} успешно отправлено.")
    except Exception as e:
        print(f"Ошибка отправки почты для поста {post_id}: {e}")


def parse_ideer():
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True,
        }
    )

    current_id = get_last_saved_id()
    
    if current_id == 0:
        print("Внимание: last_id.txt содержит 0 или не найден.")
        return

    print(f"Начинаем проверку постов. Последний сохраненный ID: {current_id}")
    
    new_posts_counter = 0
    consecutive_404_limit = 3
    consecutive_404_count = 0

    while True:
        current_id += 1
        url = f"https://ideer.ru/p/{current_id}"
        
        try:
            time.sleep(1)
            response = scraper.get(url, timeout=10)
            
            if response.status_code == 404:
                consecutive_404_count += 1
                if consecutive_404_count >= consecutive_404_limit:
                    print(f"Достигнут предел пустых страниц (404) на ID: {current_id}. Новых постов нет.")
                    break
                continue
                
            if response.status_code != 200:
                print(f"Сервер вернул код {response.status_code} для ID {current_id}. Прерываем цикл.")
                break

            consecutive_404_count = 0
            soup = BeautifulSoup(response.text, "html.parser")
            
            # --- ПАРСИНГ ДАТЫ (ищем класс, начинающийся с post_date) ---
            date_elem = soup.find(class_=lambda x: x and x.startswith("post_date"))
            if date_elem:
                # Пытаемся вытащить точную дату из всплывашки (tooltip), если её нет — берем текст элемента
                tooltip = date_elem.find(class_=lambda x: x and "tooltip" in x)
                date_str = tooltip.text.strip() if tooltip else date_elem.text.strip()
            else:
                date_str = "Дата не указана"

            # --- ПАРСИНГ КАТЕГОРИИ (ищем класс, начинающийся с post_category) ---
            cat_elem = soup.find(class_=lambda x: x and x.startswith("post_category"))
            category = cat_elem.text.strip() if cat_elem else "Без категории"

            # --- ПАРСИНГ ТЕКСТА (ищем класс, начинающийся с post_note) ---
            text_elem = soup.find(class_=lambda x: x and x.startswith("post_note"))
            
            # Если из-за обновлений класс изменится, используем старые резервные селекторы
            if not text_elem:
                text_elem = (
                    soup.find("div", class_="short-text") or 
                    soup.find("div", class_="post-body") or
                    soup.find("article")
                )
            
            if not text_elem:
                print(f"Не удалось найти текст в посте {current_id}. Пропускаем карточку.")
                continue
                
            text = text_elem.text.strip()

            # --- ПАРСИНГ КАРТИНКИ ---
            img_url = None
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if "posts" in src or "uploads" in src:
                    img_url = src if src.startswith("http") else "https://ideer.ru" + src
                    break

            # Отправляем письмо с учетом новых полей
            send_email(current_id, date_str, category, text, img_url)
            new_posts_counter += 1
            
            # Фиксируем успех в базе
            save_last_id(current_id)

        except Exception as e:
            print(f"Ошибка при обработке ID {current_id}: {e}")
            break

    print(f"Парсинг завершен. Отправлено новых постов за этот запуск: {new_posts_counter}. Текущий ID в базе остановился на: {get_last_saved_id()}")


if __name__ == "__main__":
    parse_ideer()
