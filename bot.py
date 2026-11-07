import os
import glob
import re
import uuid
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import yt_dlp
import instaloader

# إعدادات مهلة الاتصال لتجنب انقطاع الرفع
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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.tikwm.com/'
}

if not os.path.exists('downloads'):
    os.makedirs('downloads')

# فك الرابط المختصر وتحويل /photo/ إلى /video/ لتقبله جميع الواجهات
def prepare_tiktok_url(url):
    try:
        res = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=12)
        clean = res.url.split('?')[0]
    except Exception:
        clean = url.split('?')[0]
    
    # الخدعة الأساسية: استبدال photo بـ video ليتمكن الـ API من قراءة الألبوم
    normalized_url = clean.replace('/photo/', '/video/')
    return clean, normalized_url

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في البوت الشامل! 🚀\n\n"
        "✨ *الخدمات المتاحة:*\n"
        "1️⃣ *تيك توك:* تنزيل الفيديوهات بدون علامة مائية، وتنزيل ألبومات الصور كاملة مع الصوت.\n"
        "2️⃣ *إنستغرام:* تنزيل الريلز (Reels)، الفيديوهات، الصور المفردة، وألبومات الصور.\n"
        "3️⃣ *يوتيوب ومنصات أخرى:* تنزيل الفيديوهات بأعلى جودة متاحة.\n"
        "4️⃣ *استخراج الصوت:* تحويل أي فيديو لمقطع صوتي مباشرة عبر الزر المرفق.\n"
        "5️⃣ *استخراج النصوص (OCR):* أرسل أي صورة وسأستخرج النص العربي منها."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

def send_photo_album(chat_id, saved_files, music_url=None, title="ألبوم صور"):
    if not saved_files:
        return False

    for i in range(0, len(saved_files), 10):
        batch = saved_files[i:i + 10]
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

    for path in saved_files:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    if music_url:
        try:
            if not music_url.startswith('http'):
                music_url = "https://www.tikwm.com" + music_url
            audio_res = requests.get(music_url, headers=HEADERS, timeout=25)
            if audio_res.status_code == 200 and len(audio_res.content) > 1000:
                audio_path = f"downloads/tk_audio_{chat_id}_{uuid.uuid4().hex[:4]}.mp3"
                with open(audio_path, 'wb') as f:
                    f.write(audio_res.content)
                with open(audio_path, 'rb') as af:
                    bot.send_audio(chat_id, af, title=str(title)[:40], caption=f"🎵 {str(title)[:60]}")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
        except Exception as err:
            print(f"Error sending audio: {err}")
    return True

# ==================== معالج تيك توك (فيديو + ألبومات صور) ====================
def download_tiktok_content(chat_id, raw_url, status_msg_id):
    clean_url, normalized_url = prepare_tiktok_url(raw_url)

    # نجرب الرابط المعدل (/video/) ثم الرابط الخام لضمان الاستجابة 100%
    urls_to_try = [normalized_url, raw_url, clean_url]

    # المحاولة الأولى: TikWM API
    for target in urls_to_try:
        try:
            api_url = "https://www.tikwm.com/api/"
            payload = {'url': target, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}
            res = requests.post(api_url, data=payload, headers=HEADERS, timeout=20)

            if res.status_code == 200 and res.text.strip():
                json_data = res.json()
                if json_data.get('code') == 0 and json_data.get('data'):
                    data = json_data['data']

                    # 1. إذا كان ألبوم صور (Slideshow)
                    images = data.get('images')
                    if images and isinstance(images, list):
                        music_url = data.get('music') or data.get('play')
                        title = data.get('title') or 'ألبوم صور تيك توك'
                        saved_files = []

                        for idx, img_url in enumerate(images):
                            try:
                                if not img_url.startswith('http'):
                                    img_url = "https://www.tikwm.com" + img_url
                                r = requests.get(img_url, headers=HEADERS, timeout=15)
                                if r.status_code == 200 and len(r.content) > 500:
                                    img_path = f"downloads/tk_img_{chat_id}_{idx}_{uuid.uuid4().hex[:4]}.jpg"
                                    with open(img_path, 'wb') as f:
                                        f.write(r.content)
                                    saved_files.append(img_path)
                            except Exception as err:
                                print(f"Error downloading TikTok image {idx}: {err}")

                        if saved_files:
                            send_photo_album(chat_id, saved_files, music_url, title)
                            bot.delete_message(chat_id, status_msg_id)
                            return True

                    # 2. إذا كان فيديو عادي
                    video_url = data.get('hdplay') or data.get('play')
                    if video_url:
                        if not video_url.startswith('http'):
                            video_url = "https://www.tikwm.com" + video_url
                        v_res = requests.get(video_url, headers=HEADERS, timeout=35)

                        if len(v_res.content) > MAX_TELEGRAM_SIZE and data.get('play'):
                            play_url = data.get('play')
                            if not play_url.startswith('http'):
                                play_url = "https://www.tikwm.com" + play_url
                            v_res = requests.get(play_url, headers=HEADERS, timeout=35)

                        video_path = f"downloads/tk_vid_{chat_id}_{uuid.uuid4().hex[:4]}.mp4"
                        with open(video_path, 'wb') as f:
                            f.write(v_res.content)

                        if os.path.getsize(video_path) <= MAX_TELEGRAM_SIZE:
                            short_key = uuid.uuid4().hex[:8]
                            URL_CACHE[short_key] = normalized_url
                            markup = InlineKeyboardMarkup()
                            btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"ext_{short_key}")
                            markup.add(btn)

                            with open(video_path, 'rb') as vf:
                                bot.send_video(chat_id, vf, caption="تم تنزيل الفيديو بنجاح! 🎬✨", reply_markup=markup, timeout=300)

                            if os.path.exists(video_path):
                                os.remove(video_path)
                            bot.delete_message(chat_id, status_msg_id)
                            return True
                        else:
                            if os.path.exists(video_path):
                                os.remove(video_path)
        except Exception as e:
            print(f"TikWM attempt failed for {target}: {e}")

    # المحاولة الثانية: TiklyDown API (باستخدام الرابط المعدل أيضاً)
    for target in [normalized_url, clean_url]:
        try:
            fallback_api = f"https://api.tiklydown.eu.org/api/download?url={target}"
            f_res = requests.get(fallback_api, headers=HEADERS, timeout=20)
            if f_res.status_code == 200:
                f_data = f_res.json()
                if 'images' in f_data and f_data['images']:
                    images = [img['url'] if isinstance(img, dict) else img for img in f_data['images']]
                    music_url = f_data.get('music', {}).get('play_url') if isinstance(f_data.get('music'), dict) else None
                    title = f_data.get('title', 'ألبوم صور تيك توك')
                    saved_files = []

                    for idx, img_url in enumerate(images):
                        r = requests.get(img_url, headers=HEADERS, timeout=15)
                        if r.status_code == 200:
                            img_path = f"downloads/tk2_img_{chat_id}_{idx}_{uuid.uuid4().hex[:4]}.jpg"
                            with open(img_path, 'wb') as f:
                                f.write(r.content)
                            saved_files.append(img_path)

                    if saved_files:
                        send_photo_album(chat_id, saved_files, music_url, title)
                        bot.delete_message(chat_id, status_msg_id)
                        return True
        except Exception as e:
            print(f"TiklyDown fallback failed: {e}")

    return False

# ==================== معالج إنستغرام (صور + ألبومات + ريلز) ====================
def download_instagram_content(chat_id, raw_url, status_msg_id):
    req_id = uuid.uuid4().hex[:6]
    target_dir = f"downloads/insta_{chat_id}_{req_id}"
    
    match = re.search(r'instagram\.com/(?:[A-Za-z0-9_.-]+/)?(?:p|reel|tv)/([A-Za-z0-9_-]+)', raw_url)
    if not match:
        return False
    
    shortcode = match.group(1)

    try:
        L = instaloader.Instaloader(
            dirname_pattern=target_dir,
            filename_pattern='{shortcode}',
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            quiet=True
        )
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=target_dir)

        downloaded_files = sorted(glob.glob(f"{target_dir}/*"))
        media_files = [f for f in downloaded_files if f.split('.')[-1].lower() in ['jpg', 'jpeg', 'png', 'webp', 'mp4']]

        if media_files:
            photos = [f for f in media_files if f.split('.')[-1].lower() in ['jpg', 'jpeg', 'png', 'webp']]
            videos = [f for f in media_files if f.split('.')[-1].lower() == 'mp4']

            for v_path in videos:
                if os.path.getsize(v_path) <= MAX_TELEGRAM_SIZE:
                    short_key = uuid.uuid4().hex[:8]
                    URL_CACHE[short_key] = raw_url
                    markup = InlineKeyboardMarkup()
                    btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"ext_{short_key}")
                    markup.add(btn)
                    with open(v_path, 'rb') as vf:
                        bot.send_video(chat_id, vf, caption="تم التنزيل من إنستغرام بنجاح! 🎬✨", reply_markup=markup, timeout=300)

            if photos and not (len(videos) == 1 and len(photos) == 1 and not post.typename == 'GraphSidecar'):
                send_photo_album(chat_id, photos)

            for f in glob.glob(f"{target_dir}/*"):
                try:
                    os.remove(f)
                except Exception:
                    pass
            try:
                os.rmdir(target_dir)
            except Exception:
                pass

            bot.delete_message(chat_id, status_msg_id)
            return True
    except Exception as e:
        print(f"Instaloader attempt note: {e}")
        for f in glob.glob(f"{target_dir}/*"):
            try:
                os.remove(f)
            except Exception:
                pass
        try:
            if os.path.exists(target_dir):
                os.rmdir(target_dir)
        except Exception:
            pass

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

# ==================== المعالج العام للروابط والرسائل ====================
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if not message.text:
        return
    text_input = message.text.strip()
    urls = re.findall(r'https?://[^\s]+', text_input)
    
    if urls:
        raw_url = urls[0]
        msg = bot.reply_to(message, "جاري المعالجة وتنزيل المحتوى... ⏳")

        # 1. إذا كان الرابط تيك توك
        if 'tiktok.com' in raw_url:
            if download_tiktok_content(message.chat.id, raw_url, msg.message_id):
                return
            # إذا فشل وكان الرابط يحتوي على /photo/ نوقف المحاولة هنا لأن yt-dlp لا يدعم صور تيك توك
            clean_check, norm_check = prepare_tiktok_url(raw_url)
            if '/photo/' in clean_check:
                bot.edit_message_text("عذراً، تعذر جلب ألبوم الصور حالياً، يرجى المحاولة بعد قليل. ❌", message.chat.id, msg.message_id)
                return
            raw_url = norm_check

        # 2. إذا كان الرابط إنستغرام
        if 'instagram.com' in raw_url:
            if download_instagram_content(message.chat.id, raw_url, msg.message_id):
                return

        # 3. المعالج الشامل للفيديوهات عبر (yt-dlp)
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
                        bot.edit_message_text("⚠️ حجم هذا المقطع يزيد عن 50 ميجابايت (الحد المسموح للبوتات في تليجرام).", message.chat.id, msg.message_id)
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
            else:
                bot.edit_message_text("عذراً، تعذر استخراج المحتوى من هذا الرابط. ❌", message.chat.id, msg.message_id)

        except Exception as e:
            bot.edit_message_text("عذراً، تعذر استخراج المحتوى أو أن الحساب خاص. ❌", message.chat.id, msg.message_id)
            print(f"Download error: {e}")
            
        finally:
            for f in downloaded_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
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
        print(f"Audio error: {e}")
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
