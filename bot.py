# تنزيل ومعالجة تيك توك عبر TikWM API مع محاولة احتياطية عبر yt-dlp
def download_tiktok_content(chat_id, raw_url, status_msg_id):
    # 1. التجربة الأولى عبر TikWM API
    try:
        api_url = "https://www.tikwm.com/api/"
        payload = {'url': raw_url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}
        res = requests.post(api_url, data=payload, headers=HEADERS, timeout=20)
        
        if res.status_code == 200 and res.text.strip():
            json_data = res.json()
            if json_data.get('code') == 0:
                data = json_data.get('data', {})

                # حالة ألبوم الصور (Slideshow)
                if 'images' in data and data['images']:
                    images = data['images']
                    music_url = data.get('music')
                    title = data.get('title', 'ألبوم صور تيك توك')

                    saved_files = []
                    for idx, img_url in enumerate(images):
                        try:
                            r = requests.get(img_url, headers=HEADERS, timeout=15)
                            if r.status_code == 200:
                                img_path = f"downloads/tk_img_{chat_id}_{idx}_{uuid.uuid4().hex[:4]}.jpg"
                                with open(img_path, 'wb') as f:
                                    f.write(r.content)
                                saved_files.append(img_path)
                        except Exception as err:
                            print(f"Error fetching image: {err}")

                    for i in range(0, len(saved_files), 10):
                        batch = saved_files[i:i + 10]
                        media_group = []
                        open_handles = []
                        for path in batch:
                            fh = open(path, 'rb')
                            open_handles.append(fh)
                            media_group.append(InputMediaPhoto(fh))

                        bot.send_media_group(chat_id, media_group)
                        for fh in open_handles:
                            fh.close()

                    for path in saved_files:
                        if os.path.exists(path):
                            os.remove(path)

                    if music_url:
                        try:
                            audio_res = requests.get(music_url, headers=HEADERS, timeout=25)
                            if audio_res.status_code == 200:
                                audio_path = f"downloads/tk_audio_{chat_id}_{uuid.uuid4().hex[:4]}.mp3"
                                with open(audio_path, 'wb') as f:
                                    f.write(audio_res.content)
                                with open(audio_path, 'rb') as af:
                                    bot.send_audio(chat_id, af, title=title[:40], caption=f"🎵 {title[:60]}")
                                if os.path.exists(audio_path):
                                    os.remove(audio_path)
                        except Exception as err:
                            print(f"Error sending audio: {err}")

                    bot.delete_message(chat_id, status_msg_id)
                    return True

                # حالة الفيديو العادي
                video_url = data.get('play')
                if video_url:
                    v_res = requests.get(video_url, headers=HEADERS, timeout=30)
                    video_path = f"downloads/tk_vid_{chat_id}_{uuid.uuid4().hex[:4]}.mp4"
                    with open(video_path, 'wb') as f:
                        f.write(v_res.content)

                    markup = InlineKeyboardMarkup()
                    btn = InlineKeyboardButton("استخراج الصوت 🎵", callback_data=f"extaudio_{raw_url}")
                    markup.add(btn)

                    with open(video_path, 'rb') as vf:
                        bot.send_video(chat_id, vf, caption="تم تنزيل الفيديو بنجاح! 🎬✨", reply_markup=markup)

                    if os.path.exists(video_path):
                        os.remove(video_path)

                    bot.delete_message(chat_id, status_msg_id)
                    return True
    except Exception as e:
        print(f"TikWM attempt failed: {e}")

    # 2. التجربة الاحتياطية تلقائياً عبر yt-dlp في حال فشل السيرفر الأولي
    return False
