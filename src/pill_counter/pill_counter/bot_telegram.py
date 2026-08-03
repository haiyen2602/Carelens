#!/usr/bin/python
"""
Telegram bot dem thuoc.

Cach chay:
    1. Dat token bot vao bien moi truong TELEGRAM_BOT_TOKEN,
       hoac tao file api_key.json:  {"api_key": "123456:ABC-..."}
    2. python app.py
"""

import json
import os
import sys
from io import BytesIO

import cv2
import numpy as np
import telebot

# get_prediction nam trong predict.py, model duoc load 1 lan luc import
from predict import get_prediction


def load_token():
    '''
    Lay token bot theo thu tu: bien moi truong -> api_key.json
    '''
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if token:
        return token.strip()

    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_key.json')
    if os.path.isfile(key_path):
        with open(key_path, 'r', encoding='utf-8') as f:
            token = json.load(f).get('api_key', '')
        if token and 'DAN_TOKEN' not in token:
            return token.strip()

    print(
        'Chua co token cua bot Telegram.\n'
        'Cach 1: set TELEGRAM_BOT_TOKEN=123456:ABC-...\n'
        'Cach 2: sua file api_key.json thanh {"api_key": "123456:ABC-..."}\n'
        'Token lay tu @BotFather tren Telegram.'
    )
    sys.exit(1)


API_TOKEN = load_token()

bot = telebot.TeleBot(API_TOKEN)


# Handle '/start' and '/help'
@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    bot.reply_to(message, """\
Hi there, I am Pills Counter bot.

I am here to help you with counting pills, \
just send me photo and I will send you another \
and then I will say how many tablets or capsules \
that picture has.\
""")


# Handle images
@bot.message_handler(content_types=['photo'])
def photo(message):
    # Get file ID of the photo sent by the user
    file_id = message.photo[-1].file_id

    # Download the photo file from Telegram servers
    file_info = bot.get_file(file_id)
    file = BytesIO(bot.download_file(file_info.file_path))

    # Load the image using OpenCV
    image = cv2.imdecode(np.frombuffer(file.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        bot.reply_to(message, "I couldn't read that image, please send another one.")
        return

    # Prediction
    predicted_image, count_dict = get_prediction(image)

    capsules = count_dict.get('capsules', 0)
    tablets = count_dict.get('tablets', 0)

    if capsules + tablets == 0:
        bot.reply_to(message, "I didn't find any pills on that picture.")
        return

    # Send a confirmation message
    message_to_send = (f"There are {capsules} capsules and {tablets} tablets. "
                       f"A total of {capsules + tablets} pills.")
    bot.reply_to(message, message_to_send)

    # Encode the filtered image as a JPEG and send it back to the user
    ret, buffer = cv2.imencode('.jpg', predicted_image)
    file = BytesIO(buffer)
    bot.send_photo(message.chat.id, file, caption="There is your predicted image.")


# Handle all other messages with content_type 'text' (content_types defaults to ['text'])
@bot.message_handler(func=lambda message: True)
def echo_message(message):
    message_to_send = "I'm just Pills Counter bot and i can't reply to your message. Send me pictures with pills, please."
    bot.reply_to(message, message_to_send)


if __name__ == '__main__':
    # Kiem tra token truoc, tranh infinity_polling lap vo han khi token sai
    try:
        me = bot.get_me()
    except telebot.apihelper.ApiTelegramException as e:
        print(f'Token khong hop le, Telegram tra ve: {e.description}')
        sys.exit(1)

    print(f'Bot @{me.username} dang chay, nhan Ctrl+C de dung.')
    bot.infinity_polling()
