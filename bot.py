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
from deep_translator import GoogleTranslator

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

# دالة استخراج الصوت من الفيديو
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
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# إزالة أي Webhook أو اتصالات معلقة تلقائياً قبل التشغيل لمنع خطأ 409
try:
    bot.remove_webhook()
except Exception as e:
    print(f"Webhook removal status: {e}")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في البوت الشامل! 🚀\n\n"
        "✨ **الخدمات المتاحة:**\n"
        "1️⃣ **تنزيل الوسائط:** أرسل رابط فيديو أو صورة.\n"
        "2️⃣ **استخراج الصوت:** تحويل الفيديو لمقطع صوتي.\n"
        "3️⃣ **استخراج النصوص (OCR):** قراءة النصوص من الصور.\n"
        "4️⃣ **الترجمة:** ترجمة النصوص المستخرجة أو أي نص ترقمه للبوت فوراً!"
    )
    bot.reply_to(message, welcome_text)

def clean_url(url):
    return url.split('?')[0]

# معالج الصور مع خيار الترجمة المباشرة للنص المستخرج
@bot.message_handler(content_types=['photo'])
def handle_photo_ocr(message):
    msg = bot.reply_to(message, "جاري قراءة النص العربي من الصورة... 🔍")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        payload = {
            'apikey': 'helloworld',
            'language': 'ara',
            'OCREngine': 1,
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
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("ترجمة للإنجليزية 🇬🇧", callback_data="tr_en"),
                    InlineKeyboardButton("ترجمة للعربية 🇸🇦", callback_data="tr_ar")
                )
                bot.edit_message_text(
                    f"📝 **النص المستخرج من الصورة:**\n\n{extracted_text}",
                    message.chat.id,
                    msg.message_id,
                    reply_markup=markup
                )
                return

        bot.edit_message_text("عذراً، لم يتم العثور على نص واضح داخل الصورة. ❌", message.chat.id, msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"حدث خطأ أثناء المعالجة: {str(e)}", message.chat.id, msg.message_id)

# معالج ضغطة زِر الترجمة
@bot.callback_query_handler(func=lambda call: call.data.startswith('tr_'))
def handle_translation_callback(call):
    target_lang = call.data.split('_')[1]
    original_text = call.message.text.replace("📝 **النص المستخرج من الصورة:**", "").strip()
    
    bot.answer_callback_query(call.id, "جاري الترجمة... 🌐")
    
    try:
        translated = GoogleTranslator(source='auto', target=target_lang).translate(original_text)
        lang_name = "الإنجليزية" if target_lang == 'en' else "العربية"
        
        bot.send_message(
            call.message.chat.id,
            f"🌐 **الترجمة إلى {lang_name}:**\n\n{translated}",
            reply_to_message_id=call.message.message_id
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"حدث خطأ أثناء الترجمة: {str(e)}")

# معالج الرابط والوسائط والنصوص العادية للترجمة
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text_input = message.text.strip()
    
    if text_input.startswith('http://') or text_input.startswith('https://'):
        msg = bot.reply_to(message, "جاري المعالجة والتحميل... ⏳")

        if not os.path.exists('downloads'):
            os.makedirs('downloads')
        
        for f in glob.glob('downloads/*'):
            try:
                os.remove(f)
            except Exception:
                pass

        if 'instagram.com' in text_input:
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
                
                clean_link = clean_url(text_input)
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
            'format': 'best[height<=720]/best',
            'user_agent': HEADERS['User-Agent'],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([text_input])
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
            
    else:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("إلى الإنجليزية 🇬🇧", callback_data="txt_en"),
            InlineKeyboardButton("إلى العربية 🇸🇦", callback_data="txt_ar")
        )
        bot.reply_to(message, "اختر اللغة التي تريد ترجمة هذا النص إليها:", reply_markup=markup)

# معالج ترجمة النصوص العادية
@bot.callback_query_handler(func=lambda call: call.data.startswith('txt_'))
def handle_text_translation(call):
    target_lang = call.data.split('_')[1]
    original_text = call.message.reply_to_message.text if call.message.reply_to_message else ""
    
    if not original_text:
        bot.answer_callback_query(call.id, "تعذر العثور على النص الأصلي!", show_alert=True)
        return

    bot.answer_callback_query(call.id, "جاري الترجمة... 🌐")
    
    try:
        translated = GoogleTranslator(source='auto', target=target_lang).translate(original_text)
        lang_name = "إنجليزية" if target_lang == 'en' else "عربية"
        bot.edit_message_text(
            f"🌐 **الترجمة ({lang_name}):**\n\n{translated}",
            call.message.chat.id,
            call.message.message_id
        )
    except Exception as e:
        bot.edit_message_text(f"حدث خطأ أثناء الترجمة: {str(e)}", call.message.chat.id, call.message_id)

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

# تشغيل البوت بدون إجباره على التفقد المتكرر المعارض
bot.infinity_polling(skip_pending_updates=True)
