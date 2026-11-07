import os
import glob
import re
import uuid
import shutil
import subprocess
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import yt_dlp

apihelper.CONNECT_TIMEOUT = 120
apihelper.READ_TIMEOUT = 300

MAX_TELEGRAM_SIZE = 49 * 1024 * 1024

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

URL_CACHE = {}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    'Accept': 'application/json, text/plain, */*'
}

if not os.path.exists('downloads'):
    os.makedirs('downloads')

def unshorten_url(url):
    try:
        res = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
        return res.url.split('?')[0]
    except Exception:
        return url.split('?')[0]

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في البوت الشامل! 🚀\n\n"
        "✨ *الخدمات المتاحة:*\n"
        "1️⃣ *تيك توك وإنستغرام:* تنزيل الفيديوهات، الريلز، وألبومات الصور مع الصوت.\n"
        "2️⃣ *يوتيوب وتويتر:* تنزيل الفيديوهات بأعلى جودة.\n"
        "3️⃣ *استخراج الصوت:* تحويل الفيديو لمقطع صوتي عبر الزر المرفق.\n"
        "4️⃣ *استخراج النصوص (OCR):* قراءة النصوص العربية من الصور."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

def send_downloaded_album(chat_id, image_paths, audio_paths=None):
    if not image_paths:
        return False

    # إرسال الصور في مجموعات (10 صور كحد أقصى لكل ألبوم)
    for i in range(0, len(image_paths), 10):
        batch = image_paths[i:i + 10]
        media_group = []
        open_handles = []
        try:
            for path in batch:
                fh = open(path, 'rb')
                open_handles.append(fh)
                media_group.append(InputMediaPhoto(fh))

            if len(media_group) == 1:
                open_handles[0].seek(0)
                bot.send_photo(chat_id, open_handles[0], caption="✅ تم تنزيل الصورة بنجاح!")
            else:
                bot.send_media_group(chat_id, media_group)
        finally:
            for fh in open_handles:
                fh.close()

    # إرسال الصوت المرفق إن وجد
    if audio_paths:
        for a_path in audio_paths:
            try:
                with open(a_path, 'rb') as af:
                    bot.send_audio(chat_id, af, title="الصوت المرفق 🎵")
            except Exception as e:
                print(f"Audio send error: {e}")

    return True

# ==================== محرك سحب الصور والألبومات (gallery-dl + API) ====================
def download_images_and_slides(chat_id, raw_url, status_msg_id):
    clean_url = unshorten_url(raw_url)
    job_dir = f"downloads/job_{chat_id}_{uuid.uuid4().hex[:6]}"
    os.makedirs(job_dir, exist_ok=True)

    try:
        # 1. المحاولة عبر محرك gallery-dl المخصص للصور (يدعم تيك توك photo وإنستغرام)
        cmd = [
            "gallery-dl",
            "--directory", job_dir,
            "--user-agent", HEADERS['User-Agent'],
            raw_url
        ]
        subprocess.run(cmd, timeout=45, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        all_files = []
        for root, _, files in os.walk(job_dir):
            for file in files:
                all_files.append(os.path.join(root, file))

        all_files.sort()
        images = [f for f in all_files if f.split('.')[-1].lower() in ['jpg', 'jpeg', 'png', 'webp']]
        audios = [f for f in all_files if f.split('.')[-1].lower() in ['mp3', 'm4a', 'wav', 'ogg']]
        videos = [f for f in all_files if f.split('.')[-1].lower() in ['mp4', 'mov', 'webm']]

        if images:
            send_downloaded_album(chat_id, images, audios)
            bot.delete_message(chat_id, status_msg_id)
            return True

        if videos:
            for v_path in videos:
                if os.path.getsize(v_path) <= MAX_TELEGRAM_SIZE:
                    with open(v_path, 'rb') as vf:
                        bot.send_video(chat_id, vf, caption="تم التنزيل بنجاح! 🎬✨", timeout=300)
            bot.delete_message(chat_id, status_msg_id)
            return True

        # 2. محاولة احتياطية لتيك توك عبر TikWM مع تمرير الرابط المختصر والأصلي
        if 'tiktok.com' in raw_url:
            for target_u in [raw_url, clean_url.replace('/photo/', '/video/')]:
                res = requests.post(
                    "https://www.tikwm.com/api/",
                    data={'url': target_u, 'web': 1, 'hd': 1},
                    headers=HEADERS,
                    timeout=15
                )
                if res.status_code == 200:
                    data = res.json().get('data', {})
                    if data and data.get('images'):
                        saved_imgs = []
                        for idx, img_u in enumerate(data['images']):
                            if not img_u.startswith('http'):
                                img_u = "https://www.tikwm.com" + img_u
                            ir = requests.get(img_u, headers=HEADERS, timeout=15)
                            if ir.status_code == 200:
                                p = os.path.join(job_dir, f"img_{idx}.jpg")
                                with open(p, 'wb') as f:
                                    f.write(ir.content)
                                saved_imgs.append(p)

                        saved_aud = []
                        music_u = data.get('music')
                        if music_u:
                            if not music_u.startswith('http'):
                                music_u = "https://www.tikwm.com" + music_u
                            ar = requests.get(music_u, headers=HEADERS, timeout=15)
                            if ar.status_code == 200:
                                ap = os.path.join(job_dir, "audio.mp3")
                                with open(ap, 'wb') as f:
                                    f.write(ar.content)
                                saved_aud.append(ap)

                        if saved_imgs:
                            send_downloaded_album(chat_id, saved_imgs, saved_aud)
                            bot.delete_message(chat_id, status_msg_id)
                            return True
    except Exception as e:
        print(f"Gallery/Album error: {e}")
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

    return False

# ==================== معالج قراءة النصوص (OCR) ====================
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
                    f"📝 *النص المستخرج من الصورة:*\n\n{extracted_text}",
                    message.chat.id,
                    msg.message_id,
                    parse_mode="Markdown"
                )
                return

        bot.edit_message_text("عذراً، لم يتم العثور على نص واضح داخل الصورة. ❌", message.chat.id, msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"حدث خطأ أثناء المعالجة: {str(e)}", message.chat.id, msg.message_id)

# ==================== المعالج العام للروابط ====================
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if not message.text:
        return
    text_input = message.text.strip()
    urls = re.findall(r'https?://[^\s]+', text_input)
    
    if urls:
        raw_url = urls[0]
        msg = bot.reply_to(message, "جاري المعالجة وتنزيل المحتوى... ⏳")

        clean_check = unshorten_url(raw_url)

        # إذا كان الرابط ألبوم صور تيك توك أو منشور صور إنستغرام، نوجهه لمحرك الصور أولاً
        if '/photo/' in clean_check or ('instagram.com/p/' in clean_check):
            if download_images_and_slides(message.chat.id, raw_url, msg.message_id):
                return

        # محاولة تنزيل الفيديو عبر yt-dlp
        req_id = uuid.uuid4().hex[:6]
        output_template = f'downloads/{message.chat.id}_{req_id}_%(id)s.%(ext)s'

        ydl_opts = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'format': 'best[filesize<48M]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best',
            'http_headers': HEADERS
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
                        bot.edit_message_text("⚠️ حجم هذا المقطع يزيد عن 50 ميجابايت.", message.chat.id, msg.message_id)
                        continue

                    ext = file_path.split('.')[-1].lower()
                    
                    if ext in ['jpg', 'jpeg', 'png', 'webp']:
                        with open(file_path, 'rb') as file_data:
                            bot.send_photo(message.chat.id, file_data, caption="✅ تم التنزيل بنجاح!", timeout=120)
                        
                    elif ext in ['mp4', 'mkv', 'webm', 'mov']:
                        short_key = uuid.uuid4().hex[:8]
                        URL_CACHE[short_key] = raw_url
                        markup = InlineKeyboardMarkup()
                        btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"ext_{short_key}")
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
                return

        except Exception as e:
            print(f"yt-dlp fallback to gallery-dl: {e}")
        finally:
            for f in downloaded_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

        # إذا فشل yt-dlp (لأن الرابط طلع ألبوم صور مختصر مثلاً)، نجرب محرك الصور تلقائياً
        if download_images_and_slides(message.chat.id, raw_url, msg.message_id):
            return

        bot.edit_message_text("عذراً، تعذر استخراج المحتوى من هذا الرابط. ❌", message.chat.id, msg.message_id)
    else:
        bot.reply_to(message, "يرجى إرسال رابط فيديو/صورة للتنزيل، أو صورة تحتوي على نص لقراءتها. 📌")

# ==================== معالج زر استخراج الصوت ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('ext_'))
def handle_audio_extraction_callback(call):
    short_key = call.data.replace('ext_', '')
    target_url = URL_CACHE.get(short_key)
    
    if not target_url:
        bot.answer_callback_query(call.id, "انتهت صلاحية الرابط، أرسل الفيديو مجدداً. ❌", show_alert=True)
        return

    bot.answer_callback_query(call.id, "جاري استخراج وتحميل الصوت... ⏳")
    
    req_id = uuid.uuid4().hex[:6]
    audio_out_tmpl = f'downloads/audio_{call.message.chat.id}_{req_id}.%(ext)s'
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': audio_out_tmpl,
        'quiet': True,
        'http_headers': HEADERS
    }
    
    downloaded_audio = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])
            
        downloaded_audio = glob.glob(f'downloads/audio_{call.message.chat.id}_{req_id}.*')
        
        if downloaded_audio:
            audio_path = downloaded_audio[0]
            with open(audio_path, 'rb') as af:
                bot.send_audio(call.message.chat.id, af, title="الصوت المستخرج 🎵")
        else:
            bot.send_message(call.message.chat.id, "❌ تعذر استخراج الصوت من هذا المقطع.")
            
    except Exception as e:
        bot.send_message(call.message.chat.id, "❌ حدث خطأ أثناء استخراج الصوت.")
    finally:
        for f in downloaded_audio:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

def start_bot():
    try:
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
        print("Webhook cleared successfully")
    except Exception as e:
        print(f"Webhook note: {e}")
    print("🤖 البوت يعمل الآن ويستمع للرسائل...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)

bot_thread = Thread(target=start_bot)
bot_thread.daemon = True
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
