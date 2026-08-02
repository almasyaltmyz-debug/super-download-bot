import os
import glob
import re
import requests
from threading import Thread
from flask import Flask
import telebot
import yt_dlp
import instaloader

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
L = instaloader.Instaloader(download_videos=True, download_video_thumbnails=False, save_metadata=False, post_metadata_txt_pattern="")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def extract_clean_url(text):
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

def download_facebook_media(url):
    """تنزيل الفيديوهات من فيسبوك عبر yt-dlp بأفضل جودة"""
    try:
        ydl_opts = {
            'outtmpl': 'downloads/fb_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo+bestaudio/best',
            'user_agent': HEADERS['User-Agent'],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Facebook Error: {e}")
    return False

def download_instagram_fallback(url):
    """تنزيل الفيديو أو الصور من إنستغرام بذكاء"""
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

def download_tiktok_media(url):
    """تنزيل صور وفيديوهات تيك توك عبر TikWM API"""
    try:
        api_url = f"https://www.tikwm.com/api/?url={url}"
        response = requests.get(api_url, headers=HEADERS, timeout=15).json()
        
        if response.get('code') == 0:
            data = response.get('data', {})
            images = data.get('images')
            if images:
                for i, img_url in enumerate(images):
                    img_data = requests.get(img_url, headers=HEADERS).content
                    with open(f"downloads/tiktok_img_{i}.jpg", "wb") as f:
                        f.write(img_data)
                return True

            video_url = data.get('play') or data.get('wmplay')
            if video_url:
                vid_data = requests.get(video_url, headers=HEADERS).content
                with open("downloads/tiktok_video.mp4", "wb") as f:
                    f.write(vid_data)
                return True
    except Exception as e:
        print(f"TikTok API Error: {e}")
    return False 
    def download_pinterest_fallback(url):
    """فك روابط بنترست المختصرة وجلب الصورة بجودتها الأصلية"""
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

    # 1. تيك توك
    if 'tiktok.com' in url:
        download_tiktok_media(url)

    # 2. إنستغرام
    elif 'instagram.com' in url:
        download_instagram_fallback(url)

    # 3. فيسبوك (Facebook Videos & Reels)
    elif 'facebook.com' in url or 'fb.watch' in url or 'fb.gg' in url:
        download_facebook_media(url)

    # 4. بنترست
    elif 'pinterest.' in url or 'pin.it' in url:
        download_pinterest_fallback(url)

    # 5. باقي المنصات (YouTube/Twitter)
    else:
        try:
            ydl_opts = {
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'user_agent': HEADERS['User-Agent'],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception:
            pass

    # إرسال الملفات المُنَزَّلة
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
        bot.edit_message_text("عذراً، تعذر استخراج المحتوى من هذا الرابط. قد يكون المنشور خاصاً أو غير مدعوم. ❌", message.chat.id, msg.message_id)

bot.polling(non_stop=True)
