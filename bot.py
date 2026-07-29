import os
import glob
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
TOKEN = '8960864210:AAHxnc8I-qh6YPPzfJgv_4Pr7M20LV03Lyw'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(func=lambda message: True)
def handle_download(message):
    url = message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "من فضلك أرسل رابطاً صحيحاً للتحميل 🔗")
        return

    msg = bot.reply_to(message, "جاري معالجة الرابط وجلب المحتوى... ⏳")

    # إعدادات شاملة لتنزيل الصور والفيديوهات والألبومات معاً
    ydl_opts = {
        'outtmpl': 'downloads/%(id)s_%(autonumber)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo+bestaudio/best',
        'writethumbnails': True,  # لاستخراج الصور والبوستات
        'allow_playlist_files': True,
    }

    os.makedirs('downloads', exist_ok=True)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
            
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
            
            os.remove(file_path)

        bot.delete_message(message.chat.id, msg.message_id)

    except Exception as e:
        for f in glob.glob('downloads/*'):
            try: os.remove(f)
            except: pass
        bot.edit_message_text(f"عذراً، حدث خطأ أثناء التحميل: ❌\n{str(e)}", message.chat.id, msg.message_id, parse_mode='Markdown')

bot.polling(non_stop=True)
