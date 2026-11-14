import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

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


def send_email(post_id, category, text, img_url=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Подслушано"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    html = f"""
    <html>
      <body>
        <p><b>ID:</b> {post_id}</p>
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
    current_id = get_last_saved_id()

    if current_id == 0:
        print("Внимание: last_id.txt содержит 0 или не найден.")
        return

    print(f"Начинаем проверку постов. Последний сохраненный ID: {current_id}")

    new_posts_counter = 0
    consecutive_404_limit = 3
    consecutive_404_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        while True:
            current_id += 1
            url = f"https://ideer.ru/p/{current_id}"

            try:
                time.sleep(1)
                response = page.goto(url, wait_until="domcontentloaded", timeout=15000)

                if not response or response.status == 404:
                    consecutive_404_count += 1
                    if consecutive_404_count >= consecutive_404_limit:
                        print(f"Достигнут предел пустых страниц (404) на ID: {current_id}. Новых постов нет.")
                        break
                    continue

                if response.status != 200:
                    print(f"Сервер вернул код {response.status} для ID {current_id}. Прерываем цикл.")
                    break

                # Ждем, пока React отрисует тело поста (максимум 5 секунд)
                try:
                    page.wait_for_selector(".post-card__body", timeout=5000)
                except Exception:
                    # Если тело поста так и не появилось (например, страница ошибки внутри SPA), считаем как пустую
                    consecutive_404_count += 1
                    print(f"Карточка поста {current_id} не отрендерилась (возможно, пост удален).")
                    if consecutive_404_count >= consecutive_404_limit:
                        print(f"Достигнут предел пустых страниц на ID: {current_id}. Новых постов нет.")
                        break
                    continue

                consecutive_404_count = 0
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # --- ПАРСИНГ КАТЕГОРИИ ---
                cat_elem = soup.find("a", class_="post-card__category")
                category = cat_elem.text.strip() if cat_elem else "Без категории"

                # --- ПАРСИНГ ТЕКСТА ---
                text_elem = soup.find("div", class_="post-card__body")
                if not text_elem:
                    print(f"Не удалось найти текст в посте {current_id}. Пропускаем.")
                    continue

                text = text_elem.text.strip()

                # --- ПАРСИНГ КАРТИНКИ ---
                img_url = None
                # Ищем картинку внутри самой карточки поста, чтобы не цеплять лишнее
                card_elem = soup.find(class_="post-card") or soup
                for img in card_elem.find_all("img"):
                    src = img.get("src", "")
                    if "posts" in src or "uploads" in src or "storage" in src:
                        img_url = src if src.startswith("http") else "https://ideer.ru" + src
                        break

                send_email(current_id, category, text, img_url)
                new_posts_counter += 1
                save_last_id(current_id)

            except Exception as e:
                print(f"Ошибка при обработке ID {current_id}: {e}")
                break

        browser.close()

    print(f"Парсинг завершен. Отправлено новых постов: {new_posts_counter}. Текущий ID в базе: {get_last_saved_id()}")


if __name__ == "__main__":
    parse_ideer()
        
