from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from moviepy.editor import VideoFileClip
import os
import glob
import re
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot import apihelper
import yt_dlp
import instaloader
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
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

keep_alive()

TOKEN = '8960864210:AAGg1wQKE5_kwh05FTXPvA30xhc-IrnJrdk'
bot = telebot.TeleBot(TOKEN)
L = instaloader.Instaloader(download_videos=True, download_video_thumbnails=False, save_metadata=False, post_metadata_txt_pattern="")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def extract_clean_url(text):
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

def download_tiktok_media(url):
    """تنزيل من تيك توك باستخدام yt-dlp ومحاولة محرك TikWM كخيار احتياطي"""
    try:
        ydl_opts = {
            'outtmpl': 'downloads/tiktok_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo+bestaudio/best',
            'user_agent': HEADERS['User-Agent'],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if glob.glob('downloads/tiktok_*'):
            return True
    except Exception as e:
        print(f"TikTok yt-dlp Error: {e}")

    try:
        api_url = f"https://www.tikwm.com/api/?url={url}"
        response = requests.get(api_url, headers=HEADERS, timeout=10).json()
        if response.get('code') == 0:
            data = response.get('data', {})
            images = data.get('images')
            if images:
                for i, img_url in enumerate(images):
                    img_data = requests.get(img_url, headers=HEADERS).content
                    with open(f"downloads/tiktok_img_{i}.jpg", "wb") as f:
                        f.write(img_data)
                return True
    except Exception as e:
        print(f"TikTok API Error: {e}")
    return False

def download_facebook_media(url):
    try:
        ydl_opts = {
            'outtmpl': 'downloads/fb_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'format': 'best[height<=720]/best',
            'user_agent': HEADERS['User-Agent'],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Facebook Error: {e}")
    return False

def download_instagram_fallback(url):
    try:
        shortcode_match = re.search(r'/(?:p|reel|reels|tv)/([^/?#&]+)', url)
        if shortcode_match:
            shortcode = shortcode_match.group(1)
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            
            if post.typename == 'GraphSidecar':
                for i, node in enumerate(post.get_sidecar_nodes()):
                    if node.is_video:
                        vid_data = requests.get(node.video_url, headers=HEADERS).content
                        with open(f"downloads/insta_vid_{i}.mp4", "wb") as f:
                            f.write(vid_data)
                    else:
                        img_data = requests.get(node.display_url, headers=HEADERS).content
                        with open(f"downloads/insta_img_{i}.jpg", "wb") as f:
                            f.write(img_data)
                return True

            elif post.is_video:
                vid_data = requests.get(post.video_url, headers=HEADERS).content
                with open("downloads/insta_video.mp4", "wb") as f:
                    f.write(vid_data)
                return True

            else:
                img_data = requests.get(post.url, headers=HEADERS).content
                with open("downloads/insta_single.jpg", "wb") as f:
                    f.write(img_data)
                return True
    except Exception as e:
        print(f"Instaloader Error: {e}")
    return False

def download_pinterest_fallback(url):
    try:
        session = requests.Session()
        response = session.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
        html = response.text
        
        img_match = re.search(r'property="og:image"\s+content="([^"]+)"', html) or \
                    re.search(r'name="twitter:image"\s+content="([^"]+)"', html) or \
                    re.search(r'https://i\.pinimg\.com/originals/[^\s"<>]+', html)

        if img_match:
            img_url = img_match.group(1) if 'content=' in img_match.group(0) or img_match.lastindex else img_match.group(0)
            img_url = img_url.replace("&amp;", "&")
            img_url = re.sub(r'/\d+x/', '/originals/', img_url)

            img_data = requests.get(img_url, headers=HEADERS, timeout=15).content
            with open("downloads/pinterest_image.jpg", "wb") as f:
                f.write(img_data)
            return True
    except Exception as e:
        print(f"Pinterest Error: {e}")
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

    if 'tiktok.com' in url or 'vt.tiktok.com' in url:
        download_tiktok_media(url)
    elif 'instagram.com' in url:
        download_instagram_fallback(url)
    elif 'facebook.com' in url or 'fb.watch' in url or 'fb.gg' in url:
        download_facebook_media(url)
    elif 'pinterest.' in url or 'pin.it' in url:
        download_pinterest_fallback(url)
    else:
        try:
            ydl_opts = {
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'format': 'best[height<=720]/best',
                'user_agent': HEADERS['User-Agent'],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
                    bot.send_video(message.chat.id, video_file, caption="تم تنزيل الفيديو بنجاح! 🎬", reply_markup=markup, timeout=300)
            else:
                with open(file_path, 'rb') as file_data:
                    bot.send_document(message.chat.id, file_data, timeout=300)
                os.remove(file_path)
            bot.delete_message(message.chat.id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"حدث خطأ أثناء إرسال الملف: ❌\n`{str(e)}`", message.chat.id, msg.message_id, parse_mode='Markdown')
    else:
        bot.edit_message_text("عذراً، تعذر استخراج المحتوى من هذا الرابط. قد يكون المنشور خاصاً أو غير مدعوم. ❌", message.chat.id, msg.message_id)

bot.polling(non_stop=True)
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
