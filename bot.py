# معالج الصور لاستخراج النص (OCR)
@bot.message_handler(content_types=['photo'])
def handle_photo_ocr(message):
    msg = bot.reply_to(message, "جاري قراءة النص من الصورة... 🔍")
    
    try:
        # الحصول على الصورة بأعلى دقة
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        payload = {
            'apikey': OCR_API_KEY,
            'language': 'ara',  # اللغة العربية
            'isOverlayRequired': False,
            'detectOrientation': True,
            'scale': True,
            'OCREngine': 2  # استخدام المحرك الثاني وهو الأقوى في تحليلات النصوص العربية
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
            else:
                bot.edit_message_text("عذراً، لم يتم العثور على نص واضح داخل الصورة. ❌", message.chat.id, msg.message_id)
        else:
            error_msg = result.get('ErrorMessage', ['حدث خطأ في قراءة الصورة'])[0]
            bot.edit_message_text(f"لم نتمكن من قراءة الصورة: {error_msg} ❌", message.chat.id, msg.message_id)

    except requests.exceptions.Timeout:
        bot.edit_message_text("تأخرت الاستجابة من السيرفر، يرجى المحاولة مرة أخرى بصورة أصغر حجماً. ⏳", message.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"حدث خطأ أثناء المعالجة: {str(e)}", message.chat.id, msg.message_id)
