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

# دالة استخراج الصوت من الفيديو
def extract_audio_from_video(video_path):
    """استخراج الصوت وتحويله إلى MP3"""
    try:
        audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
        video = VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path, logger=None)
        video.close()
        return audio_path
    except Exception as e:
        print(f"Audio extraction error: {e}")
        return None

# زيادة مهلة الاتصال والرفع
apihelper.CONNECT_TIMEOUT = 120
apihelper.READ_TIMEOUT = 300

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
OCR_API_KEY = os.environ.get('OCR_API_KEY', 'helloworld')
bot = telebot.TeleBot(BOT_TOKEN)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في بوت التحميل واستخراج النصوص الشامل! 🚀\n\n"
        "✨ **ماذا يمكنني أن أفعل لك؟**\n"
        "1️⃣ **تنزيل الوسائط:** أرسل لي رابطاً من (يوتيوب، إنستغرام، تيك توك، فيسبوك، إلخ).\n"
        "2️⃣ **استخراج الصوت:** اضغط على زر 'استخراج الصوت' تحت أي فيديو يتم تنزيله.\n"
        "3️⃣ **استخراج النص من الصور (OCR):** أرسل لي أي صورة تحتوي على نص وسأقوم بقراءته واستخراجه فوراً!"
    )
    bot.reply_to(message, welcome_text)

def clean_url(url):
    return url.split('?')[0]

# معالج الصور لاستخراج النص (OCR)
@bot.message_handler(content_types=['photo'])
def handle_photo_ocr(message):
    msg = bot.reply_to(message, "جاري قراءة النص من الصورة... 🔍")
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # المحاولة الأولى باللغة العربية مع المحرك الافتراضي المضمون
        payload = {
            'apikey': OCR_API_KEY,
            'language': 'ara',
            'isOverlayRequired': False,
            'detectOrientation': 'true',
            'scale': 'true'
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
                bot.edit_message_text(f"📝 **النص المستخرج من الصورة:**\n\n{extracted_text}", message.chat.id, msg.message_id)
                return

        # المحاولة الاحتياطية بدون تحديد لغة في حال وجود أخطاء في الرمز
        payload_fallback = {
            'apikey': OCR_API_KEY,
            'isOverlayRequired': False,
            'detectOrientation': 'true',
            'scale': 'true'
        }
        
        res_fb = requests.post(
            'https://api.ocr.space/parse/image',
            files={'filename': ('image.jpg', downloaded_file, 'image/jpeg')},
            data=payload_fallback,
            timeout=60
        ).json()
        
        if res_fb.get('OCRExitCode') == 1 and res_fb.get('ParsedResults'):
            extracted_text = res_fb['ParsedResults'][0]['ParsedText'].strip()
            if extracted_text:
                bot.edit_message_text(f"📝 **النص المستخرج من الصورة:**\n\n{extracted_text}", message.chat.id, msg.message_id)
                return

        bot.edit_message_text("عذراً، لم يتم العثور على نص واضح داخل الصورة. ❌", message.chat.id, msg.message_id)

    except requests.exceptions.Timeout:
        bot.edit_message_text("تأخرت الاستجابة من السيرفر، يرجى المحاولة مرة أخرى بصورة أصغر حجماً. ⏳", message.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"حدث خطأ أثناء المعالجة: {str(e)}", message.chat.id, msg.message_id)

# معالج الرابط والوسائط
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if not (url.startswith('http://') or url.startswith('https://')):
        bot.reply_to(message, "الرجاء إرسال رابط صحيح يتبعه http:// أو https:// أو إرسال صورة لاستخراج النص منها.")
        return

    msg = bot.reply_to(message, "جاري المعالجة والتحميل... ⏳")

    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    
    for f in glob.glob('downloads/*'):
        try:
            os.remove(f)
        except Exception:
            pass

    # إنستغرام
    if 'instagram.com' in url:
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
            
            clean_link = clean_url(url)
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

    # باقي المنصات عبر yt-dlp
    ydl_opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'format': 'best[height<=720]/best',
        'user_agent': HEADERS['User-Agent'],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except Exception:
            pass

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

# معالج استخراج الصوت
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

bot.polling(non_stop=True)
