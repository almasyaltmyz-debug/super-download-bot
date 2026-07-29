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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

def extract_clean_url(text):
    """استخراج الرابط الصافي وحذف أي رموز مرافقة"""
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

def download_image_via_url(img_url, filename="downloads/photo.jpg"):
    """تنزيل الصورة عبر requests وتخزينها"""
    try:
        res = requests.get(img_url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(res.content)
            return True
    except Exception as e:
        print(f"Error downloading image: {e}")
    return False

@bot.message_handler(func=lambda message: True)
def handle_download(message):
    raw_text = message.text.strip()
    url = extract_clean_url(raw_text)

    if not url:
        bot.reply_to(message, "من فضلك أرسل رابطاً صحيحاً للتحميل 🔗")
        return

    msg = bot.reply_to(message, "جاري معالجة الرابط وجلب المحتوى... ⏳")
    os.makedirs('downloads', exist_ok=True)

    ydl_opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'user_agent': HEADERS['User-Agent'],
    }

    # 1. المحاولة الأولى: yt-dlp للتنزيل المباشر (فيديو/صور)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception:
        pass

    # 2. المحاولة الثانية: استخراج رابط الصور المخفية في بيانات المنشور (Instagram/Pinterest)
    if not glob.glob('downloads/*'):
        try:
            ydl_opts_info = {'quiet': True, 'no_warnings': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # جلب الصور سواء كانت صورة مفردة أو ألبوم (thumbnails)
                images = []
                if 'entries' in info:
                    for entry in info['entries']:
                        if entry.get('url'): images.append(entry['url'])
                        elif entry.get('thumbnails'): images.append(entry['thumbnails'][-1]['url'])
                else:
                    if info.get('url') and ('jpg' in info['url'] or 'png' in info['url'] or 'webp' in info['url']):
                        images.append(info['url'])
                    elif info.get('thumbnails'):
                        images.append(info['thumbnails'][-1]['url'])

                # تنزيل الصور التي تم العثور عليها
                for i, img_link in enumerate(images):
                    download_image_via_url(img_link, f"downloads/image_{i}.jpg")
        except Exception:
            pass

    # 3. المحاولة الثالثة: قراءة HTML مباشرة لاستخراج og:image (للصور الثابتة)
    if not glob.glob('downloads/*'):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            img_match = re.search(r'property="og:image"\s+content="([^"]+)"', resp.text) or \
                        re.search(r'content="([^"]+)"\s+property="og:image"', resp.text)
            if img_match:
                img_url = img_match.group(1).replace("&amp;", "&")
                download_image_via_url(img_url, "downloads/og_image.jpg")
        except Exception:
            pass

    # إرسال الملفات التي تم تنزيلها
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
        bot.edit_message_text("عذراً، لم أتمكن من استخراج الصورة أو الفيديو من هذا الرابط. قد يكون المنشور خاصاً. ❌", message.chat.id, msg.message_id)

bot.polling(non_stop=True)
