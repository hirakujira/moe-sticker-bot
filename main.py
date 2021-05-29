import json
import time
import logging
from typing import Any
from urllib import parse
from urllib.parse import urlparse
import telegram.error
from telegram import Update, Bot, ReplyKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, CallbackContext, ConversationHandler, MessageHandler, Filters
from bs4 import BeautifulSoup
import emoji
import requests
import re
import os
import subprocess
import secrets
import traceback
import argparse
import shlex
from notifications import *
import shutil
import glob


class GlobalConfigs:
    BOT_NAME = ""
    BOT_TOKEN = ""
    BOT_VERSION = "2.0 ALPHA-4"

LINE_STICKER_INFO, EMOJI, TITLE, MANUAL_EMOJI = range(4)
GET_TG_STICKER = range(1)

reply_kb_for_auto_markup = ReplyKeyboardMarkup(
    [['auto']], one_time_keyboard=True)
reply_kb_for_manual_markup = ReplyKeyboardMarkup(
    [['manual']], one_time_keyboard=True)


def retry_do(func, is_fake_ra) -> Any:
    for index in range(3):
        try:
            func()
        except telegram.error.RetryAfter as ra:
            time.sleep(int(ra.retry_after))
            if is_fake_ra():
                break
            else:
                continue
        except Exception as e:
            # It could probably be a network problem, sleep for a while and try again.
            time.sleep(5)
            # Even if unknown exception occurred, keep retrying until threshold meet.
            if index == 2:
                return(str(e))
        else:
            break


def do_auto_import_line_sticker(update, ctx):
    print_import_starting(update, ctx)

    img_files_path = prepare_sticker_files(ctx, want_animated=False)
    # Create a new sticker set using the first image.
    try:
        ctx.bot.create_new_sticker_set(user_id=update.message.from_user.id,
                                       name=ctx.user_data['telegram_sticker_id'],
                                       title=ctx.user_data['telegram_sticker_title'],
                                       emojis=ctx.user_data['telegram_sticker_emoji'],
                                       png_sticker=open(img_files_path[0], 'rb'))
    except Exception as e:
        print_fatal_error(update, str(e))
        return

    message_progress = print_progress(
        None, 1, len(img_files_path), update=update)
    for index, img_file_path in enumerate(img_files_path):
        # Skip the first file.
        if index == 0:
            continue

        print_progress(message_progress, index + 1, len(img_files_path))
        # time.sleep(1)
        err = retry_do(lambda: ctx.bot.add_sticker_to_set(user_id=update.message.from_user.id,
                                                          name=ctx.user_data['telegram_sticker_id'],
                                                          emojis=ctx.user_data['telegram_sticker_emoji'],
                                                          png_sticker=open(img_file_path, 'rb')),
                       lambda: (
                           index + 1 == ctx.bot.get_sticker_set(name=ctx.user_data['telegram_sticker_id']).stickers),
                       ctx)
        if err is not None:
            print_fatal_error(update, str(err))
            return

    print_sticker_done(update, ctx)
    # clean up
    directory_path = os.path.dirname(img_files_path[0])
    shutil.rmtree(directory_path, ignore_errors=True)
    os.makedirs(directory_path, exist_ok=True)


def prepare_sticker_files(ctx, want_animated):
    # os.makedirs("line_sticker", exist_ok=True)
    dir_path = os.path.join("line_sticker", ctx.user_data['line_sticker_id'])
    shutil.rmtree(dir_path, ignore_errors=True)
    os.makedirs(dir_path, exist_ok=True)

    # subprocess.run(f"rm -r {directory_path}*", shell=True)
    if ctx.user_data['line_sticker_type'] == "sticker_message":
        for element in BeautifulSoup(ctx.user_data['line_store_webpage'].text, "html.parser").find_all('li'):
            json_text = element.get('data-preview')
            if json_text is not None:
                json_data = json.loads(json_text)
                base_image = json_data['staticUrl'].split(';')[0]
                overlay_image = json_data['customOverlayUrl'].split(';')[0]
                base_image_link_split = base_image.split('/')
                image_id = base_image_link_split[base_image_link_split.index(
                    'sticker') + 1]
                subprocess.run(
                    ["curl", "-Lo", f"{dir_path}{image_id}.base.png", base_image])
                subprocess.run(
                    ["curl", "-Lo", f"{dir_path}{image_id}.overlay.png", overlay_image])
                subprocess.run(["convert", f"{dir_path}{image_id}.base.png", f"{dir_path}{image_id}.overlay.png",
                               "-background", "none", "-filter", "Lanczos", "-resize", "512x512", "-composite", "-define", "webp:lossless=true",
                                f"{dir_path}{image_id}.webp"])
    else:
        zip_file_path = os.path.join(
            "line_sticker", ctx.user_data['line_sticker_id'] + ".zip")
        subprocess.run(["curl", "-Lo", zip_file_path,
                        ctx.user_data['line_sticker_download_url']])
        subprocess.run(["bsdtar", "-xf", zip_file_path, "-C", dir_path])
        if not want_animated:
            # Remove garbage
            for f in glob.glob(os.path.join(dir_path, "*key*")) + glob.glob(os.path.join(dir_path, "tab*")) + glob.glob(os.path.join(dir_path, "productInfo.meta")):
                os.remove(f)
            # Resize to fulfill telegram's requirement, AR is automatically retained
            # Lanczos resizing produces much sharper image.
            for f in glob.glob(os.path.join(dir_path, "*")):
                subprocess.run(["mogrify", "-background", "none", "-filter", "Lanczos", "-resize", "512x512",
                                "-format", "webp", "-define", "webp:lossless=true", f])
        else:
            dir_path = os.path.join(dir_path, "animation@2x")
            # Magic!
            # LINE's apng has fps of 9, however ffmpeg defaults to 25
            for f in glob.glob(os.path.join(dir_path, "*.png")):
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-i", f,
                                "-lavfi", 'color=white[c];[c][0]scale2ref[cs][0s];[cs][0s]overlay=shortest=1,setsar=1:1',
                                "-c:v", "libx264", "-r", "9", "-crf", "26", "-y", f + ".mp4"])
            return sorted([f for f in glob.glob(os.path.join(dir_path, "*.mp4"))])

    return sorted([f for f in glob.glob(os.path.join(dir_path, "*.webp"))])


def do_download_line_sticker(update, ctx):
    update.message.reply_text(ctx.user_data['line_sticker_download_url'])


def initialise_manual_import(update, ctx):
    print_import_starting(update, ctx)
    ctx.user_data['img_files_path'] = prepare_sticker_files(
        ctx, want_animated=False)
    # This is the FIRST sticker.
    ctx.user_data['manual_emoji_index'] = 0
    notify_next(update, ctx)


# MANUAL_EMOJI
def manual_add_emoji(update: Update, ctx: CallbackContext) -> int:
    # Verify emoji.
    em = ''.join(e for e in re.findall(
        emoji.get_emoji_regexp(), update.message.text))
    if em == '':
        update.message.reply_text("Please send emoji! Try again")
        return MANUAL_EMOJI

    # First sticker to create new set.
    if ctx.user_data['manual_emoji_index'] == 0:
        try:
            ctx.bot.create_new_sticker_set(user_id=update.message.from_user.id,
                                           name=ctx.user_data['telegram_sticker_id'],
                                           title=ctx.user_data['telegram_sticker_title'],
                                           emojis=em,
                                           png_sticker=open(ctx.user_data['img_files_path'][0], 'rb'))
        except Exception as e:
            update.message.reply_text(
                "Error creating sticker set! Please try again!\n" + str(e))
            return ConversationHandler.END
    else:
        # try:
        err = retry_do(lambda: ctx.bot.add_sticker_to_set(user_id=update.message.from_user.id,
                                                          name=ctx.user_data['telegram_sticker_id'],
                                                          emojis=em,
                                                          png_sticker=open(
                                                              ctx.user_data['img_files_path'][ctx.user_data['manual_emoji_index']], 'rb'
                                                          )),
                       lambda: (ctx.user_data['manual_emoji_index'] + 1 == ctx.bot.get_sticker_set(
                           name=ctx.user_data['telegram_sticker_id']).stickers),
                       ctx
                       )
        if err is not None:
            print_fatal_error(update, str(err))
            return ConversationHandler.END
            # update.message.reply_text(
            #     "Error assigning this one! Please send the same emoji again.\n" + err)

        if ctx.user_data['manual_emoji_index'] == len(ctx.user_data['img_files_path']) - 1:
            print_sticker_done(update, ctx)
            # clean up
            directory_path = os.path.dirname(
                ctx.user_data['img_files_path'][0])
            shutil.rmtree(directory_path, ignore_errors=True)
            os.makedirs(directory_path, exist_ok=True)

            return ConversationHandler.END

    ctx.user_data['manual_emoji_index'] += 1
    notify_next(update, ctx)
    return MANUAL_EMOJI


def notify_next(update, ctx):
    retry_do(lambda: ctx.bot.send_photo(chat_id=update.effective_chat.id,
                                        caption="Please send emoji(s) representing this sticker\n"
                                        "請傳送代表這個貼圖的emoji(可以多個)\n"
                                        "このスタンプにふさわしい絵文字を入力してください(複数可)\n" +
                                        f"{ctx.user_data['manual_emoji_index'] + 1} of {len(ctx.user_data['img_files_path'])}",
                                        photo=open(ctx.user_data['img_files_path'][ctx.user_data['manual_emoji_index']], 'rb')),
             lambda: False, ctx)


# TITLE
# This is the final conversaion step, if user wants to assign each sticker a different emoji, return to MANUAL_EMOJI,
# otherwise, do auto import then END conversation.
def parse_title(update: Update, ctx: CallbackContext) -> int:
    # Manual ID assignation is now removed, it seems meaningless.
    # Auto ID generation.
    ctx.user_data['telegram_sticker_id'] = f"line_{ctx.user_data['line_sticker_type']}_" \
        f"{ctx.user_data['line_sticker_id']}_" \
        f"{secrets.token_hex(nbytes=3)}_by_{GlobalConfigs.BOT_NAME}"

    if update.message.text.strip().lower() != "auto":
        ctx.user_data['telegram_sticker_title'] = update.message.text.strip()

    if ctx.user_data['manual_emoji'] is True:
        initialise_manual_import(update, ctx)
        return MANUAL_EMOJI
    else:
        do_auto_import_line_sticker(update, ctx)
        return ConversationHandler.END


# EMOJI
def parse_emoji(update: Update, ctx: CallbackContext) -> int:
    if update.message.text.strip().lower() == "manual":
        ctx.user_data['manual_emoji'] = True
    else:
        em = ''.join(e for e in re.findall(
            emoji.get_emoji_regexp(), update.message.text))
        if em == '':
            update.message.reply_text("Please send emoji! Try again")
            return EMOJI
        ctx.user_data['telegram_sticker_emoji'] = em

    ctx.user_data['telegram_sticker_title'] = BeautifulSoup(ctx.user_data['line_store_webpage'].text, 'html.parser')\
        .find("title").get_text().split('|')[0].strip().split('LINE')[0][:-3] + \
        f" @{GlobalConfigs.BOT_NAME}"
    update.message.reply_text(
        "Please set a title for this sticker set. Send <code>auto</code> to automatically set original title from LINE Store as shown below:\n"
        "請設定貼圖包的標題, 也就是名字. 傳送<code>auto</code>可以自動設為LINE Store中原版的標題如下:\n"
        "スタンプのタイトルを入力してください。<code>auto</code>を入力すると、LINE STORE上に表記されているのタイトルが自動的以下の通りに設定されます。" + "\n\n" +
        "<code>" + ctx.user_data['telegram_sticker_title'] + "</code>",
        reply_markup=reply_kb_for_auto_markup,
        parse_mode="HTML")
    return TITLE


# LINE_STICKER_INFO
def parse_line_url(update: Update, ctx: CallbackContext) -> int:
    try:
        message_url = re.findall(r'\b(?:https?):[\w/#~:.?+=&%@!\-.:?\\-]+?(?=[.:?\-]*(?:[^\w/#~:.?+=&%@!\-.:?\-]|$))',
                                 update.message.text)[0]
        ctx.user_data['line_store_webpage'] = requests.get(message_url)
        ctx.user_data['line_sticker_url'], \
            ctx.user_data['line_sticker_type'], \
            ctx.user_data['line_sticker_id'], \
            ctx.user_data['line_sticker_download_url'] = get_line_sticker_detail(
                ctx.user_data['line_store_webpage'])
    except Exception as e:
        update.message.reply_text('URL parse error! Make sure you sent a correct LINE Store URL! Try again please.\n'
                                  'URL解析錯誤! 請確認傳送的是正確的LINE商店URL連結. 請重試.\n'
                                  'URL解析エラー！もう一度、正しいLINEスタンプストアのリンクを入力してください\n\n' + str(e))
        return LINE_STICKER_INFO
    if str(ctx.user_data['in_command']).startswith("/import_line_sticker"):
        print_ask_emoji(update)
        return EMOJI
    elif str(ctx.user_data['in_command']).startswith("/download_line_sticker"):
        do_download_line_sticker(update, ctx)
        return ConversationHandler.END
    elif str(ctx.user_data['in_command']).startswith("/get_animated_line_sticker"):
        do_get_animated_line_sticker(update, ctx)
        return ConversationHandler.END
    else:
        pass


def get_line_sticker_detail(webpage):
    if not webpage.url.startswith("https://store.line.me"):
        raise Exception("Not a LINE Store link! 不是LINE商店之連結!")
    json_details = json.loads(BeautifulSoup(
        webpage.text, "html.parser").find_all('script')[0].contents[0])
    i = json_details['sku']
    url = json_details['url']
    url_comps = urlparse(url).path[1:].split('/')
    if url_comps[0] == "stickershop":
        # First one matches AnimatedSticker with NO sound and second one with sound.
        if 'MdIcoPlay_b' in webpage.text or 'MdIcoAni_b' in webpage.text:
            t = "sticker_animated"
            u = "https://stickershop.line-scdn.net/stickershop/v1/product/" + \
                i + "/iphone/stickerpack@2x.zip"
        elif 'MdIcoMessageSticker_b' in webpage.text:
            t = "sticker_message"
            u = webpage.url
        else:
            t = "sticker"
            u = "https://stickershop.line-scdn.net/stickershop/v1/product/" + \
                i + "/iphone/stickers@2x.zip"
    elif url_comps[0] == "emojishop":
        t = "emoji"
        u = "https://stickershop.line-scdn.net/sticonshop/v1/sticon/" + \
            i + "/iphone/package.zip"
    else:
        raise Exception("Not a supported sticker type!\nLink is: " + url)

    return url, t, i, u


def do_get_animated_line_sticker(update, ctx):
    if ctx.user_data['line_sticker_type'] != "sticker_animated":
        update.message.reply_text("Sorry! This LINE Sticker set is NOT animated! Please check again.\n"
                                  "抱歉! 這個LINE貼圖包沒有動態版本! 請檢查連結是否有誤.\n"
                                  "このスタンプの動くバージョンはございません。もう一度ご確認してください。")
        return ConversationHandler.END
    print_import_starting(update, ctx)
    for gif_file in prepare_sticker_files(ctx, want_animated=True):
        retry_do(lambda: ctx.bot.send_animation(
            chat_id=update.effective_chat.id, animation=open(gif_file, 'rb')),
            lambda: False,
            ctx)
    update.message.reply_text(
        ctx.user_data['in_command'] + " done! 指令成功完成!")


def command_import_line_sticker(update: Update, ctx: CallbackContext):
    initialize_user_data(update, ctx)
    print_ask_line_store_link(update)
    return LINE_STICKER_INFO


def command_download_line_sticker(update: Update, ctx: CallbackContext):
    initialize_user_data(update, ctx)
    print_ask_line_store_link(update)
    return LINE_STICKER_INFO


def command_get_animated_line_sticker(update: Update, ctx: CallbackContext):
    initialize_user_data(update, ctx)
    print_ask_line_store_link(update)
    return LINE_STICKER_INFO


def initialize_user_data(update, ctx):
    ctx.user_data['in_command'] = update.message.text
    ctx.user_data['manual_emoji'] = False
    ctx.user_data['line_sticker_url'] = ""
    ctx.user_data['line_store_webpage'] = None
    ctx.user_data['line_sticker_download_url'] = ""
    ctx.user_data['line_sticker_type'] = "sticker"
    ctx.user_data['line_sticker_id'] = ""
    ctx.user_data['telegram_sticker_emoji'] = ""
    ctx.user_data['telegram_sticker_id'] = ""
    ctx.user_data['telegram_sticker_title'] = ""


def command_alsi(update: Update, ctx: CallbackContext) -> int:
    if update.message.text.startswith("alsi"):
        alsi_parser = argparse.ArgumentParser(prog="alsi", exit_on_error=False, add_help=False,
                                              formatter_class=argparse.RawTextHelpFormatter,
                                              description="Advanced Line Sticker Import - command line tool to import LINE sticker.\n進階LINE貼圖匯入程式",
                                              epilog='Example usage:\n'
                                              '  alsi -id=example_id_1 -title="Example Title" -link=https://store.line.me/stickershop/product/8898\n\n'
                                              'Note:\n  Argument containing white space must be closed by quotes.\n'
                                              '  ID must contain alphabet, number and underscore only.')
        alsi_parser.add_argument(
            '-emoji', help="Emoji to assign to whole sticker set, ignore this option to assign manually\n指定給整個貼圖包的Emoji, 忽略這個選項來手動指定貼圖的emoji", required=False)
        alsi_parser.add_argument(
            '-id', help="Telegram sticker name(ID), used for share link\nTelegram貼圖包ID, 用於分享連結", required=True)
        alsi_parser.add_argument(
            '-title', help="Telegram sticker set title\nTelegram貼圖包的標題", required=True)
        alsi_parser.add_argument(
            '-link', help="LINE Store link of LINE sticker pack\nLINE商店貼圖包連結", required=True)
        try:
            alsi_args = alsi_parser.parse_args(
                shlex.split(update.message.text)[1:])
        except:
            update.message.reply_text(
                "Wrong syntax!!\n" + "<code>" + alsi_parser.format_help() + "</code>", parse_mode="HTML")
            return ConversationHandler.END
        # initialise
        ctx.user_data['in_command'] = "alsi"
        ctx.user_data['manual_emoji'] = True
        ctx.user_data['line_sticker_url'] = alsi_args.link
        ctx.user_data['line_store_webpage'] = None
        ctx.user_data['line_sticker_download_url'] = ""
        ctx.user_data['line_sticker_type'] = "sticker"
        ctx.user_data['line_sticker_id'] = ""
        # parse link
        try:
            ctx.user_data['line_store_webpage'] = requests.get(alsi_args.link)
            ctx.user_data['line_sticker_url'], \
                ctx.user_data['line_sticker_type'], \
                ctx.user_data['line_sticker_id'], \
                ctx.user_data['line_sticker_download_url'] = get_line_sticker_detail(
                    ctx.user_data['line_store_webpage'])
        except:
            update.message.reply_text("Wrong link!!")
            return ConversationHandler.END
        # add id and title
        if not re.match('^\w+$', alsi_args.id):
            update.message.reply_text("Wrong ID!!")
            return ConversationHandler.END
        ctx.user_data['telegram_sticker_id'] = alsi_args.id + \
            "_by_" + GlobalConfigs.BOT_NAME
        ctx.user_data['telegram_sticker_title'] = alsi_args.title

        if alsi_args.emoji is None:
            initialise_manual_import(update, ctx)
            return MANUAL_EMOJI
        else:
            ctx.user_data['telegram_sticker_emoji'] = alsi_args.emoji
            do_auto_import_line_sticker(update, ctx)
            return ConversationHandler.END

    else:
        update.message.reply_text("wrong command!")
        return ConversationHandler.END


# GET_TG_STICKER
def parse_tg_sticker(update: Update, ctx: CallbackContext) -> int:
    sticker_set = ctx.bot.get_sticker_set(name=update.message.sticker.set_name)
    update.message.reply_text("This might take some time, please wait...\n"
                              "此項作業可能需時較長, 請稍等...\n"""
                              "少々お待ちください...\n"
                              "<code>\n"
                              f"Name: {sticker_set.name}\n"
                              f"Title: {sticker_set.title}\n"
                              f"Amount: {str(len(sticker_set.stickers))}\n"
                              "</code>",
                              parse_mode="HTML")
    dir_path = os.path.join("tg_sticker", sticker_set.name)
    shutil.rmtree(dir_path, ignore_errors=True)
    os.makedirs(dir_path, exist_ok=True)
    for index, sticker in enumerate(sticker_set.stickers):
        try:
            ctx.bot.get_file(sticker.file_id).download(dir_path + sticker.set_name +
                                                       "_" + str(index).zfill(3) + "_" +
                                                       emoji.demojize(sticker.emoji)[1:-1] +
                                                       (".tgs" if sticker_set.is_animated else ".webp"))
        except Exception as e:
            print_fatal_error(update, str(e))
            return ConversationHandler.END
    webp_zip = os.path.join(dir_path, sticker_set.name + "_webp.zip")
    tgs_zip = os.path.join(dir_path, sticker_set.name + "_tgs.zip")
    png_zip = os.path.join(dir_path, sticker_set.name + "_png.zip")

    subprocess.run(["bsdtar", "-acvf", webp_zip,
                   os.path.join(dir_path, "*.webp")])

    if sticker_set.is_animated:
        for f in glob.glob(os.path.join(dir_path, "*.tgs")):
            subprocess.run(["lottie_convert.py", f, f + ".webp"])
        subprocess.run(["bsdtar", "-acvf", tgs_zip,
                       os.path.join(dir_path, "*.tgs")])
    else:
        for f in glob.glob(os.path.join(dir_path, "*.webp")):
            subprocess.run(["mogrify", "-format", "png", f])
        subprocess.run(["bsdtar", "-acvf", png_zip,
                       os.path.join(dir_path, "*.png")])

    try:
        ctx.bot.send_document(chat_id=update.effective_chat.id,
                              document=open(webp_zip, 'rb'))
        if sticker_set.is_animated:
            ctx.bot.send_document(chat_id=update.effective_chat.id,
                                  document=open(tgs_zip, 'rb'))
        else:
            ctx.bot.send_document(chat_id=update.effective_chat.id,
                                  document=open(png_zip, 'rb'))
    except Exception as e:
        print_fatal_error(update, str(e))

    # clean up
    shutil.rmtree(dir_path, ignore_errors=True)
    os.makedirs(dir_path, exist_ok=True)

    return ConversationHandler.END


def command_download_telegram_sticker(update: Update, ctx: CallbackContext):
    initialize_user_data(update, ctx)
    update.message.reply_text("Please send a sticker.\n"
                              "請傳送一張Telegram貼圖.\n"
                              "ステッカーを一つ送信してください。")
    return GET_TG_STICKER


def print_ask_emoji(update):
    update.message.reply_text("Please enter emoji representing this sticker set\n"
                              "請傳送用於表示整個貼圖包的emoji\n"
                              "このスタンプセットにふさわしい絵文字を入力してください\n"
                              "eg. ☕ \n\n"
                              "If you want to manually assign different emoji for each sticker, send <code>manual</code>\n"
                              "如果您想要為貼圖包內每個貼圖設定不同的emoji, 請傳送<code>manual</code>\n"
                              "一つずつ絵文字を付けたいなら、<code>manual</code>を送信してください。",
                              reply_markup=reply_kb_for_manual_markup,
                              parse_mode="HTML")


def command_cancel(update: Update, ctx: CallbackContext) -> int:
    update.message.reply_text("SESSION END.")
    start(update, ctx)
    return ConversationHandler.END


def handle_text_message(update: Update, ctx: CallbackContext):
    print_use_start_command(update)
    if update.message.text.startswith("https://store.line.me") or update.message.text.startswith("https://line.me"):
        print_suggest_import(update)


def handel_sticker_message(update: Update, ctx: CallbackContext):
    print_use_start_command(update)
    print_suggest_download(update)


def print_warning(update: Update, ctx: CallbackContext):
    update.message.reply_text("You are already in command : " + ctx.user_data['in_command'][1:] + "\n"
                              "If you encountered a problem, please send /cancel and start over.")


def main() -> None:
    GlobalConfigs.BOT_TOKEN = os.getenv("BOT_TOKEN")
    GlobalConfigs.BOT_NAME = Bot(GlobalConfigs.BOT_TOKEN).get_me().username
    updater = Updater(GlobalConfigs.BOT_TOKEN)

    dispatcher = updater.dispatcher

    conv_advanced_import = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex(
            '^alsi*') & ~Filters.command, command_alsi)],
        states={
            MANUAL_EMOJI: [MessageHandler(Filters.text & ~Filters.command, manual_add_emoji)],
        },
        fallbacks=[CommandHandler('cancel', command_cancel), MessageHandler(
            Filters.command, print_warning)],
        run_async=True
    )

    # Each conversation is time consuming, enable run_async
    conv_import_line_sticker = ConversationHandler(
        entry_points=[CommandHandler(
            'import_line_sticker', command_import_line_sticker)],
        states={
            LINE_STICKER_INFO: [MessageHandler(Filters.text & ~Filters.command, parse_line_url)],
            EMOJI: [MessageHandler(Filters.text & ~Filters.command, parse_emoji)],
            TITLE: [MessageHandler(Filters.text & ~Filters.command, parse_title)],
            MANUAL_EMOJI: [MessageHandler(Filters.text & ~Filters.command, manual_add_emoji)],
        },
        fallbacks=[CommandHandler('cancel', command_cancel), MessageHandler(
            Filters.command, print_warning)],
        run_async=True
    )
    conv_get_animated_line_sticker = ConversationHandler(
        entry_points=[CommandHandler(
            'get_animated_line_sticker', command_get_animated_line_sticker)],
        states={
            LINE_STICKER_INFO: [MessageHandler(Filters.text & ~Filters.command, parse_line_url)],
        },
        fallbacks=[CommandHandler('cancel', command_cancel), MessageHandler(
            Filters.command, print_warning)],
        run_async=True
    )
    conv_download_line_sticker = ConversationHandler(
        entry_points=[CommandHandler(
            'download_line_sticker', command_download_line_sticker)],
        states={
            LINE_STICKER_INFO: [MessageHandler(Filters.text & ~Filters.command, parse_line_url)],
            EMOJI: [MessageHandler(Filters.text & ~Filters.command, parse_emoji)],
        },
        fallbacks=[CommandHandler('cancel', command_cancel), MessageHandler(
            Filters.command, print_warning)],
        run_async=True
    )
    conv_download_telegram_sticker = ConversationHandler(
        entry_points=[CommandHandler(
            'download_telegram_sticker', command_download_telegram_sticker)],
        states={
            GET_TG_STICKER: [MessageHandler(Filters.sticker, parse_tg_sticker)],
        },
        fallbacks=[CommandHandler('cancel', command_cancel), MessageHandler(
            Filters.command, print_warning)],
        run_async=True
    )
    # 派遣します！
    dispatcher.add_handler(conv_import_line_sticker)
    dispatcher.add_handler(conv_get_animated_line_sticker)
    dispatcher.add_handler(conv_download_line_sticker)
    dispatcher.add_handler(conv_download_telegram_sticker)
    dispatcher.add_handler(conv_advanced_import)
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('help', command_help))
    dispatcher.add_handler(CommandHandler('faq', command_faq))
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command, handle_text_message))
    dispatcher.add_handler(MessageHandler(
        Filters.sticker, handel_sticker_message))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
