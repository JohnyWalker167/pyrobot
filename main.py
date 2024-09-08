import os
import re
import time
import subprocess
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums, types
from urllib.parse import urlparse, parse_qs, unquote
from config import *
from utils import get_duration, remove_unwanted

app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1000,
    parse_mode=enums.ParseMode.HTML,
    in_memory=True
)

spoiler_settings = {}
# Initialize start time
BotTimes = type("BotTimes", (object,), {"task_start": datetime.now()})

def extract_filename(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    
    # Assume the file parameter contains the filename
    if 'file' in query_params:
        filename = os.path.basename(unquote(query_params['file'][0]))
    else:
        filename = 'downloaded_file'  # Default if no filename is found

    print(f"Extracted filename: {filename}")
    return filename

async def progress(current, total, message, last_edit_time, last_data, status):
    percentage = current * 100 / total
    bar_length = 20  # Length of the progress bar
    dots = int(bar_length * (current / total))
    bar = '●' * dots + '○' * (bar_length - dots)
    
    elapsed_time = time.time() - last_edit_time[0]
    speed = ((current - last_data[0]) / 1024 / 1024) / elapsed_time  # MB per second

    if elapsed_time >= 3:
        progress_message = (
            f"Status: {status}\n"
            f"[{bar}] {percentage:.1f}%\n"
            f"Speed: {speed:.2f} MB/s"
        )
        await message.edit_text(progress_message)
        
        last_edit_time[0] = time.time()
        last_data[0] = current

@app.on_message(filters.private & (filters.document | filters.video | filters.photo))
async def pyro_task(client, message):
    start_time = time.time()
    last_edit_time = [start_time]  # Store as list to pass by reference
    last_data = [0]  # Track the last amount of data transferred
    caption = await remove_unwanted(message.caption)

    # Initialize the has_spoiler setting for this task/message
    spoiler_settings[message.id] = False

    rply = await message.reply_text(
        f"Please send a photo\nSelect the spoiler setting:",
        reply_markup=types.InlineKeyboardMarkup(
            [
                [types.InlineKeyboardButton("True", callback_data=f"set_spoiler_true_{message.id}")],
                [types.InlineKeyboardButton("False", callback_data=f"set_spoiler_false_{message.id}")]
            ]
        )
    )
    
    photo_msg = await app.listen(message.chat.id, filters=filters.photo)
    
    thumb_path = await app.download_media(photo_msg, file_name=f'photo_{message.id}.jpg')
    
    progress_msg = await rply.edit_text("Starting download...")
    
    try:
        file_path = await app.download_media(message, file_name=f"{caption}", 
                                             progress=progress, progress_args=(progress_msg, last_edit_time, last_data, "Downloading"))
        
        duration = await get_duration(file_path)
        
        if not os.path.exists(thumb_path):
            await message.reply_text("Please set a custom thumbnail first.")
            return

        await app.send_video(chat_id=message.chat.id, 
                             video=file_path, 
                             caption=f"<code>{message.caption}</code>",
                             has_spoiler=spoiler_settings[message.id],  # Use the stored spoiler setting
                             duration=duration, 
                             width=480, 
                             height=320, 
                             thumb=thumb_path, 
                             progress=progress, 
                             progress_args=(progress_msg, last_edit_time, last_data, "Uploading")
                            )
        
        await progress_msg.edit_text("Uploaded ✅")
        
    except Exception as e:
        logger.error(f'{e}')
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        # Clean up the spoiler setting for this message ID
        spoiler_settings.pop(message.id, None)

@app.on_message(filters.text)
async def handle_download(client, message):
    if message.text.startswith("http://") or message.text.startswith("https://"):
        download_url = message.text
        filename = extract_filename(download_url)

        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")

        progress_msg = await message.reply_text("Starting download...")

        command = [
            "aria2c",
            "--continue=true",
            "--max-connection-per-server=4",
            "--split=4",
            "--summary-interval=1",
            "--console-log-level=notice",
            "--dir=" + downloads_dir,  
            "--out=" + filename,
            download_url
        ]

        BotTimes.task_start = datetime.now()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        await asyncio.sleep(5)  # Adding sleep to prevent floodwait

        process.communicate()  # Wait for the process to complete

        await progress_msg.edit_text(f"Download complete! `{filename}`")
        
        await asyncio.sleep(5)  # Adding sleep to prevent floodwait

@app.on_message(filters.command("upload"))
async def upload_downloaded_file(client, message):
    try:
        start_time = time.time()
        last_edit_time = [start_time]  # Store as list to pass by reference
        last_data = [0]  # Track the last amount of data transferred
        # Initialize the has_spoiler setting for this task/message
        spoiler_settings[message.id] = False

        rply = await message.reply_text(
            f"Please send a photo\nSelect the spoiler setting:",
            reply_markup=types.InlineKeyboardMarkup(
                [
                    [types.InlineKeyboardButton("True", callback_data=f"set_spoiler_true_{message.id}")],
                    [types.InlineKeyboardButton("False", callback_data=f"set_spoiler_false_{message.id}")]
                ]
            )
        )
        
        photo_msg = await app.listen(message.chat.id, filters=filters.photo)
        
        thumb_path = await app.download_media(photo_msg, file_name=f'photo_{message.id}.jpg')

        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        
        if len(message.command) < 2:
            await message.reply_text("Please specify the file name.")
            return
        
        filename = message.command[1]
        file_path = os.path.join(downloads_dir, filename)

        duration = await get_duration(file_path)
        progress_msg = await rply.edit_text("Starting upload...")

        if os.path.exists(file_path):
            await app.send_video(chat_id=message.chat.id, 
                                video=file_path, 
                                caption=f"<code>{filename}</code>",
                                has_spoiler=spoiler_settings[message.id],  # Use the stored spoiler setting
                                duration=duration, 
                                width=480, 
                                height=320, 
                                thumb=thumb_path, 
                                progress=progress, 
                                progress_args=(progress_msg, last_edit_time, last_data, "Uploading")
                                )
            await progress_msg.edit_text(f"File `{filename}` uploaded successfully!")
        else:
            await progress_msg.edit_text(f"File `{filename}` not found.")
    except Exception as e:
        logger.error(f"{e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        # Clean up the spoiler setting for this message ID
        spoiler_settings.pop(message.id, None)

app.run()
