،s a, [29/07/26 08:56 م]
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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

def download_direct_image(url):
    """تنزيل الصورة مباشرة عبر الرابط المباشر"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            file_path = "downloads/direct_image.jpg"
            with open(file_path, 'wb') as f:
                f.write(res.content)
            return True
    except Exception as e:
        print(f"Direct Image Download Error: {e}")
    return False

@bot.message_handler(func=lambda message: True)
def handle_download(message):
    url = message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "من فضلك أرسل رابطاً صحيحاً للتحميل 🔗")
        return

    msg = bot.reply_to(message, "جاري معالجة الرابط وجلب المحتوى... ⏳")
    os.makedirs('downloads', exist_ok=True)

    # 1. المحاولة الأولى: عبر yt-dlp التنزيل المباشر
    ydl_opts = {
        'outtmpl': 'downloads/%(id)s_%(autonumber)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception:
        pass

    # 2. المحاولة الثانية: استخراج معلومات الرابط لتنزيل الصورة إن وجُدت
    if not glob.glob('downloads/*'):
        try:
            ydl_opts_info = {'quiet': True, 'no_warnings': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # البحث عن رابط الصورة داخل بيانات Meta
                img_url = info.get('url') or info.get('thumbnail')
                if not img_url and info.get('thumbnails'):
                    img_url = info['thumbnails'][-1].get('url')

                if img_url:
                    download_direct_image(img_url)
        except Exception:
            pass

    # 3. المحاولة الثالثة: قراءة وسوم og:image كخيار أخير
    if not glob.glob('downloads/*'):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            html = response.text
            img_match = re.search(r'property="og:image"\s+content="([^"]+)"', html) or \
                        re.search(r'content="([^"]+)"\s+property="og:image"', html) or \
                        re.search(r'name="twitter:image"\s+content="([^"]+)"', html)
            if img_match:
                clean_img_url = img_match.group(1).replace("&amp;", "&")
                download_direct_image(clean_img_url)
        except Exception:
            pass

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

،s a, [29/07/26 08:56 م]
bot.send_document(message.chat.id, file_data)
                os.remove(file_path)
            bot.delete_message(message.chat.id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"حدث خطأ أثناء إرسال الملف: ❌\n{str(e)}", message.chat.id, msg.message_id, parse_mode='Markdown')
    else:
        bot.edit_message_text("عذراً، لم أتمكن من استخراج صورة أو فيديو من هذا الرابط. ❌", message.chat.id, msg.message_id)

bot.polling(non_stop=True)
