import os
import glob
import re
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import instaloader

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

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
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في البوت الشامل! 🚀\n\n"
        "✨ **الخدمات المتاحة:**\n"
        "1️⃣ **تنزيل الوسائط:** أرسل رابط فيديو أو صورة.\n"
        "2️⃣ **استخراج الصوت:** تحويل الفيديو لمقطع صوتي.\n"
        "3️⃣ **استخراج النصوص (OCR):** قراءة النصوص من الصور."
    )
    bot.reply_to(message, welcome_text)

# حل روابط TikTok المختصرة واستخراج الرابط الحقيقي
def resolve_tiktok_url(url):
    try:
        if 'vt.tiktok.com' in url or 'vm.tiktok.com' in url:
            res = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
            return res.url.split('?')[0]
        return url.split('?')[0]
    except Exception as e:
        print(f"URL resolve error: {e}")
        return url.split('?')[0]

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
    
    # استخراج أول رابط داخل الرسالة لو كانت تحتوي على نصوص إضافية
    urls = re.findall(r'https?://[^\s]+', text_input)
    if urls:
        raw_url = urls[0]
        msg = bot.reply_to(message, "جاري المعالجة والتحميل... ⏳")

        if not os.path.exists('downloads'):
            os.makedirs('downloads')
        
        for f in glob.glob('downloads/*'):
            try:
                os.remove(f)
            except Exception:
                pass

        # فك الرابط المختصر وتنظيفه
        target_url = resolve_tiktok_url(raw_url)

        if 'instagram.com' in target_url:
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
                if '/reel/' in target_url:
                    shortcode = target_url.split('/reel/')[1].split('/')[0]
                elif '/p/' in target_url:
                    shortcode = target_url.split('/p/')[1].split('/')[0]
                    
                if shortcode:
                    post = instaloader.Post.from_shortcode(L.context, shortcode)
                    L.download_post(post, target='downloads')
            except Exception as e:
                print(f"Instaloader error: {e}")

        # إعدادات yt-dlp المحدثة بتجاوز القيود
        ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo+bestaudio/best',
            'check_formats': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([target_url])
            except Exception as e:
                print(f"yt-dlp primary error: {e}")
                try:
                    # محاولة ثانية بالرابط الأصلي خام
                    ydl.download([raw_url])
                except Exception as e2:
                    print(f"yt-dlp fallback error: {e2}")

        downloaded_files = glob.glob('downloads/*')

        if downloaded_files:
            try:
                for file_path in downloaded_files:
                    ext = file_path.split('.')[-1].lower()
                    
                    if ext in ['jpg', 'jpeg', 'png', 'webp']:
                        with open(file_path, 'rb') as file_data:
                            bot.send_photo(message.chat.id, file_data, timeout=120)
                        os.remove(file_path)
                        
                    elif ext in ['mp4', 'mkv', 'webm', 'mov']:
                        temp_video_path = f"downloads/temp_{os.path.basename(file_path)}"
                        os.rename(file_path, temp_video_path)
                        
                        with open(temp_video_path, 'rb') as video_file:
                            markup = InlineKeyboardMarkup()
                            btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"extract_{os.path.basename(temp_video_path)}")
                            markup.add(btn)
                            bot.send_video(message.chat.id, video_file, caption="تم تنزيل الفيديو بنجاح! 🎬", reply_markup=markup)
                            
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

bot.polling(none_stop=True, interval=0)
