import telebot
import yt_dlp
import requests
import os

TOKEN = '8960864210:AAHxnc8I-qh6YPPzfJgv_4Pr7M20LV03Lyw'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "أهلاً بك في بوت التحميل الذكي! 🎬\n\n"
        "أرسل لي أي رابط فيديو (تيك توك، يوتيوب، إنستغرام، فيسبوك...) وسأقوم بتحميله فوراً."
    )

def download_tiktok(url):
    """تحميل فيديوهات تيك توك عبر API سريع وبدون علامة مائية"""
    api_url = f"https://api.douyin.wtseg.com/api/tiktok?url={url}"
    # سيرفر بديل سريع لتيك توك
    tik_api = f"https://tikwm.com/api/?url={url}"
    
    response = requests.get(tik_api, timeout=15).json()
    if response.get('code') == 0:
        video_url = response['data']['play']
        video_data = requests.get(video_url, timeout=30).content
        filename = "tiktok_video.mp4"
        with open(filename, 'wb') as f:
            f.write(video_data)
        return filename
    else:
        raise Exception("تعذر استخراج فيديو تيك توك")

@bot.message_handler(func=lambda message: True)
def process_video_link(message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "يرجى إرسال رابط فيديو صحيح يبدأ بـ http أو https.")
        return

    msg = bot.reply_to(message, "جاري معالجة الرابط وتحميل الفيديو... ⏳")
    filename = None

    try:
        # إذا كان الرابط من تيك توك
        if "tiktok.com" in url:
            filename = download_tiktok(url)
        else:
            # لمقاطع المواقع الأخرى (يوتيوب، فيسبوك، إلخ)
            ydl_opts = {
                'format': 'best',
                'outtmpl': 'downloaded_video.%(ext)s',
                'quiet': True,
                'nocheckcertificate': True,
                'socket_timeout': 30,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

        bot.edit_message_text("جاري رفع الفيديو إلى تيليجرام... 🚀", chat_id=msg.chat.id, message_id=msg.message_id)

        with open(filename, 'rb') as video_file:
            bot.send_video(message.chat.id, video_file, caption="تم التحميل بنجاح! 🎉")

    except Exception as e:
        bot.edit_message_text(f"حدث خطأ أثناء التحميل: {str(e)}", chat_id=msg.chat.id, message_id=msg.message_id)

    finally:
        # تنظيف الملف المكتمل من الجهاز
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass
        bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)

print("--- البوت المطور جاهز وسريع جداً ---")
bot.infinity_polling()