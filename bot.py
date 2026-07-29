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

def download_instagram_fallback(url):
    """تنزيل الصور والفيديوهات من إنستغرام عبر Instaloader"""
    try:
        shortcode_match = re.search(r'/(?:p|reel|tv)/([^/?#&]+)', url)
        if shortcode_match:
            shortcode = shortcode_match.group(1)
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            
            # إن كان المنشور ألبوماً أو صورة مفردة
            if post.typename == 'GraphSidecar':
                for i, node in enumerate(post.get_sidecar_nodes()):
                    img_data = requests.get(node.display_url, headers=HEADERS).content
                    with open(f"downloads/insta_{i}.jpg", "wb") as f:
                        f.write(img_data)
            else:
                img_data = requests.get(post.url, headers=HEADERS).content
                with open("downloads/insta_single.jpg", "wb") as f:
                    f.write(img_data)
            return True
    except Exception as e:
        print(f"Instaloader Error: {e}")
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

    # 1. المحاولة الأولى: yt-dlp (ممتاز للفيديوهات واليوتيوب وباقي المواقع)
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

    # 2. المحاولة الثانية: مخصصة لصور وفيديوهات إنستغرام عبر Instaloader
    if not glob.glob('downloads/*') and 'instagram.com' in url:
        download_instagram_fallback(url)

    # 3. المحاولة الثالثة: قراءة الصورة المباشرة لـ Pinterest وباقي المواقع
    if not glob.glob('downloads/*'):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            img_match = re.search(r'property="og:image"\s+content="([^"]+)"', resp.text) or \
                        re.search(r'content="([^"]+)"\s+property="og:image"', resp.text)
            if img_match:
                img_url = img_match.group(1).replace("&amp;", "&")
                img_bytes = requests.get(img_url, headers=HEADERS, timeout=10).content
                with open("downloads/pinterest_img.jpg", "wb") as f:
                    f.write(img_bytes)
        except Exception:
            pass

    # إرسال المحتوى المُنزّل
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
        bot.edit_message_text("عذراً، تعذر استخراج الصورة أو الفيديو من هذا الرابط. قد يكون الحساب خاصاً. ❌", message.chat.id, msg.message_id)

bot.polling(non_stop=True)
