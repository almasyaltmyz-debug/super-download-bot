import os
import requests
import yt_dlp
import telebot

# --- (كود Flask لضمان الاستمرارية يظل كما هو في البداية) ---

TOKEN = 'ضع_التوكين_الخاص_بك_هنا'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(func=lambda message: True)
def handle_all_links(message):
    url = message.text.strip()
    
    # التأكد أن الرسالة تحتوي على رابط
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "من فضلك أرسل رابطاً صحيحاً للتحميل 🔗")
        return

    msg = bot.reply_to(message, "جاري معالجة الرابط وجلب المحتوى... ⏳")

    # إعدادات yt-dlp لاستخراج البيانات دون تحميل مقدماً
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # 1️⃣ التعامل مع ألبومات الصور / السلايدات (Carousel / Playlist)
            if 'entries' in info:
                for entry in info['entries']:
                    send_media_item(message.chat.id, entry)
            # 2️⃣ التعامل مع عنصر واحد (صورة واحدة أو فيديو واحد)
            else:
                send_media_item(message.chat.id, info)
                
            bot.delete_message(message.chat.id, msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"عذراً، تعذر تحميل الرابط! التأكد من صحته أو الخصوصية. ❌\nالخطأ: {str(e)}", message.chat.id, msg.message_id)

def send_media_item(chat_id, item_info):
    """دالة فرعية للتمييز بين الصورة والفيديو وإرسالها"""
    url = item_info.get('url') or item_info.get('webpage_url')
    ext = item_info.get('ext', '')
    
    # إذا كان خيار الإدخال عبارة عن صورة
    if ext in ['jpg', 'jpeg', 'png', 'webp'] or item_info.get('vcodec') == 'none':
        # إذا توفرت صورة مباشرة أو رابط معينة
        photo_url = item_info.get('url') or item_info.get('thumbnail')
        if photo_url:
            bot.send_photo(chat_id, photo_url)
    else:
        # إذا كان فيديو
        video_url = item_info.get('url')
        if video_url:
            bot.send_video(chat_id, video_url)

# --- (كود keep_alive والـ bot.polling) ---
