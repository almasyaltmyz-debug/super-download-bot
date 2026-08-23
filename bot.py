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
bot = telebot.TeleBot(BOT_TOKEN)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في بوت التحميل الشامل! 🚀\n\n"
        "أرسل لي أي رابط من المنصات التالية وسأقوم بتحميله لك فوراً:\n"
        "• يوتيوب (فيديو أو شورتس)\n"
        "• إنستغرام (ريلز، منشورات، ستوري)\n"
        "• تيك توك\n"
        "• فيسبوك، تويتر (X)، بينترست، تيك توك وغيرها الكثير!\n\n"
        "💡 كما يمكنك استخراج الصوت من أي فيديو بنقرة زر واحدة!"
    )
    bot.reply_to(message, welcome_text)

def clean_url(url):
    return url.split('?')[0]

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if not (url.startswith('http://') or url.startswith('https://')):
        bot.reply_to(message, "الرجاء إرسال رابط صحيح يتبعه http:// أو https://")
        return

    msg = bot.reply_to(message, "جاري المعالجة والتحميل... ⏳")

    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    
    for f in glob.glob('downloads/*'):
        try:
            os.remove(f)
        except Exception:
            pass

    # التعامل مع روابط إنستغرام
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

    # التعامل مع بقية المنصات عبر yt-dlp
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

# معالج الضغط على زر استخراج الصوت
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
