import os
import glob
import re
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import yt_dlp
import instaloader

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

MAX_TELEGRAM_SIZE = 49 * 1024 * 1024

def extract_audio_from_video(video_path):
    try:
        audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
        video = VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path, logger=None)
        video.close()
        return audio_path
    except Exception as e:
        print(f"Audio extraction error: {e}")
        return None

apihelper.CONNECT_TIMEOUT = 120
apihelper.READ_TIMEOUT = 300

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

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في البوت الشامل! 🚀\n\n"
        "✨ **الخدمات المتاحة:**\n"
        "1️⃣ **تنزيل الوسائط:** فيديوهات تيك توك، إنستغرام، يوتيوب.\n"
        "2️⃣ **صور وسلايدات تيك توك:** تنزيل الصور كاملة بدقتها الأصلية مع الصوت.\n"
        "3️⃣ **استخراج الصوت:** تحويل الفيديو لمقطع صوتي.\n"
        "4️⃣ **استخراج النصوص (OCR):** قراءة النصوص من الصور."
    )
    bot.reply_to(message, welcome_text)

# فك الروابط المختصرة
def resolve_clean_url(url):
    try:
        res = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=12)
        return res.url.split('?')[0]
    except Exception:
        return url.split('?')[0]

# دالة تنزيل تيك توك باستخدام مسارين (API رئيسي + احتياطي)
def download_tiktok_content(chat_id, raw_url, status_msg_id):
    clean_url = resolve_clean_url(raw_url)
    
    # 1. المحاولة الأولى: عبر TikWM API
    try:
        api_url = f"https://www.tikwm.com/api/?url={clean_url}"
        res = requests.get(api_url, headers=HEADERS, timeout=20).json()
        
        if res.get('code') == 0:
            data = res.get('data', {})
            
            # صور وسلايد شو
            if 'images' in data and data['images']:
                images = data['images']
                music_url = data.get('music')
                title = data.get('title', 'صور تيك توك')

                for i in range(0, len(images), 10):
                    batch = images[i:i + 10]
                    media_group = [InputMediaPhoto(img_url) for img_url in batch]
                    bot.send_media_group(chat_id, media_group)

                if music_url:
                    bot.send_audio(chat_id, music_url, caption=f"🎵 الصوت المصاحب: {title[:50]}")

                bot.delete_message(chat_id, status_msg_id)
                return True

            # فيديو عادي
            video_url = data.get('play')
            if video_url:
                bot.send_video(chat_id, video_url, caption="تم تنزيل الفيديو بنجاح! 🎬✨")
                bot.delete_message(chat_id, status_msg_id)
                return True
    except Exception as e:
        print(f"TikWM failed: {e}")

    # 2. المحاولة الثانية (واجهة بديلة في حال حظر Render أو تعثر TikWM)
    try:
        fallback_api = f"https://api.tiklydown.eu.org/api/download?url={clean_url}"
        f_res = requests.get(fallback_api, headers=HEADERS, timeout=20).json()
        
        # استخراج الصور من الواجهة البديلة
        if 'images' in f_res and f_res['images']:
            images = [img['url'] if isinstance(img, dict) else img for img in f_res['images']]
            music_url = f_res.get('music', {}).get('play_url') or f_res.get('music')
            title = f_res.get('title', 'صور تيك توك')

            for i in range(0, len(images), 10):
                batch = images[i:i + 10]
                media_group = [InputMediaPhoto(img_url) for img_url in batch]
                bot.send_media_group(chat_id, media_group)

            if music_url:
                bot.send_audio(chat_id, music_url, caption=f"🎵 الصوت المصاحب: {title[:50]}")

            bot.delete_message(chat_id, status_msg_id)
            return True

        # استخراج الفيديو من الواجهة البديلة
        video_data = f_res.get('video', {})
        fallback_vid = video_data.get('noWatermark') or video_data.get('watermark')
        if fallback_vid:
            bot.send_video(chat_id, fallback_vid, caption="تم تنزيل الفيديو بنجاح! 🎬✨")
            bot.delete_message(chat_id, status_msg_id)
            return True

    except Exception as e:
        print(f"Fallback API failed: {e}")

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
                    msg.message_id
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

        # معالجة تيك توك حصرياً عبر الواجهات المخصصة
        if 'tiktok.com' in raw_url:
            success = download_tiktok_content(message.chat.id, raw_url, msg.message_id)
            if success:
                return
            else:
                bot.edit_message_text("عذراً، تعذر استخراج المحتوى من هذا الرابط. ❌", message.chat.id, msg.message_id)
                return

        if not os.path.exists('downloads'):
            os.makedirs('downloads')
        
        for f in glob.glob('downloads/*'):
            try:
                os.remove(f)
            except Exception:
                pass

        clean_link = raw_url.split('?')[0]

        if 'instagram.com' in raw_url:
            try:
                L = instaloader.Instaloader(
                    dirname_pattern='downloads',
                    filename_pattern='{shortcode}',
                    download_videos=True,
                    download_video_thumbnails=False,
                    download_geotags=False,
                    download_comments=False,
                    save_metadata=False
                )
                
                shortcode = None
                if '/reel/' in clean_link:
                    shortcode = clean_link.split('/reel/')[1].split('/')[0]
                elif '/p/' in clean_link:
                    shortcode = clean_link.split('/p/')[1].split('/')[0]
                    
                if shortcode:
                    post = instaloader.Post.from_shortcode(L.context, shortcode)
                    L.download_post(post, target='downloads')
            except Exception as e:
                print(f"Instaloader error: {e}")

        ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'check_formats': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([clean_link])
            except Exception:
                try:
                    ydl.download([raw_url])
                except Exception as e:
                    print(f"yt-dlp error: {e}")

        downloaded_files = glob.glob('downloads/*')

        if downloaded_files:
            try:
                for file_path in downloaded_files:
                    file_size = os.path.getsize(file_path)

                    if file_size > MAX_TELEGRAM_SIZE:
                        bot.edit_message_text("⚠️ حجم هذا الملف يزيد عن 50 ميجابايت (الحد المسموح في تليجرام).", message.chat.id, msg.message_id)
                        os.remove(file_path)
                        return

                    ext = file_path.split('.')[-1].lower()
                    
                    if ext in ['jpg', 'jpeg', 'png', 'webp']:
                        with open(file_path, 'rb') as file_data:
                            bot.send_photo(message.chat.id, file_data, timeout=120)
                        os.remove(file_path)
                        
                    elif ext in ['mp4', 'mkv', 'webm', 'mov']:
                        temp_video_path = f"downloads/temp_{os.path.basename(file_path)}"
                        os.rename(file_path, temp_video_path)
                        
                        markup = InlineKeyboardMarkup()
                        btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"extract_{os.path.basename(temp_video_path)}")
                        markup.add(btn)

                        with open(temp_video_path, 'rb') as video_file:
                            bot.send_video(
                                message.chat.id, 
                                video_file, 
                                caption="تم تنزيل الفيديو بنجاح! 🎬✨", 
                                reply_markup=markup,
                                timeout=300
                            )
                        os.remove(temp_video_path)
                            
                    else:
                        with open(file_path, 'rb') as file_data:
                            bot.send_document(message.chat.id, file_data, timeout=300)
                        os.remove(file_path)

                bot.delete_message(message.chat.id, msg.message_id)

            except Exception as e:
                bot.edit_message_text(f"حدث خطأ أثناء إرسال الملف: {str(e)}", message.chat.id, msg.message_id)
        else:
            bot.edit_message_text("عذراً، تعذر استخراج المحتوى من هذا الرابط.", message.chat.id, msg.message_id)
            
    else:
        bot.reply_to(message, "يرجى إرسال رابط فيديو/صورة للتنزيل، أو صورة تحتوي على نص لقراءتها. 📌")

@bot.callback_query_handler(func=lambda call: call.data.startswith('extract_'))
def handle_audio_extraction(call):
    filename = call.data.replace('extract_', '')
    video_path = os.path.join('downloads', filename)
    
    if os.path.exists(video_path):
        bot.answer_callback_query(call.id, "جاري استخراج الصوت... ⏳")
        audio_path = extract_audio_from_video(video_path)
        
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, 'rb') as audio_file:
                bot.send_audio(call.message.chat.id, audio_file, title="الصوت المستخرج 🎵")
            os.remove(audio_path)
        else:
            bot.send_message(call.message.chat.id, "عذراً، حدث خطأ أثناء استخراج الصوت. ❌")
            
        if os.path.exists(video_path):
            os.remove(video_path)
            
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    else:
        bot.answer_callback_query(call.id, "انتهت صلاحية هذا الملف أو تم حذفه! ❌", show_alert=True)

try:
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
    print("Webhook cleared successfully via HTTP request")
except Exception as e:
    print(f"Failed to clear webhook: {e}")

bot.infinity_polling(timeout=10, long_polling_timeout=5)
