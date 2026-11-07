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

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

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

def download_tiktok_content(chat_id, raw_url, status_msg_id):
    try:
        api_url = "https://www.tikwm.com/api/"
        payload = {'url': raw_url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}
        res = requests.post(api_url, data=payload, headers=HEADERS, timeout=20)
        
        if res.status_code == 200 and res.text.strip():
            json_data = res.json()
            if json_data.get('code') == 0:
                data = json_data.get('data', {})

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
        bot.edit_message_text(f"حدث خطأ أثناء المعالجة: {str(e)}", message.chat.id, msg.message_id)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text_input = message.text.strip()
    urls = re.findall(r'https?://[^\s]+', text_input)
    
    if urls:
        raw_url = urls[0]
        msg = bot.reply_to(message, "جاري المعالجة وتنزيل المحتوى... ⏳")

        if 'tiktok.com' in raw_url:
            success = download_tiktok_content(message.chat.id, raw_url, msg.message_id)
            if success:
                return

        req_id = uuid.uuid4().hex[:6]
        output_template = f'downloads/{message.chat.id}_{req_id}_%(id)s.%(ext)s'

        ydl_opts = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            }
        }
        
        downloaded_files = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([raw_url])

            downloaded_files = glob.glob(f'downloads/{message.chat.id}_{req_id}_*')

            if downloaded_files:
                for file_path in downloaded_files:
                    file_size = os.path.getsize(file_path)

                    if file_size > MAX_TELEGRAM_SIZE:
                        bot.edit_message_text("⚠️ حجم هذا الملف يزيد عن 50 ميجابايت (الحد المسموح في تليجرام).", message.chat.id, msg.message_id)
                        continue

                    ext = file_path.split('.')[-1].lower()
                    
                    if ext in ['jpg', 'jpeg', 'png', 'webp']:
                        with open(file_path, 'rb') as file_data:
                            bot.send_photo(message.chat.id, file_data, caption="✅ تم التنزيل بنجاح!", timeout=120)
                        
                    elif ext in ['mp4', 'mkv', 'webm', 'mov']:
                        markup = InlineKeyboardMarkup()
                        btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"extaudio_{raw_url}")
                        markup.add(btn)

                        with open(file_path, 'rb') as video_file:
                            bot.send_video(
                                message.chat.id, 
                                video_file, 
                                caption="تم تنزيل الفيديو بنجاح! 🎬✨", 
                                reply_markup=markup,
                                timeout=300
                            )
                    else:
                        with open(file_path, 'rb') as file_data:
                            bot.send_document(message.chat.id, file_data, timeout=300)

                bot.delete_message(message.chat.id, msg.message_id)
            else:
                bot.edit_message_text("عذراً، تعذر استخراج المحتوى من هذا الرابط.", message.chat.id, msg.message_id)

        except Exception as e:
            bot.edit_message_text(f"حدث خطأ أثناء تنزيل الملف: {str(e)}", message.chat.id, msg.message_id)
            
        finally:
            for f in downloaded_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
    else:
        bot.reply_to(message, "يرجى إرسال رابط فيديو/صورة للتنزيل، أو صورة تحتوي على نص لقراءتها. 📌")

@bot.callback_query_handler(func=lambda call: call.data.startswith('extaudio_'))
def handle_audio_extraction_callback(call):
    target_url = call.data.replace('extaudio_', '')
    bot.answer_callback_query(call.id, "جاري استخراج وتحميل الصوت... ⏳")
    
    req_id = uuid.uuid4().hex[:6]
    audio_out_tmpl = f'downloads/audio_{call.message.chat.id}_{req_id}.%(ext)s'
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': audio_out_tmpl,
        'quiet': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])
            
        expected_audio_path = f'downloads/audio_{call.message.chat.id}_{req_id}.mp3'
        
        if os.path.exists(expected_audio_path):
            with open(expected_audio_path, 'rb') as af:
                bot.send_audio(call.message.chat.id, af, title="الصوت المستخرج 🎵")
            os.remove(expected_audio_path)
        else:
            bot.send_message(call.message.chat.id, "❌ متعذر استخراج الصوت من هذا الفيديو.")
            
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء استخراج الصوت: {str(e)}")

# دالة تشغيل البوت في مسار (Thread) منفصل
def start_bot():
    try:
        bot.remove_webhook()
        print("Webhook cleared successfully")
    except Exception as e:
        print(f"Webhook note: {e}")
    print("🤖 البوت يعمل الآن ويستمع للرسائل...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

# تشغيل البوت تلقائياً في الخلفية فور استدعاء الملف
bot_thread = Thread(target=start_bot)
bot_thread.daemon = True
bot_thread.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
