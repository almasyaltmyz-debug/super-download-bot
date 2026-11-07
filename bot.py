import os
import glob
import re
import uuid
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import yt_dlp

# إعداد مهلة الاتصال لمنع توقف الطلبات
apihelper.CONNECT_TIMEOUT = 120
apihelper.READ_TIMEOUT = 300

MAX_TELEGRAM_SIZE = 49 * 1024 * 1024

# إنشاء تطبيق Flask لإبقاء الخدمة نشطة على Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

# جلب توكن البوت من متغيرات البيئة
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# تنظيف أي Webhook معلق فور إقلاع البوت لمنع تعارض Conflict 409
try:
    bot.remove_webhook()
except Exception as e:
    print(f"Webhook cleanup note: {e}")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

if not os.path.exists('downloads'):
    os.makedirs('downloads')

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في البوت الشامل! 🚀\n\n"
        "✨ **الخدمات المتاحة:**\n"
        "1️⃣ **تنزيل الوسائط:** فيديوهات تيك توك، إنستغرام، يوتيوب، تويتر وغيرها.\n"
        "2️⃣ **ألبومات تيك توك:** تنزيل الصور كاملة بدقتها الأصلية مع الصوت المرفق.\n"
        "3️⃣ **استخراج الصوت:** تحويل أي فيديو لمقطع صوتي مباشرة.\n"
        "4️⃣ **استخراج النصوص (OCR):** قراءة النصوص من الصور."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

# تنزيل ومعالجة تيك توك (فيديوهات وألبومات صور)
def download_tiktok_content(chat_id, raw_url, status_msg_id):
    try:
        api_url = "https://www.tikwm.com/api/"
        payload = {'url': raw_url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}
        res = requests.post(api_url, data=payload, headers=HEADERS, timeout=20)
        
        if res.status_code == 200 and res.text.strip():
            json_data = res.json()
            if json_data.get('code') == 0:
                data = json_data.get('data', {})

                # 1. حالة ألبوم الصور (Slideshow)
                images = data.get('images')
                if images and isinstance(images, list):
                    music_url = data.get('music')
                    title = data.get('title', 'ألبوم صور تيك توك')

                    saved_files = []
                    for idx, img_url in enumerate(images):
                        try:
                            r = requests.get(img_url, headers=HEADERS, timeout=15)
                            if r.status_code == 200:
                                img_path = f"downloads/tk_img_{chat_id}_{idx}_{uuid.uuid4().hex[:4]}.jpg"
                                with open(img_path, 'wb') as f:
                                    f.write(r.content)
                                saved_files.append(img_path)
                        except Exception as err:
                            print(f"Error fetching image {idx}: {err}")

                    # إرسال الصور في مجموعات (ألبوم 10 صور كحد أقصى لكل دفعة)
                    if saved_files:
                        for i in range(0, len(saved_files), 10):
                            batch = saved_files[i:i + 10]
                            media_group = []
                            open_handles = []
                            for path in batch:
                                fh = open(path, 'rb')
                                open_handles.append(fh)
                                media_group.append(InputMediaPhoto(fh))

                            bot.send_media_group(chat_id, media_group)
                            for fh in open_handles:
                                fh.close()

                        for path in saved_files:
                            if os.path.exists(path):
                                os.remove(path)

                        # تنزيل وإرسال الصوت المرفق بالألبوم
                        if music_url:
                            try:
                                audio_res = requests.get(music_url, headers=HEADERS, timeout=25)
                                if audio_res.status_code == 200:
                                    audio_path = f"downloads/tk_audio_{chat_id}_{uuid.uuid4().hex[:4]}.mp3"
                                    with open(audio_path, 'wb') as f:
                                        f.write(audio_res.content)
                                    with open(audio_path, 'rb') as af:
                                        bot.send_audio(chat_id, af, title=title[:40], caption=f"🎵 {title[:60]}")
                                    if os.path.exists(audio_path):
                                        os.remove(audio_path)
                            except Exception as err:
                                print(f"Error sending audio: {err}")

                        bot.delete_message(chat_id, status_msg_id)
                        return True

                # 2. حالة الفيديو العادي
                video_url = data.get('play')
                if video_url:
                    v_res = requests.get(video_url, headers=HEADERS, timeout=30)
                    video_path = f"downloads/tk_vid_{chat_id}_{uuid.uuid4().hex[:4]}.mp4"
                    with open(video_path, 'wb') as f:
                        f.write(v_res.content)

                    markup = InlineKeyboardMarkup()
                    btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"extaudio_{raw_url}")
                    markup.add(btn)

                    with open(video_path, 'rb') as vf:
                        bot.send_video(chat_id, vf, caption="تم تنزيل الفيديو بنجاح! 🎬✨", reply_markup=markup)

                    if os.path.exists(video_path):
                        os.remove(video_path)

                    bot.delete_message(chat_id, status_msg_id)
                    return True
    except Exception as e:
        print(f"TikWM attempt failed: {e}")

    return False

@bot.message_handler(content_types=['photo'])
def handle_photo_ocr(message):
    msg = bot.reply_to(message, "جاري قراءة النص العربي من الصورة... 🔍")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        payload = {
            'apikey': 'helloworld',
            'language': 'ara',
            'OCREngine': 2,
            'isOverlayRequired': False,
            'scale': True
        }
        
        response = requests.post(
            'https://api.ocr.space/parse/image',
            files={'filename': ('image.jpg', downloaded_file, 'image/jpeg')},
            data=payload,
            timeout=60
        )
        
        result = response.json()
        
        if result.get('OCRExitCode') == 1 and result.get('ParsedResults'):
            extracted_text = result['ParsedResults'][0]['ParsedText'].strip()
            if extracted_text:
                bot.edit_message_text(
                    f"📝 **النص المستخرج من الصورة:**\n\n{extracted_text}",
                    message.chat.id,
                    msg.message_id,
                    parse_mode="Markdown"
                )
                return

        bot.edit_message_text("عذراً، لم يتم العثور على نص واضح داخل الصورة. ❌", message.chat.id, msg.message_id)

    except Exception as e:
        bot.edit
