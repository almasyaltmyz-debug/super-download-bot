import os
import glob
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

# --- 2. توكين البوت الجديد الخاص بك ---
TOKEN = '8960864210:AAGg1wQKE5_kwh05FTXPvA30xhc-IrnJrdk'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(func=lambda message: True)
def handle_download(message):
    url = message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "من فضلك أرسل رابطاً صحيحاً للتحميل 🔗")
        return

    msg = bot.reply_to(message, "جاري معالجة الرابط وجلب المحتوى... ⏳")

    os.makedirs('downloads', exist_ok=True)

    try:
        # جلب معلومات الرابط أولاً بدون فرض تنزيل فيديو
        ydl_opts_info = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            bot.edit_message_text("تعذر الحصول على معلومات من هذا الرابط. ❌", message.chat.id, msg.message_id)
            return

        # دعم المنشورات الفردية والألبومات (Carousel)
        entries = info.get('entries', [info])

        for index, item in enumerate(entries):
            # إذا كان المحتوى يتضمن فيديو
            if item.get('vcodec') and item.get('vcodec') != 'none':
                ydl_opts_video = {
                    'outtmpl': f'downloads/video_{index}.%(ext)s',
                    'quiet': True,
                    'no_warnings': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts_video) as ydl_down:
                    ydl_down.download([item.get('webpage_url', url)])
            
            # إذا كان المحتوى عبارة عن صورة (إنستغرام، تويتر، إلخ)
            else:
                img_url = item.get('url') or item.get('display_url')
                if not img_url and item.get('thumbnails'):
                    img_url = item['thumbnails'][-1].get('url')

                if img_url:
                    img_bytes = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}).content
                    file_path = f"downloads/image_{index}.jpg"
                    with open(file_path, 'wb') as f:
                        f.write(img_bytes)

        # جلب كل الملفات المحفوظة لإرسالها
        downloaded_files = glob.glob('downloads/*')

        if not downloaded_files:
            bot.edit_message_text("لم يتم العثور على أي ملفات قابلة للتحميل في هذا الرابط. ❌", message.chat.id, msg.message_id)
            return

        # إرسال الملفات للمستخدم
        for file_path in downloaded_files:
            ext = file_path.split('.')[-1].lower()
            with open(file_path, 'rb') as file_data:
                if ext in ['jpg', 'jpeg', 'png', 'webp']:
                    bot.send_photo(message.chat.id, file_data)
                elif ext in ['mp4', 'mkv', 'webm', 'mov']:
                    bot.send_video(message.chat.id, file_data)
                else:
                    bot.send_document(message.chat.id, file_data)
            
            # تنظيف السيرفر أولاً بأول
            os.remove(file_path)

        bot.delete_message(message.chat.id, msg.message_id)

    except Exception as e:
        for f in glob.glob('downloads/*'):
            try: os.remove(f)
            except: pass
        bot.edit_message_text(f"عذراً، حدث خطأ أثناء التحميل: ❌\n{str(e)}", message.chat.id, msg.message_id, parse_mode='Markdown')

bot.polling(non_stop=True)
