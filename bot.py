import os
import glob
import re
import requests
from threading import Thread
from flask import Flask
import telebot
import yt_dlp

# --- 1. سيرفر Flask المدمج لإبقاء البوت شغالاً 24/7 ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

keep_alive()

# --- 2. توكين البوت الخاص بك ---
TOKEN = '8960864210:AAGg1wQKE5_kwh05FTXPvA30xhc-IrnJrdk'
bot = telebot.TeleBot(TOKEN)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

def extract_image_fallback(url):
    """استخراج الصورة مباشرة عند فشل yt-dlp في إيجاد فيديو"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        html = response.text
        # البحث عن رابط الصورة عالية الجودة في og:image أو twitter:image
        img_match = re.search(r'property="og:image"\s+content="([^"]+)"', html) or \
                    re.search(r'name="twitter:image"\s+content="([^"]+)"', html) or \
                    re.search(r'content="([^"]+)"\s+property="og:image"', html)
        
        if img_match:
            img_url = img_match.group(1).replace("&amp;", "&")
            img_data = requests.get(img_url, headers=HEADERS, timeout=10).content
            file_path = "downloads/fallback_image.jpg"
            with open(file_path, 'wb') as f:
                f.write(img_data)
            return True
    except Exception as e:
        print(f"Fallback Error: {e}")
    return False

@bot.message_handler(func=lambda message: True)
def handle_download(message):
    url = message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "من فضلك أرسل رابطاً صحيحاً للتحميل 🔗")
        return

    msg = bot.reply_to(message, "جاري معالجة الرابط وجلب المحتوى... ⏳")
    os.makedirs('downloads', exist_ok=True)

    download_success = False

    # المحاولة الأولى: عبر yt-dlp (للفيديوهات والألبومات)
    try:
        ydl_opts = {
            'outtmpl': 'downloads/%(id)s_%(autonumber)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        download_success = True
    except Exception:
        # المحاولة الثانية: النظام الاحتياطي للصور (Pinterest / Instagram Photos)
        download_success = extract_image_fallback(url)

    # جلب جميع الملفات التي تم تنزيلها
    downloaded_files = glob.glob('downloads/*')

    if downloaded_files:
        try:
            for file_path in downloaded_files:
                ext = file_path.split('.')[-1].lower()
                with open(file_path, 'rb') as file_data:
                    if ext in ['jpg', 'jpeg', 'png', 'webp']:
                        bot.send_photo(message.chat.id, file_data)
                    elif ext in ['mp4', 'mkv', 'webm', 'mov']:
                        bot.send_video(message.chat.id, file_data)
                    else:
                        bot.send_document(message.chat.id, file_data)
                os.remove(file_path)
            bot.delete_message(message.chat.id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"حدث خطأ أثناء إرسال الملف: ❌\n{str(e)}", message.chat.id, msg.message_id, parse_mode='Markdown')
    else:
        bot.edit_message_text("عذراً، لم أتمكن من استخراج صورة أو فيديو من هذا الرابط. ❌", message.chat.id, msg.message_id)

bot.polling(non_stop=True)
