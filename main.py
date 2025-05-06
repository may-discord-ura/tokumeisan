import asyncio  #botメッセージ自動削除待機用
import datetime
import html
import io  # メッセージを削除する際に添付ファイルを取得するため　
import json
import os
import random
import re
import string
import time
import urllib.parse  #日本語URLデコード用
from collections import defaultdict, deque
from datetime import timedelta

import aiohttp  # メッセージを削除する際に添付ファイルを取得するため
import discord
import requests  #天気予報用
from bs4 import BeautifulSoup  #カタログ読み込み関連
from discord import app_commands
from discord.abc import GuildChannel, PrivateChannel
from discord.ext import commands, tasks
from discord.ui import Button, Modal, TextInput, View  #モーダル関連

# インテントの生成
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# botの定義
bot = commands.Bot(intents=intents, command_prefix="$", max_messages=10000)
tree = bot.tree

# コマンドの実行タイミングを記録する連中（連投制限用）
last_executed = {}
last_executed['temp'] = 0
temp_time_before = 0

# 設定ファイルのパス
CONFIG_FILE = 'configs/config.json'
CHANNEL_LIST = "configs/channels.json"
ANONYM_LIST = 'configs/anolist.json'
AUTODELETE_LIST = 'configs/autodelete.json'
KEYWORD_LIST = 'configs/keywords.json'
IMAGE_LIST = 'configs/imagelist.json'
NEWCHANNEL_LIST = 'configs/newchannel.json'
ID_LIST = 'configs/ids.json'
CREATED_THREAD_LIST = 'configs/created_threads.json'

# メッセージの記録を保存する辞書
message_log = defaultdict(lambda: deque([0] * 7, maxlen=7))
start_message_time = datetime.datetime.now()
THRESHOLD = 30
TIME_WINDOW_MINUTES = 1
LOCK_DURATION = timedelta(minutes=3)
beforeslot = 0
nextslot = 0

# 関数初期化（ここでやらないと起動時にエラーが出たりする）
command_count = 0
day_count = 0
is_enabled_threadstop = False
is_enabled_react = False
is_enabled_futaba = False
is_enabled_channelspeed = False
is_enabled_onmessage_bot = False
is_enabled_onmessage_temp = False
is_enabled_msgdellog = False
is_enabled_anochange = False
is_enabled_earthquake= False
PREDEFINED_NAME = "としあき"


# タイムアウト処理が既に行われたメッセージIDのセット
processed_messages = set()
processed_messages_special = set()



### --------関数定義ゾーン---------
# 設定を読み込む
def load_config(file):
    with open(file, 'r') as f:
        return json.load(f)


# 設定を書き込む
def save_config(config, file):
    with open(file, 'w') as f:
        json.dump(config, f, indent=4,ensure_ascii=False)



# id生成用の関数
def get_random_string(length: int) -> str:
    random_source = string.ascii_letters + string.digits
    random_string = ''.join(
        (random.choice(random_source) for i in range(length)))
    return random_string


# idをjsonに格納・読み出しする関数
def reload_ids(user_id):
    global member_data
    with open(ID_LIST, "r", encoding="utf-8") as json_file:
        member_data = json.load(json_file)
    check_date()
    if str(user_id) not in member_data:
        new_data = {
            "tid":
            get_random_string(8),
            "color":
            random.choice((0x66cdaa, 0x7cfc00, 0xffd700, 0xc0c0c0,
                           0xba55d3))  #水色、緑、橙、灰、紫
        }
        member_data[user_id] = new_data
    # jsonを書き込んで読み込み直す
    with open(ID_LIST, "w", encoding="utf-8") as json_file:
        json.dump(member_data, json_file, ensure_ascii=False, indent=4)
    with open(ID_LIST, "r", encoding="utf-8") as json_file:
        member_data = json.load(json_file)


def check_date():
    global member_data
    global day_count
    day_now = datetime.date.today().day
    if day_now != day_count:
        day_count = day_now
        config["day_count"] = day_count
        save_config(config, CONFIG_FILE)
        member_data = {}


#ano本体
async def ano_post(本文: str,user_id: int,id表示: bool,添付ファイル: discord.Attachment = None,interaction: discord.Interaction = None,resmode: bool = False,message:discord.Message =None,channelid:int =None,attachment_file:discord.File =None,attachment_file_log:discord.File =None):
    #連投制限
    current_time = time.time()
    if user_id in last_executed and current_time - last_executed[user_id] < 15 and interaction:
        await interaction.response.send_message(
            content=f"連続で実行できません。ちょっと（5秒くらい）待ってね。書き込もうとした内容→　{本文}",
            ephemeral=True)
        return

    #ID生成
    reload_ids(user_id)

    # 通し番号を更新してファイルに保存
    global command_count
    command_count += 1
    config["command_count"] = command_count
    save_config(config, CONFIG_FILE)

    ###本番送信部分###
    # ID表示チェック
    if id表示:
        emb_id = "ID:" + member_data[str(user_id)]["tid"]
    else:
        emb_id = ""

    # 添付ファイルをFile形式に変更
    if 添付ファイル:
        attachment_file = await 添付ファイル.to_file()
        attachment_file_log = await 添付ファイル.to_file()

    # 半角スペースx2を改行に変換
    本文 = 本文.replace("  ", "\n")

    # 埋め込みを作成
    ano_embed = discord.Embed(
        title='',
        description=f"{本文}\n ",  #0624
        color=member_data[str(user_id)]["color"]  # 色を指定 (青色)0x3498db
    )

    # 埋め込みに情報を追加
    if resmode is True:
        ano_embed.set_footer(text=f'とくめいさん#{str(command_count)} 返信版')
    else:
        ano_embed.set_footer(text=f'とくめいさん#{str(command_count)} {emb_id}')

    # 実行ユーザー宛に成功メッセージを送信
    if interaction:
        await interaction.response.send_message(ephemeral=True,content="書き込み成功！このメッセージは自動で消えます",delete_after=3)

    # 添付ファイルが画像の場合、埋め込み内に画像を表示
    url_without_query =""
    if attachment_file:
        url_without_query = re.sub(r'\?.*$', '', attachment_file.filename.lower())
        if url_without_query.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            ano_embed.set_image(url=f"attachment://{attachment_file.filename}")
        else:
            ano_embed.add_field(name="添付ファイル", value=attachment_file.filename, inline=False)

    # コマンドを実行したチャンネルにメッセージを送信
    if channelid:
        message_channel = bot.get_channel(channelid)
    else:
        message_channel = interaction.channel

    if resmode is True: # 返信版
        message = await message.reply(embed=ano_embed)
    elif attachment_file:
        message = await message_channel.send(embed=ano_embed, file=attachment_file)
    else: # 添付ファイルのない通常投稿
        message = await message_channel.send(embed=ano_embed)

    # 開示用のリスト生成
    global anonyms
    anonyms[message.id] = [command_count, user_id]
    save_config(anonyms, ANONYM_LIST)

    ###ログ送信部分###
    # コマンドを実行したチャンネルorスレッドを取得
    # 自動変換の場合とそうでない場合
    try:
        thread_id = interaction.channel_id
        thread_name = interaction.channel.name
        username = interaction.user.name
    except Exception:
        thread_id = channelid
        thread_name = message_channel.name
        username = bot.get_user(user_id)

    # ログ保存用チャンネルにメッセージを送信
    log_channel = bot.get_channel(LOG_CHANNEL_ID[0])
    if log_channel:
        log_message = (
            f"**名前:** {username}<@{user_id}>\n"  #0624
            f"**チャンネル:**{thread_name}<#{thread_id}>\n"
            f"**内容:** {本文}"  #0624
            f"　[jump]({message.jump_url})"  #0624
        )
        log_embed = discord.Embed(
            title='Anonymous実行ログ#' + str(command_count),
            description=log_message,
            color=0x3498db  # 色を指定 (青色)
        )

        #添付ファイルの有無で分岐
        if attachment_file_log:
            url_without_query = re.sub(r'\?.*$', '', attachment_file_log.filename.lower())
            if url_without_query.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                log_embed.set_image(url=f"attachment://{attachment_file_log.filename}")
            else:
                log_embed.add_field(name="添付ファイル", value=attachment_file_log.filename, inline=False)

        if attachment_file_log:
            await log_channel.send(embed=log_embed, file=attachment_file_log)
        else:
            await log_channel.send(embed=log_embed)

    else:
        print(f"チャンネルID {LOG_CHANNEL_ID[0]} が見つかりませんでした")

    # コマンドの実行タイミングを記録
    last_executed[user_id] = current_time

# autodeleteで削除したメッセージをテキストに書き出す
def log_deleted_messages(channel_name, messages):
    date_str = datetime.datetime.now(server_timezone).strftime("%Y-%m-%d")
    log_file = f"autodelete_log/{channel_name}[{date_str}].txt"

    # 既存のログファイルを読み込む
    existing_logs = []
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            existing_logs = f.readlines()

    # 新しいログエントリを追加
    new_logs = []
    for message in messages:
        # 通常メッセージまたはembedのdescriptionをログに保存
        content = message.content.replace('\n', ' \\n ')
        if message.embeds:
            for embed in message.embeds:
                if embed.description:
                    content = embed.description.replace('\n', ' \\n ')
        content = content.replace(',', '，`')
        if content == "":
            content = "本文なし"
        posted_time = message.created_at.astimezone(server_timezone).strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{posted_time},{message.author.id},{message.author.name},{content}\n"
        new_logs.append(log_entry)

    # 既存のログと新しいログを統合してソート
    all_logs = existing_logs + new_logs
    all_logs.sort()  # timestampが最初に来るので、文字列としてソートすれば時系列順になる

    # ログファイルに書き込む
    os.makedirs("autodelete_log", exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(all_logs)



### -----on_readyゾーン------
# discordと接続した時に呼ばれる
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}.")
    await tree.sync()
    print("Synced slash commands.")
    await bot.change_presence(activity=discord.Activity(name="/help | 二次裏", type=discord.ActivityType.watching))


    """設定をファイルから読み込む"""
    global command_count
    global day_count
    global config
    global PREDEFINED_NAME
    global TARGET_CHANNEL_ID,AUTODELETE_CHANNEL_ID, LOG_CHANNEL_ID, SPEED_CHANNEL_ID, FORUM_ALERT_CHANNEL_ID, BOTCOMMAND_ALERT_CHANNEL_ID,DELETE_LOG_CHANNEL_ID
    global BOT_AUTODELETE_ID, ANO_CHANGE_CHANNEL_ID, EARTHQUAKE_CHANNEL_ID, CREATED_ALERT_CHANNEL_ID
    global server_timezone
    global is_enabled_threadstop, is_enabled_react, is_enabled_futaba
    global is_enabled_channelspeed, is_enabled_msgdellog #ログ関係
    global is_enabled_onmessage_bot, is_enabled_onmessage_temp
    global is_enabled_anochange, is_enabled_earthquake
    global last_eq_id
    global anonyms
    global keyword_list
    global autodelete_config
    command_count = 0  # コマンド実行回数をカウントするための変数

    if os.path.exists(CONFIG_FILE):
        # 初期設定の読み込み
        config = load_config(CONFIG_FILE)
    else:
        config = {}    
    if config.get('server_timezone', "UTC") == "JST":# タイムゾーンを定義
        JST = datetime.timezone(timedelta(hours=+9), 'JST')
        server_timezone = JST
    else:
        UTC = datetime.timezone(timedelta(hours=+0), 'UTC')
        server_timezone = UTC
    command_count = config.get('command_count', 0)
    day_count = config.get('day_count', 0)
    is_enabled_threadstop = config.get('is_enabled_threadstop', False)
    is_enabled_react = config.get('is_enabled_react', False)
    is_enabled_futaba = config.get('is_enabled_futaba', False)
    is_enabled_channelspeed = config.get('is_enabled_channelspeed', False)
    is_enabled_onmessage_bot = config.get('is_enabled_onmessage_bot',False)
    is_enabled_onmessage_temp = config.get('is_enabled_onmessage_temp',False)
    is_enabled_msgdellog = config.get('is_enabled_msgdellog', False)
    is_enabled_anochange = config.get('is_enabled_anochange', False)
    is_enabled_earthquake= config.get('is_enabled_earthquake', False)
    PREDEFINED_NAME = config.get('PREDEFINED_NAME', "としあき")
    last_eq_id = config.get('last_eq_id', "0")


    if os.path.exists(CHANNEL_LIST):
        channels = load_config(CHANNEL_LIST)
    else:
        channels = {}
    TARGET_CHANNEL_ID = channels.get('スレッド監視対象チャンネル', [])
    AUTODELETE_CHANNEL_ID = channels.get('スレッド自動削除対象チャンネル', {})
    LOG_CHANNEL_ID = channels.get('ログ保存先チャンネル', [])
    SPEED_CHANNEL_ID = channels.get('速度監視対象チャンネル', [])
    FORUM_ALERT_CHANNEL_ID = channels.get('フォーラム新着通知チャンネル', [])
    BOTCOMMAND_ALERT_CHANNEL_ID = channels.get('BOT発言抑制対象外チャンネル', [])
    BOT_AUTODELETE_ID = channels.get('BOT発言抑制対象BOTID', [])
    DELETE_LOG_CHANNEL_ID = channels.get('削除ログ保存先チャンネル', [])
    ANO_CHANGE_CHANNEL_ID = channels.get('匿名変換対象チャンネル', [])
    EARTHQUAKE_CHANNEL_ID = channels.get('地震速報通知チャンネル', [])
    CREATED_ALERT_CHANNEL_ID = channels.get('VC作成時通知サーバー・チャンネル', {})

    if os.path.exists(AUTODELETE_LIST):
        autodelete_config = load_config(AUTODELETE_LIST)
    else:
        autodelete_config = {}
        save_config(autodelete_config, AUTODELETE_LIST)

    # 匿名投稿の開示用リスト読み込み
    if os.path.exists(ANONYM_LIST):
        anonyms = load_config(ANONYM_LIST)
    else:
        anonyms = {}
        save_config(anonyms, ANONYM_LIST)

    # 二次裏スレッド監視用単語リスト読み込み
    if os.path.exists(KEYWORD_LIST):
        keyword_list = load_config(KEYWORD_LIST)
    else:
        keyword_list = {}
        save_config(keyword_list, KEYWORD_LIST)

    # ループ起動
    fetch_weather.start()
    delete_old_messages.start()
    check_threads_2nd.start()
    fetch_data.start()   
    fetch_earthquake.start()

# ヘルプコマンド
class HelpPaginator(discord.ui.View):
    def __init__(self, pages: list):
        super().__init__(timeout=None)
        self.pages = pages
        self.current_page = 0

        # 初回のページ更新
        self.update_buttons()

    def update_buttons(self):
        # ページに応じたボタンの有効/無効を設定
        self.first_page.disabled = self.current_page == 0
        self.previous_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.pages) - 1
        self.last_page.disabled = self.current_page == len(self.pages) - 1

    @discord.ui.button(label="<<", style=discord.ButtonStyle.primary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.pages) - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

@tree.command(name="help", description="botの機能や使い方を表示するよ")
@app_commands.choices(コマンドor機能名=[
    app_commands.Choice(name="/ano", value="ano"),
    app_commands.Choice(name="/dice", value="dice"),
    app_commands.Choice(name="/here", value="here"),
    app_commands.Choice(name="/id出ろ", value="id出ろ"),
    app_commands.Choice(name="/oyasumi", value="oyasumi"),
    app_commands.Choice(name="/ohayo", value="ohayo"),
    app_commands.Choice(name="/temp", value="temp"),
    app_commands.Choice(name="/timemachine", value="timemachine"),
    app_commands.Choice(name="/スレ立て", value="スレ立て"),
    app_commands.Choice(name="/スレ管理", value="スレ管理"),
    app_commands.Choice(name="/時報", value="時報"),
    app_commands.Choice(name="/大空寺カウンター", value="大空寺カウンター"),
    app_commands.Choice(name="/二次裏監視ワード", value="二次裏監視ワード"),
    app_commands.Choice(name="📙あとで読む", value="あとで読む"),
    app_commands.Choice(name="📙おっぱい", value="おっぱい"),
    app_commands.Choice(name="📙とくめいさんにレスさせる", value="とくめいさんにレスさせる"),
    app_commands.Choice(name="📙名前を奪う", value="名前を奪う"),
    app_commands.Choice(name="👀人気のレス機能", value="人気のレス機能"),
    app_commands.Choice(name="👀自動匿名変換機能", value="自動匿名変換機能"),
    app_commands.Choice(name="👀新規スレッド通知機能", value="新規スレッド通知機能"),
    app_commands.Choice(name="👀おっぱい通知機能", value="おっぱい通知機能"),
    app_commands.Choice(name="👀レス自動削除機能", value="レス自動削除機能"),
    app_commands.Choice(name="👀スレッド自動削除機能", value="スレッド自動削除機能")
])
async def help(interaction: discord.Interaction,コマンドor機能名:str =""):
    if コマンドor機能名 =="":
        embed1 = discord.Embed(title="ヘルプ 1/3",
              description="思いつくままにどうでもいい機能を詰め込んだbotです\n各コマンドの詳細は「__/help コマンドor機能名__」で確認してね",
              color=discord.Color.blue())
        embed1.add_field(name="スラッシュコマンド一覧（概要）",
                       value="",
                       inline=False)
        embed1.add_field(name="/ano",
                       value="匿名レスできます",inline=True)
        embed1.add_field(name="/dice",
                       value="簡単なダイス機能です",inline=True)
        embed1.add_field(name="/here",
                       value="チャンネルIDとかを表示します",inline=True)
        embed1.add_field(name="/id出ろ",
                       value="ランダムな8桁の英数文字列を表示します",inline=True)
        embed1.add_field(name="/oyasumi",
                       value="指定した時間、発言禁止になります",inline=True)
        embed1.add_field(name="/ohayo",
                       value="ランダムで画像を表示します",inline=True)
        embed1.add_field(name="/temp",
                       value="今日の気温や天気みたいなのを表示します",inline=True)
        embed1.add_field(name="/timemachine",
                       value="レスをさかのぼるボタンを表示します",inline=True)
        embed1.add_field(name="/スレ立て",
                       value="スレッドを作成します",inline=True)
        embed1.add_field(name="/スレ管理",
                       value="作成したスレッドの設定を変更します",inline=True)
        embed1.add_field(name="/時報",
                       value="現在時刻を細かく表示します",inline=True)
        embed1.add_field(name="/大空寺カウンター",
                       value="__**1文字だけのレス**__を集計します",inline=True)
        embed1.add_field(name="/二次裏監視ワード",
                       value="二次裏のスレ監視ワードを設定します",inline=True)

        embed2 = discord.Embed(title="ヘルプ 2/3",
              description="思いつくままにどうでもいい機能を詰め込んだbotです\n各コマンドの詳細は「__/help コマンドor機能名__」で確認してね",
              color=discord.Color.blue())
        embed2.add_field(name="コンテキストメニュー一覧（概要）",
                       value="",
                       inline=False)
        embed2.add_field(name="📙あとで読む",
                       value="メッセージを指定してあとで読めるようにします",inline=True)
        embed2.add_field(name="📙おっぱい",
                       value="メッセージにおっぱいリアクションを追加します",inline=True)
        embed2.add_field(name="📙とくめいさんにレスさせる",
                       value="/ano機能で返信を行います",inline=True)
        embed2.add_field(name="📙名前を奪う",
                       value="贅沢な名だね",inline=True)
        embed2.add_field(name="その他の機能（概要）",
                       value="",
                       inline=False)

        embed3 = discord.Embed(title="ヘルプ 3/3",
              description="思いつくままにどうでもいい機能を詰め込んだbotです\n各コマンドの詳細は「__/help コマンドor機能名__」で確認してね",
              color=discord.Color.blue())
        embed3.add_field(name="👀人気のレス",
                       value="リアクションが溜まるとチャンネル内で通知します",inline=True)
        embed3.add_field(name="👀自動匿名変換",
                       value="一部チャンネルのレスを匿名発言に変換します",inline=True)
        embed3.add_field(name="👀新規スレッド通知",
                       value="フォーラム等にスレッドが立つと通知します",inline=True)
        embed3.add_field(name="👀おっぱい通知",
                       value="おっぱい",inline=True)
        embed3.add_field(name="👀レス自動削除",
                       value="一定時間経過したレスを削除します",inline=True)
        embed3.add_field(name="👀スレッド自動削除",
                       value="一定時間経過したスレッドを削除します",inline=True)
        pages =[embed1,embed2,embed3]
        view = HelpPaginator(pages)
        await interaction.response.send_message(embed=pages[0], view=view,ephemeral=True)
        return

    elif コマンドor機能名 =="ano":
        embed_title ="/ano（スラッシュコマンド）"
        embed_value ="名前を隠してメッセージを送信するコマンドです。発言に返信されても通知が来ないので注意\n"
        embed_value+="- __オプション__\n"
        embed_value+=" - 本文：メッセージの本文を入力（半角スペース2連続で改行になります）\n"
        embed_value+=" - id表示：Trueにするとidが出ます（毎日0時更新）\n"
        embed_value+=" - 添付ファイル：ファイルを添付する時に指定してね\n"
        embed_value+="※オプションを全部省略すると本文入力用の画面が出ます\n"
        embed_value+="※添付ファイルを指定して本文を省略するとｷﾀｰAA略になります"
        embed_value+="※添付ファイルは一回の投稿で一つまでです"
    elif コマンドor機能名 =="dice":
        embed_title ="/dice（スラッシュコマンド）"
        embed_value ="簡単なダイス機能です。1種類のダイスを複数個投げることができます\n"
        embed_value+="- __オプション__\n"
        embed_value+=" - dice：ダイスの個数Xと面数YをXdY形式で指定してください（例：4d6）（省略不可）\n"
        embed_value+="※結果は「それぞれのダイスの値」「合計値」で表示されます\n"
        embed_value+="※複数種類転がしたりはできないので専門的なのが必要であればsasaとかを使ってね"
    elif コマンドor機能名 =="here":
        embed_title ="/here（スラッシュコマンド）"
        embed_value ="チャンネルIDとかを表示できる動作テスト用のコマンドです\n"
        embed_value+="特に意味はありませんが、チャンネルIDは二次裏監視ワード機能とかで使えます"
    elif コマンドor機能名 =="id出ろ":
        embed_title ="/id出ろ（スラッシュコマンド）"
        embed_value ="ランダムな8桁の英数文字列を表示します\n"
        embed_value+="ユーザーIDに紐付いていて、毎日0時に更新されます\n"
        embed_value+="※`/ano`で出せるIDと同じものです"
    elif コマンドor機能名 =="oyasumi":
        embed_title ="/oyasumi（スラッシュコマンド）"
        embed_value ="指定した時間、__**自分を**__発言禁止（タイムアウト状態）にします\n"
        embed_value+="時間が経過するか、ほかのユーザーが起こすボタンを押すと解除されます\n"
        embed_value+="- __オプション__\n"
        embed_value+=" - minutes：タイムアウトにする時間を分単位で指定します（省略不可）\n"
        embed_value+=" - 起こさないで：Trueにするとほかのユーザーに起こされなくなります"
    elif コマンドor機能名 =="ohayo":
        embed_title ="/ohayo（スラッシュコマンド）"
        embed_value ="ランダムで画像を表示します"
    elif コマンドor機能名 =="temp":
        embed_title ="/temp（スラッシュコマンド）"
        embed_value ="今日の気温や天気みたいなのを表示します\n"
        embed_value+="表示してほしい地域があれば管理者まで"
    elif コマンドor機能名 =="timemachine":
        embed_title ="/timemachine（スラッシュコマンド）"
        embed_value ="一定期間前のレスにさかのぼるボタンを表示します\n"
        embed_value+="最大で1000レス前、1週間前、最初のレスに戻れます\n"
        embed_value+="表示したボタンは他のユーザーも使うことができます"
    elif コマンドor機能名 =="スレ立て":
        embed_title ="/スレ立て（スラッシュコマンド）"
        embed_value ="指定したフォーラムチャンネルにスレッドを作成します\n"
        embed_value ="コマンド実行後に「タイトル」「本文」「管理キー」を入力する画面が表示されます\n"
        embed_value+="botが作成したことになるので「スレ主」表示が出ません\n"
        embed_value+="- __オプション__\n"
        embed_value+=" - __画像__：添付画像を１枚だけ指定できます\n"
        embed_value+=" - __ロックまでの時間__：スレッド作成後、この時間が経過すると自動で書き込み禁止になります（単位は分です）\n"
        embed_value+=" - __削除までの時間__：書き込み禁止になってから、この時間が経過すると自動でスレッドを削除します（単位は分です）\n"
        embed_value+="※スレッド作詞後に`/スレ管理`コマンドで設定変更可能です"
    elif コマンドor機能名 =="スレ管理":
        embed_title ="/スレ管理（スラッシュコマンド）"
        embed_value ="'/スレ立て'コマンドで作成したスレッド内で使うと設定変更ができます\n"
        embed_value+="- __オプション__\n"
        embed_value+="　- __管理キー__：スレ立て時に設定した管理キーを入力します（必須）\n"
        embed_value+="　- __内容__：設定する内容を選びます。ロック・削除時間の変更やタイトル変更、手動でのロック・削除が可能です"
    elif コマンドor機能名 =="時報":
        embed_title ="/時報（スラッシュコマンド）"
        embed_value ="現在時刻をマイクロ秒単位で表示します\n"
        embed_value+="- __オプション__\n"
        embed_value+=" - 本文：時報と一緒に送信するメッセージを入れることができます\n"
        embed_value+=" - 添付ファイル：ファイルを添付する場合に指定する\n"
        embed_value+=" - 難易度を下げる：Trueにすると秒単位の表示になります"
    elif コマンドor機能名 =="大空寺カウンター":
        embed_title ="/大空寺カウンター（スラッシュコマンド）"
        embed_value ="指定したレス数内の、__**1文字だけのレス**__を集計して表示します\n"
        embed_value+="- __オプション__\n"
        embed_value+=" - レス数：1文字だけのレスを探すレス数（最新のレスから）を指定します（デフォルト値は100）\n"
        embed_value+=" - 公開する：自分だけにするとほかのユーザーに表示されません（デフォルト値は「公開する」）"
    elif コマンドor機能名 =="二次裏監視ワード":
        embed_title ="/二次裏監視ワード（スラッシュコマンド）"
        embed_value ="二次裏mayとimgのスレ本文を監視して各チャンネルに通知する設定を行います。\n"
        embed_value+="数分おきにカタログを勢順（せいじゅん）でチェックし、見つかったら指定のチャンネルに通知します。\n"
        embed_value+="- __オプション__\n"
        embed_value+=" - 監視ワード：監視ワードを指定します。スレ本文の先頭から12文字以内にあると反応します\n"
        embed_value+=" - 送信先チャンネルid：スレが見つかった場合の通知先を__**IDで**__指定します（スレッドも指定できます）\n"
        embed_value+="※`監視ワード`を省略すると__現在の設定を表示__します\n"
        embed_value+="※`監視ワード`は大文字小文字を区別しません（登録時はすべて小文字に変換されます）\n"
        embed_value+="※`送信先チャンネルid`を省略すると__現在のチャンネル（スレッド）で__設定や表示を行います\n"
        embed_value+="※チャンネルIDを調べる際はdiscordの__開発者モードをオン__にするか`/here`コマンドを使ってください"
    elif コマンドor機能名 =="あとで読む":
        embed_title ="📙あとで読む（コンテキストメニュー）"
        embed_value ="- 指定先：メッセージ\n"
        embed_value+=" - メッセージを指定してあとで読めるようにします（botがDMで内容を転送してきます）\n"
        embed_value+="※bot自体をブロックしていたりDMを受信しない設定にしていると届きません\n"
        embed_value+="※DM内で再度このコマンドを使うとメッセージが消えます"
    elif コマンドor機能名 =="おっぱい":
        embed_title ="📙おっぱい（コンテキストメニュー）"
        embed_value ="- 指定先：メッセージ\n"
        embed_value+=" - botがメッセージにおっぱいリアクションを追加します\n"
        embed_value+="※おっぱいリアクションを付けたいけど絵文字が探せないときにどうぞ"
    elif コマンドor機能名 =="とくめいさんにレスさせる":
        embed_title ="📙とくめいさんにレスさせる（コンテキストメニュー）"
        embed_value ="- 指定先：メッセージ\n"
        embed_value+=" - 指定したレスに対して、`/ano`機能で返信を行います\n"
        embed_value+="※/anoと同様、この発言に返信されても通知が来ません"
    elif コマンドor機能名 =="名前を奪う":
        embed_title ="📙名前を奪う（コンテキストメニュー）"
        embed_value ="- 指定先：ユーザー\n"
        embed_value+=" - 贅沢な名だね、今からお前の名は**としあき**だよ"
    elif コマンドor機能名 =="人気のレス機能":
        embed_title ="👀人気のレス機能（機能）"
        embed_value ="特定のリアクション絵文字が一定数溜まると、元メッセージがチャンネル内で通知されます\n"
        embed_value+="これを利用して、「人気のツイート」でdiscord内を検索することでリアクションの多いレスだけを抽出できます"
    elif コマンドor機能名 =="自動匿名変換機能":
        embed_title ="👀自動匿名変換（機能）"
        embed_value ="特定のチャンネルでメッセージが送信されると、自動で名前を隠して（`/ano`状態で）再送信します\n"
        embed_value+="現在、覆面座談会スレがこの機能の対象です"
        embed_value+="※複数ファイルを添付した場合、__最初のファイルのみ__が添付されます（2番目以降のファイルは消えます）"
    elif コマンドor機能名 =="新規スレッド通知機能":
        embed_title ="👀新規スレッド通知（機能）"
        embed_value ="フォーラム等にスレッドが立つと、特定のスレにおっと新スレ発見伝を行います\n"
        embed_value+="現在、雑談スレがこの機能の通知先になっています"
        embed_value+="設定は`/二次裏監視ワード`で編集できます"
    elif コマンドor機能名 =="おっぱい通知機能":
        embed_title ="👀おっぱい通知（機能）"
        embed_value ="おっぱいリアクションが一定数溜まると、おっぱいロールにメンションが飛びます\n"
        embed_value+="おっぱいロールは「チャンネル＆ロール」から各自で付与することができます"
    elif コマンドor機能名 =="レス自動削除機能":
        embed_title ="👀レス自動削除（機能）"
        embed_value ="特定のチャンネルで送信されたメッセージが一定時間経過後に自動で消えます\n"
        embed_value+="コマンドでの設定機能は未実装です。設定希望は管理人までどうぞ"
    elif コマンドor機能名 =="スレッド自動削除機能":
        embed_title ="👀スレッド自動削除（機能）"
        embed_value ="特定のフォーラムで作成されたスレッドが一定時間経過後に自動で消えます\n"
        embed_value+="コマンドでの設定機能は未実装です。設定希望は管理人までどうぞ"
    else:
        await interaction.response.send_message("なんか変",ephemeral=True)
        return

    embed = discord.Embed(title=embed_title,
          description=embed_value,
          color=discord.Color.blue())
    await interaction.response.send_message(embed=embed,ephemeral=True)

# コマンド実行場所のチャンネルIDとかを取得するコマンド（テスト用）
@tree.command(name="here", description="実行されたサーバーのID、チャンネル、スレッドの情報を取得します")
async def here(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    channel_id = interaction.channel_id
    thread_id = interaction.channel_id if isinstance(interaction.channel,
                                                     discord.Thread) else None
    if thread_id:
        response = f"ここは\nサーバーID: {guild_id}（{interaction.guild.name}）\n"
        response += f"スレッドID: {thread_id}（{interaction.channel.name}）\nです"
    else:
        response = f"ここは\nサーバーID: {guild_id}（{interaction.guild.name}）\n"
        response += f"チャンネルID: {channel_id}（{interaction.channel.name}）\nです"

    guilds = bot.guilds
    response += f"botを利用しているサーバー: {guilds}）\nです"
    await interaction.response.send_message(ephemeral=True,content=response)


# ダイス機能
@tree.command(name="dice", description="ダイスを振ります（簡易版）")
@app_commands.describe(dice="ダイスの個数Xと面数YをXdYの形式で入力（例：1d6）")
async def dice(interaction: discord.Interaction, dice: str):
    user_id = interaction.user.id
    current_time = time.time()

    # 最後の実行から5秒未満の場合、エラーメッセージを送信
    if user_id in last_executed and current_time - last_executed[user_id] < 5:
        await interaction.response.send_message(
            content=f"連続で実行できません。しばらく待ってから再度お試しください。実行内容→{dice}",
            ephemeral=True,
        )
        return

    # 処理開始
    match = re.match(r'(\d+)d(\d+)', dice)
    if not match:
        await interaction.response.send_message("コマンドの形式が正しくありません。例: /dice 2d6"
                                                )
        return

    num_dice = int(match.group(1))
    num_sides = int(match.group(2))

    if num_dice <= 0 or num_sides <= 0 or num_dice >= 1000 or num_sides >= 1000000:
        await interaction.response.send_message(
            "ダイスの数は1以上1000未満、面の数は1以上1000000未満にしてください。")
        return

    rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
    total = sum(rolls)

    result = ' '.join(f"{roll}" for roll in rolls)

    dice_messsage = f"**:dash::game_die: dice{num_dice}d{num_sides} の結果: {result} __( {total} )__**"
    dice_embed = discord.Embed(
        title='',
        description=dice_messsage,
        color=0x3498db  # 色を指定 (青色)
    )

    await interaction.response.send_message(embed=dice_embed)

    # コマンドの実行タイミングを記録
    last_executed[user_id] = current_time


# 時報できる
@tree.command(name="時報", description="現在時刻を表示します")
@app_commands.describe(本文="レス本文を入れる（省略可）",
                       添付ファイル="省略可",
                       難易度を下げる="Trueにするとマイクロ秒を表示しません")
async def jihou(interaction: discord.Interaction,
                本文: str = "",
                添付ファイル: discord.Attachment = None,
                難易度を下げる: bool = False):

    global day_count
    user_id = interaction.user.id
    reload_ids(user_id)
    current_time = time.time()

    # 最後の実行から5秒未満の場合、エラーメッセージを送信
    if user_id in last_executed and current_time - last_executed[user_id] < 60:
        await interaction.response.send_message(
            content="コマンドは連続で実行できません。ちょっと（1分くらい）待ってね。", ephemeral=True)
        return

    now = datetime.datetime.now(server_timezone)

    # 英語の曜日を漢字1文字に変換する辞書
    weekday_kanji = {
        'Mon': '月',
        'Tue': '火',
        'Wed': '水',
        'Thu': '木',
        'Fri': '金',
        'Sat': '土',
        'Sun': '日'
    }

    # 曜日を取得し、漢字に変換
    weekday_str = now.strftime('%a')
    weekday_kanji_str = weekday_kanji[weekday_str]

    if 本文 == "":
        本文 = "### ｷﾀ━━━━━(ﾟ∀ﾟ)━━━━━!!"

    if 難易度を下げる is True:
        microseconds = ""
    else:
        microseconds = now.strftime("%f")

    # 埋め込みを作成
    now_embed = discord.Embed(
        title=now.strftime(
            f'%Y/%m/%d（{weekday_kanji_str}）　%H:%M:%S.{microseconds}'),
        description=f"{本文}",
        color=member_data[str(user_id)]["color"]  # 色を指定 (青色)0x3498db
    )

    # 埋め込みに情報を追加
    now_embed.set_footer(text='とくめいさん＠時報')

    # コマンドを実行したチャンネルにメッセージを送信
    if 添付ファイル:
        file = await 添付ファイル.to_file()
        now_embed.set_image(url=f"attachment://{file.filename}")
        await interaction.response.send_message(embed=now_embed, file=file)
    else:
        await interaction.response.send_message(embed=now_embed)

    # コマンドの実行タイミングを記録
    last_executed[user_id] = current_time


# ID出ろ
@tree.command(name="id出ろ", description="ユーザーに紐づいたIDを表示します。ＩＤは0時更新")
async def id_dero(interaction: discord.Interaction):
    global day_count
    user_id = interaction.user.id
    reload_ids(user_id)
    id_embed = discord.Embed(
        title='',
        description=
        f"### {interaction.user.display_name}の今日のＩＤは __**{member_data[str(user_id)]['tid']}**__ です",
        color=member_data[str(user_id)]["color"]  # 色を指定 (青色)0x3498db
    )
    await interaction.response.send_message(embed=id_embed)


# 指定したレスをさかのぼるタイムマシーン
async def get_message_after(channel, after_time):
    # 指定された時間よりも後のメッセージを取得
    async for message in channel.history(limit=1, after=after_time):
        return message
    return None


# 指定したレスをさかのぼるタイムマシーン
@tree.command(name="timemachine", description="レスをさかのぼるボタンを表示します")
async def timemachine(interaction: discord.Interaction):

    if interaction.guild is None:
        await interaction.response.send_message("DM内では使えないよ",ephemeral=True)
        return

    user_id = interaction.user.id
    current_time = time.time()

    # 最後の実行から5秒未満の場合、エラーメッセージを送信
    if user_id in last_executed and current_time - last_executed[user_id] < 60:
        await interaction.response.send_message(
            content="連続で実行できません。ちょっと（1分くらい）待ってね。", ephemeral=True)
        return

    # 現在の日時を取得
    now = datetime.datetime.now(datetime.timezone.utc)
    await interaction.response.defer(thinking=True)
    channel = interaction.channel if isinstance(
        interaction.channel, discord.Thread) else interaction.channel
    # 各タイムスタンプを計算
    time_frames = {
        '100レス前': None,
        '1000レス前': None,
        '12時間前': now - datetime.timedelta(hours=12),
        '24時間前': now - datetime.timedelta(hours=24),
        '1週間前': now - datetime.timedelta(hours=168),
        '一番上': channel.created_at
    }

    # チャンネルのメッセージ履歴を取得
    messages = []
    async for message in channel.history(limit=1000):
        messages.append(message)

    # 100個前と1000個前のメッセージを取得
    if len(messages) >= 100:
        time_frames['100レス前'] = messages[99].jump_url
    if len(messages) >= 1000:
        time_frames['1000レス前'] = messages[999].jump_url
    # 時間前のメッセージを検索
    for label, target_time in list(time_frames.items())[2:6]:
        extra_message = await get_message_after(channel, target_time)
        if extra_message:
            time_frames[label] = extra_message.jump_url

    # ViewとButtonを作成
    view = View()
    for label, url in time_frames.items():
        if url:
            button = Button(label=label, url=url)
            view.add_item(button)

    await interaction.followup.send(
        "[タイムマシーン](<https://www.youtube.com/watch?v=zosBzv-Lj-k>)へようこそ！",
        view=view)
    # コマンドの実行タイミングを記録
    last_executed[user_id] = current_time


#その場でBOTに発言させる匿名発言用コマンド
@tree.command(name="ano", description="発言したチャンネル内にメッセージ内容を発言します。ファイル添付・ID表示可")
@app_commands.describe(本文="送信するメッセージ内容。半角スペースを2連続で入力すると改行に変わります",添付ファイル="省略可",id表示="TRUEにするとランダムな英数字8文字が出る（0時更新）")
async def ano(interaction: discord.Interaction,本文: str = "",id表示: bool = False,添付ファイル: discord.Attachment = None):

    if interaction.guild is None:
        await interaction.response.send_message("DM内では使えないよ",ephemeral=True)
        return

    ###事前チェック部分###
    #本文と添付ファイルがどっちもない場合はモーダルを表示
    if 本文 == "":
        if 添付ファイル is None:
            await interaction.response.send_modal(
                ReplyModal(channel=interaction.channel))
            return
        else:
            本文 = "ｷﾀ━━━━━(ﾟ∀ﾟ)━━━━━!!"

    user_id = interaction.user.id
    await ano_post(本文, user_id, id表示, 添付ファイル, interaction, False)


#匿名レス機能の本体
#モーダル内にはテキストフィールドしか置けないみたいなのでファイル添付もIDも出せない…
class ReplyModal(Modal):

    def __init__(self, message=None, channel=None):
        if message:
            title = "とくめいさんに返信してもらう"
            label = "返信レス本文"
            desc = "ここに返信レス内容を入力する（ファイル添付やID出ろはできません）"
            self.resmode = True
            self.message = message
        else:
            title = "とくめいさんに発言してもらう"
            label = "レス本文"
            desc = "ここにレス本文を入力する（ファイル添付やID出ろはできません）"
            self.resmode = False
            self.message = None
            self.channel = channel
        super().__init__(title=title)
        self.add_item(
            TextInput(label=label,
                      placeholder=desc,
                      style=discord.TextStyle.paragraph,
                      required=True))

    async def on_submit(self, interaction: discord.Interaction):
        reply_content = self.children[0].value
        ###事前チェック部分###
        #本文がない場合はエラー
        if reply_content is None:
            await interaction.response.send_message(content="！エラー！本文を入力してね",
                                                    ephemeral=True)
            return

        user_id = interaction.user.id
        await ano_post(reply_content, user_id, False, None, interaction,self.resmode, self.message)


# 自分をタイムアウトする
class TimeoutView(discord.ui.View):

    def __init__(self, member):
        super().__init__(timeout=None)
        self.member = member

    @discord.ui.button(label="→起こす←", style=discord.ButtonStyle.red)
    async def untimeout_button(self, interaction: discord.Interaction,
                               button: discord.ui.Button):
        async with asyncio.Lock():
            try:
                await self.member.timeout(None)
                await interaction.response.send_message(
                    f"{interaction.user.mention}の力で{self.member.mention}が目覚めました",
                    delete_after=60,
                    silent=True)
                await interaction.message.delete()  # メッセージを削除
            except Exception:
                return


# 自分をタイムアウトする
@tree.command(name="oyasumi", description="一定時間レスできなくなります")
@app_commands.describe(minutes="タイムアウトする時間を分単位の整数で入力する(1-721)",
                       起こさないで="Trueにすると起こすボタンが他人に表示されなくなります（要注意）")
async def oyasumi(interaction: discord.Interaction,
                  minutes: int,
                  起こさないで: bool = None):
    if os.path.exists(IMAGE_LIST):
        image_url_list = load_config(IMAGE_LIST)
        oyasumi_image_list = image_url_list["oyasumi"]
    else:
        oyasumi_image_list = {}
    image_url = random.choice(oyasumi_image_list)

    if interaction.guild is None:
        await interaction.response.send_message("DM内では使えないよ",ephemeral=True)
        return

    if minutes < 1 or minutes > 721:
        await interaction.response.send_message("常識的な数字を入れてやりなおしてね",ephemeral=True)
        return

    member = interaction.user
    timeout_duration = discord.utils.utcnow() + timedelta(minutes=minutes)

    try:
        await member.timeout(timeout_duration)
        if 起こさないで:
            await interaction.response.send_message(
                f"__**:sheep:【夢のおわり EX】**__\n{member.mention}をVCから切断＆{minutes}分後まで**永久睡眠**を付与する<耐性無効/解除不能/生贄選択不能/オーダーチェンジ不能>",
                embed=discord.Embed().set_image(url=image_url),
                silent=True
            )
            #await interaction.response.send_message(
            #    f"__**:sheep:【夢のおわり EX】**__\n{member.mention}をVCから切断＆{minutes}分後まで**永久睡眠**を付与する<耐性無効/解除不能/生贄選択不能/オーダーチェンジ不能>",
            #    silent=True,
            #    file=discord.File("https://media.discordapp.net/attachments/1287779758138069074/1288893216116052050/IMG_3381.jpg")
            #)
        else:
            await interaction.response.send_message(
                f":sheep:**{member.mention}は{minutes}分間寝ちゃうみたい**\n※起こす:chicken:ボタンを押すと途中でも解除されます",
                view=TimeoutView(member),
                embed=discord.Embed().set_image(url=image_url),
                silent=True
            )
            #oyasumi_embed = discord.Embed(
            #    title="",
            #    color=0x4678EE  # 色を指定 (青色)
            #)
            #oyasumi_embed.set_image(url=image_url)
            #await interaction.response.send_message(embed=oyasumi_embed,silent=True)

            #await interaction.response.send_message(
            #    f":sheep:**{member.mention}は{minutes}分間寝ちゃうみたい**\n※起こす:chicken:ボタンを押すと途中でも解除されます",
            #    silent=True,
            #    view=TimeoutView(member)
            #)
    except discord.Forbidden:
        await interaction.response.send_message("ユーザーをタイムアウトする権限がありません。",
                                                ephemeral=True)

# おはよう画像をランダム表示
@tree.command(name="ohayo", description="おはようございます")
async def ohayo(interaction: discord.Interaction):

    if os.path.exists(IMAGE_LIST):
        image_url_list = load_config(IMAGE_LIST)
        ohayo_image_list = image_url_list["ohayo"]
    else:
        ohayo_image_list = {}

    if ohayo_image_list != {}:
        image_url = random.choice(ohayo_image_list)
        ohayo_embed = discord.Embed(
            title="",
            color=0x4678EE  # 色を指定 (青色)
        )
        ohayo_embed.set_image(url=image_url)
        await interaction.response.send_message(embed=ohayo_embed)
    else:
        await interaction.response.send_message("エラー！表示する画像がないです。。。",ephemeral=True)


# 二次裏監視ワードの表示と追加
@tree.command(name="二次裏監視ワード", description="監視ワードを設定・表示します。設定されている内容と同じものを指定すると設定を削除します")
@app_commands.describe(監視ワード="監視ワードを設定します",送信先チャンネルid="通知するチャンネルまたはスレッドをIDで指定できます（省略するとこのチャンネル・スレッドを対象にします）")
async def add_futaba_word(interaction: discord.Interaction, 監視ワード: str = "", 送信先チャンネルid: str = ""):
    global keyword_list

    # 送信先チャンネルが空欄の場合は実行したチャンネルIDを設定する
    if 送信先チャンネルid == "":
        forward_channel_id = interaction.channel_id
    else:
        try:
            forward_channel_id = int(送信先チャンネルid)
        except Exception:
            await interaction.response.send_message('Error! 送信先チャンネルIDの指定が変',ephemeral=True)
            return

    # 送信先チャンネルが適正かチェック
    guild = interaction.guild
    guild_id = str(interaction.guild_id)
    parent_channel = ""
    channel_type = ""
    try:
        channel = guild.get_channel_or_thread(forward_channel_id)
        if channel:
            if isinstance(channel, discord.Thread):
                parent_channel = "@" + channel.parent.name
            else:
                channel_type = "Unknown"
                if isinstance(channel, discord.TextChannel):
                    channel_type = "チャンネル"
                elif isinstance(channel, discord.VoiceChannel):
                    channel_type = "ボイスチャンネル"
                else:
                    await interaction.response.send_message('Error! チャンネルが変',ephemeral=True)
                    return
        elif forward_channel_id == 114514:#全設定表示用のマジックワード
            pass
        else:
            await interaction.response.send_message(f'Error! 送信先チャンネル（ID：{送信先チャンネルid}）がないよ',ephemeral=True)
            return
    except ValueError:
        await interaction.response.send_message('Error! 送信先チャンネルIDの指定が変',ephemeral=True)
        return

    監視ワード = 監視ワード.lower() #監視ワードを小文字に変換
    # 監視ワードが適正かチェック 
    if 監視ワード == "":# 引数がない場合は現在の設定を表示
        if forward_channel_id == 114514:
            output_message = "**監視ワード : [通知先チャンネルID]**"
            for key, value in keyword_list.items():
                output_message = (f"{output_message}\n__{key}__ : {value}")
        else:
            output_message = "**このチャンネル（スレッド）で監視している単語は以下のとおりです。**\n"
            for key, value in keyword_list.items():
                for server_id, channel_id in value.items():
                    if forward_channel_id in channel_id:
                        output_message = (f"{output_message}__{key}__ , ")
        await interaction.response.send_message(f"{output_message}",ephemeral=True)
        return
    elif len(監視ワード) >= 12:
        await interaction.response.send_message("監視ワードが長すぎます。12文字以内にしてね",ephemeral=True)
        return
    elif len(監視ワード) < 2:
        await interaction.response.send_message("監視ワードが短すぎます。2文字以上にしてね",ephemeral=True)
        return

    # 監視ワードがすでに存在し、送信先チャンネルIDがリストに含まれている場合
    if 監視ワード in keyword_list:
        for key,value in keyword_list[監視ワード].items():
            if key == guild_id and forward_channel_id in value:
                keyword_list[監視ワード][key].remove(forward_channel_id)  # 送信先チャンネルIDを削除
                if keyword_list[監視ワード][key]: # 送信先チャンネルIDが残ってる場合はそのまま
                    await interaction.response.send_message(f"{監視ワード}の{channel.name}{channel_type}{parent_channel}への通知設定を__削除__しました",ephemeral=True)
                else: # リストが空になったら監視ワード自体を削除
                    del keyword_list[監視ワード][key]
                    await interaction.response.send_message(f"{監視ワード}の監視設定を__削除__しました",ephemeral=True)
                if not keyword_list[監視ワード]:
                    del keyword_list[監視ワード]
                return

    # 監視ワードが存在しないか、存在しても送信先チャンネルIDがリストに含まれていない場合
    if 監視ワード not in keyword_list:
        keyword_list[監視ワード] = {}
    if guild_id not in keyword_list[監視ワード]:
        keyword_list[監視ワード][guild_id] = []

    keyword_list[監視ワード][guild_id].append(forward_channel_id)  # 送信先チャンネルIDを追加
    await interaction.response.send_message(f"{監視ワード}の{channel.name}{channel_type}{parent_channel}への通知設定を__追加__しました",ephemeral=True)

    save_config(keyword_list, KEYWORD_LIST)


# アッツ島とサムイ島の気温を表示　20240626とりあえず完成
# OpenMeteoからjsonを取得してリストに直してjsonに保存してキャッシュ扱いにして一定時間内のリクエストはキャッシュを返す（リクエスト制限対策）
@tree.command(name="temp", description="今日の天気を表示")
async def temp(interaction: discord.Interaction):

    #ループ処理で取得した天気リストを使う
    global temp_list

    # ランダム天気
    lis = [
        "", f"\nなお、富山県富山市は現在{temp_list['toyama'][4]}ですが、回線速度への影響はありません",
        f"\n最高気温タイトルホルダー埼玉県熊谷市の現在の気温は{temp_list['kumagaya'][1]}度です",
        f"\nまた、長崎は{temp_list['nagasaki'][4]}でした",
        f"\nちなみに日本最北端、宗谷岬（北海道稚内市）の現在の気温は{temp_list['souya'][1]}度です",
        f"\n一方、キテレツ大百科で有名な静岡県浜松市は{temp_list['shizuoka'][4]}なう"
    ]

    # 埋め込み作成
    temp_title = f"本日({temp_list['attu'][0]})の天気をお知らせします"
    temp_message = (
        f"- 🥶__**サムイ島**__は現在{temp_list['samui'][4]}、気温は**{temp_list['samui'][1]}度**です\n"
        f" - 本日の体感気温は__最高**{temp_list['samui'][2]}度**__、__最低**{temp_list['samui'][3]}度**__です\n"
        f"- 🥵__**アッツ島**__は現在{temp_list['attu'][4]}、気温は**{temp_list['attu'][1]}度**です\n"
        f" - 本日の体感気温は__最高**{temp_list['attu'][2]}度**__、__最低**{temp_list['attu'][3]}度**__です"
        f"{random.choice(lis)}")
    temp_embed = discord.Embed(
        title=temp_title,
        description=temp_message,
        color=0x3498db  # 色を指定 (青色)
    )
    # 返信でメッセージを送信
    await interaction.response.send_message(embed=temp_embed)

# メッセージ一括削除（管理用）
@tree.command(name="メッセージ一括削除", description="指定された期間内のメッセージを一括削除します")
async def delete_messages(interaction: discord.Interaction,oldest_message_id: str, newest_message_id: str):
    channel = bot.get_channel(1247796615494766712)
    if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
        if not channel:
            await interaction.response.send_message("指定されたチャンネルが見つかりません。",ephemeral=True)
            return

        try:
            start_message = await channel.fetch_message(int(oldest_message_id))
            end_message = await channel.fetch_message(int(newest_message_id))
        except discord.NotFound:
            await interaction.response.send_message("指定されたメッセージIDが見つかりません。",ephemeral=True)
            return

        await interaction.response.defer(thinking=True,ephemeral=True)
        fourteen_days_ago = datetime.datetime.now(datetime.timezone.utc) - timedelta(days=14)
        messages_to_delete = []
        async for message in channel.history(limit=None,after=start_message.created_at, before=end_message.created_at):
            if not message.pinned:
                if message.created_at < fourteen_days_ago:
                    try:
                        await message.delete()
                        await asyncio.sleep(1)  # レートリミットを避けるための待機
                    except discord.Forbidden:
                        pass
                else:
                    messages_to_delete.append(message)
                    if len(messages_to_delete) >= 100:
                        await channel.delete_messages(messages_to_delete)
                        messages_to_delete = []
                        await asyncio.sleep(1)  # レートリミットを避けるための待機

        if messages_to_delete:
            await channel.delete_messages(messages_to_delete)

        await interaction.followup.send("指定された期間のメッセージを削除しました。",ephemeral=True)
    else:
        await interaction.response.send_message("チャンネルがテキストチャンネルじゃないみたい",ephemeral=True)

# メッセージ自動削除対象の登録
# チャンネル内のメッセージが多すぎると不具合が起きる可能性あり
@tree.command(name="レス自動削除設定", description="このチャンネルのレス自動削除設定をします")
@app_commands.describe(
    minutes="メッセージを削除するまでの時間（分単位）※0を指定すると自動削除しなくなり、省略すると現在の設定を表示します",
    ログ保存="削除したメッセージをテキストファイルに書き出すかどうかを設定します（デフォルト：False）"
)
async def auto_delete(interaction: discord.Interaction, minutes: int = -1, ログ保存:bool=False):
    target_id = str(interaction.channel_id)  # コマンドが実行されたチャンネルまたはスレッドのID
    global autodelete_config
    # 設定の表示、更新または削除
    if minutes == -1:
        if target_id in autodelete_config:
            current_minutes = autodelete_config[target_id]
            await interaction.response.send_message(
                f"このチャンネル（スレッド）では {current_minutes} 分後にメッセージが自動削除されます。",
                ephemeral=True
            )
            return
        else:
            await interaction.response.send_message(
                "このチャンネル（スレッド）では自動削除を行わない設定になっています。",
                ephemeral=True
            )
            return

    if interaction.user.guild_permissions.administrator:
        pass
    else:
        if isinstance(interaction.channel, discord.Thread) and interaction.channel.owner == interaction.user:
            print(interaction.channel.owner,interaction.user.id)
            pass
        else:
            #interaction.channel.type == discord.ChannelType.public_thread
            #isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel) or isinstance(channel, discord.ForumChannel):
            await interaction.response.send_message(
                "設定変更はスレッドのオーナーまたは管理者のみ可能です",
                ephemeral=True
            )
            return

    if minutes == 0:
        if target_id in autodelete_config:
            del autodelete_config[target_id]
            save_config(autodelete_config,AUTODELETE_LIST)
            await interaction.response.send_message(
                f"{interaction.channel.mention} の設定が削除されました。",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{interaction.channel.mention} には設定がありません。",
                ephemeral=True
            )
    elif minutes < 5 or minutes > 10080:
        await interaction.response.send_message("時間を5分～10080分の間で指定してください",ephemeral=True)
        return
    else:
        autodelete_config[target_id] = {'minutes': minutes,'ログ保存': ログ保存}
        save_config(autodelete_config,AUTODELETE_LIST)
        if ログ保存 is True:
            await interaction.response.send_message(
                f"{interaction.channel.mention} でメッセージを {minutes} 分後に削除するように設定しました。\nログはautodeleteフォルダに保存されます。",ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{interaction.channel.mention} でメッセージを {minutes} 分後に削除するように設定しました。\nログは保存しません。",
                ephemeral=True
            )

    await delete_old_messages()

@tree.command(name="ランダム画像", description="特定のチャンネルからランダムな画像を表示します")
async def show_random_image(interaction: discord.Interaction):
    try:
        # 指定されたチャンネルを取得
        channel = bot.get_channel(1355950021773758496)
        if not channel:
            await interaction.response.send_message("指定されたチャンネルが見つかりません。", ephemeral=True)
            return

        # メッセージ履歴から画像を収集
        image_urls = []
        async for message in channel.history(limit=100):
            for attachment in message.attachments:
                # URLのクエリパラメータを取り除く
                url_without_query = re.sub(r'\?.*$', '', attachment.url.lower())
                if url_without_query.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    image_urls.append(attachment.url)

        if not image_urls:
            await interaction.response.send_message("画像が見つかりませんでした。", ephemeral=True)
            return

        # ランダムに1つ選択
        selected_image = random.choice(image_urls)

        # 埋め込みメッセージを作成
        embed = discord.Embed(
            title="",
            description="",
            color=0x3498db
        )
        embed.set_image(url=selected_image)

        await interaction.response.send_message(embed=embed)

    except ValueError:
        await interaction.response.send_message("チャンネルIDの形式が正しくありません。", ephemeral=True)

@tree.command(name="ガンダム画像", description="特定のチャンネルからガンダムな画像を表示します")
async def show_gundam_image(interaction: discord.Interaction):
    try:
        # 指定されたチャンネルを取得
        channel = bot.get_channel(1358343495743574016)
        if not channel:
            await interaction.response.send_message("指定されたチャンネルが見つかりません。", ephemeral=True)
            return

        # メッセージ履歴から画像を収集
        image_urls = []
        async for message in channel.history(limit=100):
            for attachment in message.attachments:
                # URLのクエリパラメータを取り除く
                url_without_query = re.sub(r'\?.*$', '', attachment.url.lower())
                if url_without_query.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    image_urls.append(attachment.url)

        if not image_urls:
            await interaction.response.send_message("画像が見つかりませんでした。", ephemeral=True)
            return

        # ランダムに1つ選択
        selected_image = random.choice(image_urls)

        # 埋め込みメッセージを作成
        embed = discord.Embed(
            title="",
            description="",
            color=0x3498db
        )
        embed.set_image(url=selected_image)

        await interaction.response.send_message(embed=embed)

    except ValueError:
        await interaction.response.send_message("チャンネルIDの形式が正しくありません。", ephemeral=True)

# ごはん
@tree.command(name="ごはん", description="クックパッドのレシピをランダムで表示します")
async def show_recipe(interaction: discord.Interaction):
    await interaction.response.defer()

    for attempt in range(5):  # 最大5回まで試行
        recipe_id = random.randint(1000000, 9999999)  # 適当なレシピIDの範囲
        url = f"https://cookpad.com/recipe/{recipe_id}"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

        if response.status_code == 200:
            await interaction.followup.send(f"URL: {url}")
            return

    await interaction.followup.send("レシピを思いつきませんでした", ephemeral=True)

# 大空寺カウンター
@tree.command(name="大空寺カウンター", description="最近開催された大空寺チャレンジの結果を表示します")
@app_commands.describe(
    レス数="対象とするメッセージ数（デフォルトは100）",
    公開する="メッセージを全員に表示するか自分だけに表示するかを選択"
)
@app_commands.choices(公開する=[
    app_commands.Choice(name="公開する", value="public"),
    app_commands.Choice(name="自分だけ", value="private")
])
async def aokura_counter(interaction: discord.Interaction, レス数: int = 100, 公開する: str = "public"):

    channel = interaction.channel
    """
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("このコマンドはテキストチャンネルでのみ使用できます。", ephemeral=True)
        return
    """

    # メッセージ数の上限を設定（API制限に注意）
    max_messages = min(レス数, 500)  # 上限500メッセージに制限

    # デフェリングする際に、公開/非公開設定を考慮
    ephemeral = 公開する == "private"
    await interaction.response.defer(ephemeral=ephemeral)

    # 指定されたメッセージ数を取得
    messages = [msg async for msg in channel.history(limit=max_messages)]

    # 1文字だけのメッセージをフィルタリング
    one_char_messages = [msg for msg in messages if len(msg.content) == 1]

    if not one_char_messages:
        await interaction.followup.send("大空寺チャレンジは最近実施されていないようです", ephemeral=ephemeral)
        return

    # 古い順に並べ替え
    one_char_messages.sort(key=lambda msg: msg.created_at)

    # メッセージの内容を改行なしで組み立て
    message_content = "".join(msg.content for msg in one_char_messages)

    # 結果を送信
    await interaction.followup.send(f"__**直近{レス数}レス**__内の大空寺チャレンジ結果:\n**{message_content}**", ephemeral=ephemeral)



# スレ立て
@tree.command(name="スレ立て", description="指定したチャンネルでスレッドを作成します")
@app_commands.describe(
    親チャンネル="スレッドを作成するチャンネルを選択します",
    画像="スレ立て時に添付する画像を指定できます",
    ロックまでの時間="設定すると、指定時間（分）経過後に書き込みできなくなります（0-1440）",
    削除までの時間="設定すると、ロック後にここで指定した時間（分）経過後にスレッドを削除します（0-1440）"
)
async def make_thread(
    interaction: discord.Interaction,
    親チャンネル: discord.ForumChannel,
    画像: discord.Attachment = None,
    ロックまでの時間: int = 0,
    削除までの時間: int = 0
):
    # 入力チェック
    if not (0 <= ロックまでの時間 <= 1440) or not (0 <= 削除までの時間 <= 1440):
        await interaction.response.send_message("時間は0から1440までで",ephemeral=True)
        return
    parent_channel_id = str(親チャンネル.id)
    if parent_channel_id in AUTODELETE_CHANNEL_ID.keys(): # 自動削除対象のチャンネルで、入力が0/0だった場合は自動設定の内容を入れなおす
        if ロックまでの時間 == 0 and 削除までの時間 == 0:
            ロックまでの時間 = AUTODELETE_CHANNEL_ID[parent_channel_id][0]
            削除までの時間 = AUTODELETE_CHANNEL_ID[parent_channel_id][1]

    # モーダルの定義
    class ThreadModal(Modal):
        def __init__(self):
            super().__init__(title="スレッドを作成")

            # モーダルフィールドの設定
            self.add_item(TextInput(label="スレタイ", placeholder="スレッドのタイトルを入力（100文字まで・省略不可）",max_length=150, style=discord.TextStyle.short))
            self.add_item(TextInput(label="本文", placeholder="スレッドの本文を入力", style=discord.TextStyle.paragraph, required=False))
            self.add_item(TextInput(label="管理キー（変更したほうがいいよ）", placeholder="あとで使える管理用パスワードを入力（20文字まで）",max_length=20, style=discord.TextStyle.short, default="0721"))

        async def on_submit(self, interaction: discord.Interaction):
            # モーダル入力内容の取得
            title = self.children[0].value
            content = self.children[1].value
            password = self.children[2].value
            if ロックまでの時間 == 0:
                lock_time = 0
                lock_time_str = "0"
                delete_time = 削除までの時間
                delete_time_str = str(削除までの時間)
            elif 削除までの時間 == 0:
                lock_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=ロックまでの時間)
                lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                delete_time = 0
                delete_time_str = "0"
            else:
                lock_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=ロックまでの時間)
                lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                delete_time = lock_time + datetime.timedelta(minutes=削除までの時間)
                delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')

            # 入力チェック
            if not title:
                await interaction.response.send_message("スレッドのタイトルを入力してください",ephemeral=True)
                return
            if not content:
                content = "ｷﾀ━━━━(ﾟ∀ﾟ)━━━━!!"


            # ロック・削除までの時間を追記
            if lock_time != 0:
                content += f"\n`このスレッドは{lock_time_str}くらいに書き込めなくなります`"
            else:
                content += "\n`※このスレッドは落ちません`"
            if delete_time != 0 and lock_time != 0:
                content += f"\n`このスレッドは{delete_time_str}くらいに消えます`"
            elif delete_time == 0:
                content += "\n`※このスレッドは消えません…たぶんね`"
            else:
                content += f"\n`※このスレッドはまだ消えませんが、スレ落ち後{削除までの時間}分で消えます`"

            # スレッドの作成
            if 画像:
                thread = await 親チャンネル.create_thread(name=title, content=content,file=await 画像.to_file())
            else:
                thread = await 親チャンネル.create_thread(name=title, content=content)

            # スターターメッセージをピン留め
            await thread.message.pin()

            # JSONデータの保存
            data = load_config(CREATED_THREAD_LIST)
            data[thread.thread.id] = {
                "guild": thread.thread.guild.id,
                "lock_time": [ロックまでの時間,lock_time_str],
                "delete_time": [削除までの時間,delete_time_str],
                "password": password
            }
            save_config(data, CREATED_THREAD_LIST)
            await interaction.response.send_message(f"スレッド '{title}' が作成されました。\nリンク→{thread.thread.jump_url}",ephemeral=True)

    # モーダル表示
    await interaction.response.send_modal(ThreadModal())

# スレ管理
@tree.command(name="スレ管理", description="スレッドの管理をする")
@app_commands.describe(
    管理キー="スレッド作成時に設定した管理キーを入力します",
    内容="設定（変更）内容を選んでね"
)
@app_commands.choices(内容=[
    app_commands.Choice(name="スレッドタイトル変更", value="0"),
    app_commands.Choice(name="スレ落ち（自動ロック）時間再設定", value="1"),
    app_commands.Choice(name="スレ削除時間再設定", value="2"),
    app_commands.Choice(name="スレッドのロック（書き込み停止）", value="3"),
    app_commands.Choice(name="スレッドの削除", value="4")
])
async def manage_thread(
    interaction: discord.Interaction,
    管理キー: str,
    内容: str
):
    channel_key = str(interaction.channel_id)
    data = load_config(CREATED_THREAD_LIST)

    # 入力チェック
    if channel_key not in data:
        await interaction.response.send_message("botが作成したスレッドじゃないみたい（終了）",ephemeral=True)
        return
    elif data[channel_key]["password"] != 管理キー:
        await interaction.response.send_message("管理キーが違うみたい（終了）",ephemeral=True)
        return

    # モーダルの定義
    class ThreadManageModal(Modal):
        def __init__(self):
            super().__init__(title="スレッドを管理")

            # モーダルフィールドの設定
            if 内容 == "0": # タイトル変更
                self.add_item(TextInput(label="変更後のスレタイを入力", placeholder="100文字まで",max_length=100, style=discord.TextStyle.short))
            if 内容 == "1": # 自動ロック時間変更
                self.add_item(TextInput(label="スレ落ち（自動ロック）時間（分）※いまから", placeholder="0～1440までの数字を入れる（0ならスレ落ちしない）",max_length=4, style=discord.TextStyle.short))
            elif 内容 == "2": # 自動削除時間変更
                self.add_item(TextInput(label="スレ自動削除時間（分）※スレ落ち後の時間", placeholder="0～1440までの数字を入れる（0なら自動削除しない）",max_length=4, style=discord.TextStyle.short))
            elif 内容 == "3": # スレッドをロック
                self.add_item(TextInput(label="スレッドのロック（最終確認）", placeholder="ここに「1041」を入れて送信する",max_length=4, style=discord.TextStyle.short))
            elif 内容 == "4": # スレッドを削除
                self.add_item(TextInput(label="スレッドの削除（最終確認）", placeholder="ここに「1041」を入れて送信する",max_length=4, style=discord.TextStyle.short))

        async def on_submit(self, interaction: discord.Interaction):
            # jsonを取得して元の管理情報を変換して変数に入れる
            data = load_config(CREATED_THREAD_LIST)
            ロックまでの時間 = data[channel_key]["lock_time"][0]
            削除までの時間 = data[channel_key]["delete_time"][0]
            lock_time_str = "0"
            lock_time = 0
            delete_time_str = "0"
            delete_time = 0
            # もともとの設定内容に応じて変数を格納
            if ロックまでの時間 == 0:
                if 削除までの時間 == 0: # [自動ロックしない：自動削除しない]の処理
                    pass
                else: # [自動ロックしない：自動削除する]の処理
                    delete_time_str = data[channel_key]["delete_time"][1] #この場合のみ、数値が文字列化されて格納されている
                    delete_time = int(delete_time_str)
            else:
                if 削除までの時間 == 0: # [自動ロックする　：自動削除しない]の処理
                    lock_time_str = data[channel_key]["lock_time"][1]
                    lock_time = datetime.datetime.strptime(lock_time_str, '%Y年%m月%d日%H時%M分')
                else: # [自動ロックする　：自動削除する]の処理
                    lock_time_str = data[channel_key]["lock_time"][1]
                    lock_time = datetime.datetime.strptime(lock_time_str, '%Y年%m月%d日%H時%M分')
                    delete_time_str = data[channel_key]["delete_time"][1]
                    delete_time = datetime.datetime.strptime(delete_time_str, '%Y年%m月%d日%H時%M分')
            # スターターメッセージを取得
            message = await interaction.channel.fetch_message(interaction.channel_id)

            # モーダル入力内容の取得
            try:
                modal_value = int(self.children[0].value)
            except Exception:
                await interaction.response.send_message("入力が変",ephemeral=True)
                return

            if 内容 == "0":
                await interaction.channel.edit(name=self.children[0].value)
                await interaction.response.send_message("タイトル変更完了",ephemeral=True)
                return
            else: # モーダル入力内容の取得・int化
                try:
                    modal_value = int(self.children[0].value)
                except Exception:
                    await interaction.response.send_message("入力が変",ephemeral=True)
                    return

            if 内容 == "1": # 自動ロック時間変更
                if not (0 <= modal_value <= 1440):
                    await interaction.response.send_message("時間は0から1440までで",ephemeral=True)
                    return
                ロックまでの時間 = modal_value
                if modal_value != 0: # ロックする場合
                    detail = f"自動スレ落ち（ロック）時間を__{modal_value}分__にしました"
                    lock_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=modal_value)
                    lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                    if 削除までの時間 != 0: # 削除設定があった場合は時刻を更新（ロックしない→する、なのでintからdatetimeになる）
                        delete_time = lock_time + datetime.timedelta(minutes=削除までの時間)
                        delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')
                else:
                    lock_time = 0 # ロックしない場合
                    detail = "自動スレ落ち（ロック）を__しない__設定にしました"
                    if isinstance(delete_time,datetime.datetime): # もともとロックする＆削除する設定だった場合はdelete_timeにdatetimeではなくint（分）を入れなおす
                        delete_time = 削除までの時間
                        delete_time_str = str(削除までの時間)

            elif 内容 == "2":# 自動削除時間変更
                if not (0 <= modal_value <= 1440):
                    await interaction.response.send_message("時間は0から1440までで",ephemeral=True)
                    return
                削除までの時間 = modal_value
                if modal_value != 0: # 自動削除する場合
                    detail = f"スレ自動削除時間を__{modal_value}分__にしました"
                    delete_time = message.created_at.astimezone(server_timezone) + datetime.timedelta(minutes=ロックまでの時間) + datetime.timedelta(minutes=modal_value)
                    delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')
                else:
                    detail = "スレ自動削除を__しない__設定にしました"
                    delete_time = 0
                    delete_time_str = "0"
            elif 内容 == "3":#スレロック
                lock_time = datetime.datetime.now(server_timezone)
                lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                detail = "スレッドをロックしました"
                if not (modal_value == 1041):
                    await interaction.response.send_message("最終確認失敗",ephemeral=True)
                    return
                if delete_time != 0:
                    delete_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=削除までの時間)
                    delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')
            else: #スレ削除
                if not (modal_value == 1041):
                    await interaction.response.send_message("最終確認失敗",ephemeral=True)
                    return
                detail = "done"
                await interaction.response.send_message("スレッドを削除しました",ephemeral=True)
                await interaction.channel.delete()
                del data[str(interaction.channel_id)]
                save_config(data, CREATED_THREAD_LIST)
                return

            # スレ本文を編集
            matches = [match.start() for match in re.finditer('`', message.content)]
            target_index = matches[-4] -1
            new_content = message.content[:target_index]

            # ロック・削除までの時間を削除して追記
            if ロックまでの時間 == 0 and 内容 != "3":
                new_content += "\n`※このスレッドは落ちません`"
            elif ロックまでの時間 != 0 and 内容 != "3":
                new_content += f"\n`このスレッドは{lock_time_str}くらいに書き込めなくなります`"
            else:
                new_content += "\n`※このスレッドは書き込めなくなりました`"
            if 削除までの時間 == 0:
                new_content += "\n`※このスレッドは消えません…たぶんね`"
            elif 削除までの時間 != 0 and ロックまでの時間 == 0 and 内容 != "3":
                new_content += f"\n`※このスレッドはまだ消えませんが、スレ落ち後{削除までの時間}分で消えます`"
            else:
                new_content += f"\n`このスレッドは{delete_time_str}くらいに消えます`"
            await message.edit(content=new_content)

            # jsonに戻す
            data[channel_key]["delete_time"][0] = 削除までの時間
            data[channel_key]["lock_time"][0] = ロックまでの時間
            data[channel_key]["delete_time"][1] = delete_time_str
            data[channel_key]["lock_time"][1] = lock_time_str
            save_config(data, CREATED_THREAD_LIST)

            # 処理内容に応じたメッセージを送信
            if 内容 == "3":
                await interaction.channel.edit(locked=True,archived=True)
                await interaction.response.send_message("スレッドを手動でロックしました。もう書き込みできないねえ")
            else:
                await interaction.response.send_message(f"スレッドの設定を変更しました\n（{detail}）")

    # モーダル表示
    await interaction.response.send_modal(ThreadManageModal())


# 今日は何の日
@tree.command(name="今日は何の日", description="今日が何の日かお教えします")
async def what_today(interaction: discord.Interaction):
    today = datetime.datetime.now()
    month = today.month
    day = today.day

    # Wikipediaの「今日は何の日」ページのURL
    url = f"https://ja.wikipedia.org/wiki/{month}月{day}日"
    
    # Wikipediaページを取得
    response = requests.get(url)
    if response.status_code != 200:
        await interaction.response.send_message("Wikipediaページの取得に失敗しました。",ephemeral=True)
        return

    # BeautifulSoupでHTMLを解析
    soup = BeautifulSoup(response.text, "html.parser")

    # ページ内の「記念日」「誕生日」「忌日」のセクションを探す
    sections = soup.find_all("h2")
    events = {"できごと": [], "誕生日": [], "忌日": [], "記念日・年中行事": []}

    for section in sections:
        header_text = section.text.strip()
        if header_text in events.keys():
            ul = section.find_next("ul")
            if ul:
                for li in ul.find_all("li"):
                    events[header_text].append(li)

    # 各カテゴリーからランダムに1つ選択
    chosen_category = random.choice(list(events.keys()))
    print(list(events.keys()))
    if events[chosen_category]:
        chosen_event = random.choice(events[chosen_category])
        formatted_event = format_event(chosen_event, chosen_category, month, day)
        await interaction.response.send_message(formatted_event)
    else:
        await interaction.response.send_message("{chosen_category}に該当するデータが見つかりませんでした。")

def format_event(event, category, month, day):
    # 年・人物名・説明を抽出する正規表現
    text = event.text.strip()
    match = re.match(r"(\d{1,4}年) - (.+)", text)
    if match:
        year = match.group(1)
        details = match.group(2)

        # 最初のリンクを探し、年号リンクはスキップ
        link_url = None
        for link in event.find_all("a", href=True):
            href = urllib.parse.unquote(link['href'])
            if not re.match(r"/wiki/\d+年$", href) and not re.match(r"/wiki/\d+%E5%B9%B4$", href):  # 年号リンクを除外
                link_url = f"https://ja.wikipedia.org{href}"
                break


        if category == "誕生日":
            result = f"__**【誕生日】**__\n{year}{month}月{day}日は、{details}の誕生日です。"
        elif category == "忌日":
            result = f"__**【忌日】**__\n{year}{month}月{day}日は、{details}の命日です。"
        elif category == "できごと":
            result = f"__**【歴史】**__\n{year}{month}月{day}日、{details}"
        elif category == "記念日・年中行事":
            result = f"__**【記念日】**__\n{month}月{day}日は、{details}"
        else:
            result = f"{year}{month}月{day}日は、{details}に関連する記念日です。"

        # リンクがあれば結果に追加
        if link_url:
            result += f"\n関連リンク: [{href}]({link_url})"
        return result
    else:
        # 正規表現にマッチしない場合はそのまま返す
        return f"{month}月{day}日には、{text}"



# チャンネルから出ていくコマンドテスト
@tree.command(name="ジェネリックoyasumi", description="30秒間、このチャンネルの閲覧を制限します。")
async def self_purge(interaction: discord.Interaction):
    channel = interaction.channel
    user = interaction.user
    if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel) or isinstance(channel, discord.ForumChannel):
        # 現在のパーミッションを取得
        overwrite = channel.overwrites_for(user)

        # 読み取り権限を拒否
        overwrite.read_messages = False
        await channel.set_permissions(user, overwrite=overwrite)

        await interaction.response.send_message("30秒間、このチャンネルの閲覧を制限しました。", ephemeral=True)

        # 30秒待機
        await asyncio.sleep(30)

        # パーミッションを元に戻す
        await channel.set_permissions(user, overwrite=None)

        await interaction.followup.send("閲覧制限を解除しました。", ephemeral=True)

@tree.command(name="ほしいものリスト", description="Amazonで商品を検索してランダムな商品を表示します")
@app_commands.describe(検索ワード="検索したいワードを入力してください")
async def wish_list(interaction: discord.Interaction, 検索ワード: str = "干し芋"):

    await interaction.response.defer(thinking=True)

    # AmazonのURLと検索クエリを作成
    url = f"https://www.amazon.co.jp/s?k={検索ワード}"

    # ユーザーエージェントを偽装するオプションを設定。amazonの503エラーの回避
    user_agents = [
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 OPR/77.0.4054.254',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 Edg/92.0.902.55',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 OPR/77.0.4054.254',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 Edg/92.0.902.55',
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 OPR/77.0.4054.254'
    ]

    referers = [
      'https://narou-osusume.com/osusumes/2',
      'https://narou-osusume.com/osusumes/10',
      'https://narou-osusume.com/osusumes/15'
    ]

    # ランダムにユーザーエージェントとリファラを選択
    user_agent = random.choice(user_agents)
    referer = random.choice(referers)

    # ユーザーエージェントを偽装するためのヘッダーを設定
    headers = {
        'User-Agent': user_agent,
        'Referer': referer
    }

    response = requests.get(url, headers=headers)

    # レスポンスのパース
    soup = BeautifulSoup(response.content, 'html.parser')

    # 最初の5つの商品を取得
    items = soup.find_all('div', {'data-component-type': 's-search-result'}, limit=5)

    if items:
        # ランダムに1つの商品を選択
        item = random.choice(items)
        title = item.h2.text.strip()
        asin = item['data-asin']  # ASINを取得

        # 価格を取得
        price = item.find('span', {'class': 'a-color-price'})
        if price:
            price = price.text + "円"
        else:
            price = "価格情報なし"

        link = f"https://www.amazon.co.jp/dp/{asin}/"
        response_message = f"[**{title}**]({link})\n価格: {price}\n"
    else:
        response_message = "検索結果が見つかりませんでした。"

    await interaction.followup.send(response_message)

"""
--------------コンテキストメニューコーナー--------------
"""


# 匿名でレスするコンテキストメニュー
@tree.context_menu(name="とくめいさんにレスさせる")
async def ano_reply(interaction: discord.Interaction,
                    message: discord.Message):
    await interaction.response.send_modal(ReplyModal(message))


@tree.context_menu(name="おっぱい")
async def oppai(interaction: discord.Interaction, message: discord.Message):
    try:
        await message.add_reaction("<:oppai:1253325289896022066>")
        await interaction.response.send_message("リアクションを追加したパイ",ephemeral=True,delete_after=5)
    except Exception as e:
        print(f"{e} from {message.author.name}")
        await interaction.response.send_message("致命的なエラー:sob:",ephemeral=True,delete_after=5)


# 名前を奪う（サーバープロフィールネームを変更する）コンテキストメニュー
@tree.context_menu(name="名前を奪う")
async def change_nickname(interaction: discord.Interaction,user: discord.Member):
    if user == bot.user:
        await interaction.response.send_message("自分の名前は変更できなくてェ…",ephemeral=True)
        return

    try:
        await user.edit(nick=PREDEFINED_NAME)
        await interaction.response.send_message(
            f"{user.name}のサーバーニックネームを{PREDEFINED_NAME}に変更しました。",ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("このユーザーのニックネームを変更する権限がありません。",ephemeral=True)
    except discord.HTTPException as e:
        await interaction.response.send_message(
            f"ニックネームの変更中にエラーが発生しました: {str(e)}", ephemeral=True)


# あとで読む（自分にDM）コンテキストメニュー
@tree.context_menu(name="あとで読む")
async def dm_self(interaction: discord.Interaction, message: discord.Message):
    user = interaction.user

    # メッセージがDM内のものであるかをチェック
    #if isinstance(message.channel, discord.DMChannel):
    if message.guild is None:
        if message.author == bot.user:
            await message.delete()
            await interaction.response.send_message(
                "メッセージを削除しました。月島さんのおかげでしたか？", ephemeral=True)
        else:
            await interaction.response.send_message("DM内では使えないよ",ephemeral=True)
        return

    # メッセージの情報を取得
    server_name = message.guild.name
    channel_name = message.channel.name
    author_name = message.author.display_name
    author_id = message.author.id
    author_avatar_url = message.author.display_avatar.url if message.author.display_avatar else None
    content = message.content
    attachments = message.attachments
    timestamp = message.created_at.strftime("%Y/%m/%d %H:%M")

    # 元のメッセージへのリンクを作成
    message_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"

    # 埋め込みメッセージの作成
    embed = discord.Embed(title="",
                          description=content,
                          color=discord.Color.blue())
    embed.set_author(name=f"{author_name}@{author_id}",
                     icon_url=author_avatar_url)
    embed.set_footer(text=f"元レスの投稿日時: {timestamp}")

    # メッセージが埋め込みを含む場合、その情報を取得
    if message.embeds:
        for original_embed in message.embeds:
            if original_embed.description:
                embed.add_field(name="",
                                value=original_embed.description,
                                inline=False)
            # 埋め込み内の画像を取得
            if original_embed.image:
                embed.set_image(url=original_embed.image.url)
            # 埋め込み内の動画やサムネイルなども処理
            if original_embed.thumbnail:
                embed.set_thumbnail(url=original_embed.thumbnail.url)
            if original_embed.url:
                embed.add_field(name="リンク",
                                value=original_embed.url,
                                inline=False)
            elif original_embed.video:
                embed.add_field(name="動画",
                                value=original_embed.video.url,
                                inline=False)

    # 添付ファイルがある場合、それを埋め込みに追加
    for attachment in attachments:
        # URLのクエリパラメータを取り除くための正規表現
        url_without_query = re.sub(r'\?.*$', '', attachment.url.lower())
        if url_without_query.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):  # 動画は埋め込み不可
            new_url = attachment.url.replace('cdn.discordapp.com', 'media.discordapp.net')# 長期間有効なURLに
            embed.set_image(url=new_url)
            embed.add_field(name="", value=attachment.url, inline=False)
        else:
            embed.add_field(name="添付ファイル", value=attachment.url, inline=False)

    # DMを送信
    try:
        await user.send(
            content=
            f"{server_name} #{channel_name}の[レス]({message_link})を挟み込んでおいたよ",
            embed=embed,silent=True)
        await interaction.response.send_message("DMにしおりを挟んでおいたよ",
                                                ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('"DMは"\n"送られなかった"\n※DM拒否してない？',
                                                ephemeral=True)


### --------------on_reaction_addコーナー-------------- ###
# delが溜まるとタイムアウト
@bot.event
async def on_reaction_add(reaction, user):
    global is_enabled_react
    global anonyms
    if is_enabled_react:
        message_dsc = ""
        imgurl = ""
        emb_title = "☆☆☆【PR】人気のツイート☆☆☆"
        if reaction.message.author == bot.user:  #botへのリアクションは無視する。ただし匿名機能へのDELを除く。匿名発言にDELが20個溜まったら真名看破
            if str(reaction.emoji) == '<:DEL:1247440603244003438>' and reaction.count == 8 and reaction.message.id not in processed_messages_special:
                try:
                    post_num = anonyms[reaction.message.id][0]
                    user_id = anonyms[reaction.message.id][1]
                    processed_messages_special.add(reaction.message.id)
                    del_embed = discord.Embed(
                        title="【真名看破】",
                        description=
                        f"### 占いの結果、__とくめいさん#{post_num}__の発言者は<@{user_id}>だったようです",
                        color=0xff0000  # 色を指定 (赤)
                    )
                    await reaction.message.reply(embed=del_embed, silent=True)
                except Exception:
                    return
        elif str(reaction.emoji
               ) == '<:DEL:1247440603244003438>':  # ":del:"絵文字のUnicode表現
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                try:
                    processed_messages.add(reaction.message.id)
                    await reaction.message.author.timeout(
                        timedelta(seconds=10))  # 1時間タイムアウト（3600秒）
                    emb_title = "☆☆☆【PR】不人気のツイート☆☆☆"
                    message_dsc = f"<:DEL:1247440603244003438>が溜まったので{reaction.message.author.mention}が10秒間発言できなくなるよ"
                except discord.HTTPException as e:
                    await reaction.message.channel.send(f"なんかエラー: {e}")
        elif str(reaction.emoji) == '<:debu:1250566480542826627>': # DEB
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"<:debu:1250566480542826627>が溜まったので{reaction.message.author.mention}の体脂肪率が0.5ポイント増える呪いをかけました"
        elif str(reaction.emoji) == '<:yasero:1346359624806174752>': # やせろ
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"<:yasero:1346359624806174752>{reaction.message.author.mention}"
        elif str(reaction.emoji) == '<:death:1248828254056616016>':
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## {reaction.message.author.mention} is Dead....<:death:1248828254056616016>"
        elif str(reaction.emoji) == '<:jusei:1249566862388232273>':
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"<:jusei:1249566862388232273>{reaction.message.author.mention} の調教段階が進み、従順Lvが5になりました"
        elif str(reaction.emoji) == '<:mujiina1:1248093698848325713>':
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## <:mujiina1:1248093698848325713>[流行る](<{reaction.message.jump_url}>)"
        elif str(reaction.emoji) == '<:mujiina2:1249007942078824570>':
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## <:mujiina2:1249007942078824570>[流行らない](<{reaction.message.jump_url}>)"
        elif str(reaction.emoji) == '<:nen:1247585412298313759>':  # 念
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## [念レス成功](<{reaction.message.jump_url}>)<:nen:1247585412298313759>"
        elif str(reaction.emoji) == '<:soudane:1247440583086051398>':  # そうだね
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = "## そうだね×10"
        elif str(reaction.emoji) == '<:iemon:1250776114213818429>':  # 伊右衛門お嬢様
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"伊右衛門を{reaction.message.author.mention}にしやがって…<:iemon:1250776114213818429>"
        elif str(reaction.emoji) == '<:aura:1253323998855434331>':  # アウラ
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"{reaction.message.author.mention}は伊達じゃない<:aura:1253323998855434331>"
        elif str(reaction.emoji) == '<:mageress:1247767251327651840>':  # マジレス
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## [誰このおっさん](<{reaction.message.jump_url}>)<:mageress:1247767251327651840>"
        elif str(reaction.emoji) == '<:warota:1255428332091346986>':  # 久々にワロタ
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## [久々にワロタ](<{reaction.message.jump_url}>)\nこういうレスがたくさんあったのが昔の虹裏なんだよな\n新参は過去のmayを知らないから困る<:warota:1255428332091346986>"
        elif str(reaction.emoji) == '<:dora:1248099357413216377>':  # ドラえもん
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## これは[ホモレス](<{reaction.message.jump_url}>)だ！<:dora:1248099357413216377>"
        elif str(reaction.emoji) == '<:Nan:1254712481708773417>':  # ナン
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## [ナン](<{reaction.message.jump_url}>)だこれ<:Nan:1254712481708773417>"
        elif str(reaction.emoji) == '<:tycoon:1247919780980064287>':  # タイクーン王
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## [レス](<{reaction.message.jump_url}>)の様子が変なのだ…\nそこはうんちを出し入れする穴なのだ！<:tycoon:1247919780980064287>"
        elif str(reaction.emoji) == '<:robot_humebatasukarunoni:1247766333656010853>':  # 踏めば助かるのにロボ
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"## [死ねば助かるのに…](<{reaction.message.jump_url}>)<:seiron_robot_hume_fume:1356184491999236267>"
        elif str(reaction.emoji
               ) == '<:oppai:1253325289896022066>':  # おっぱい（ロールへのメンション付き）
            if reaction.count == 5 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"# <@&1257339248982360165>[！？](<{reaction.message.jump_url}>) "
        elif str(reaction.emoji) == '💩':  # うんこ（名前変更付き）
            if reaction.count == 10 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = "## うんこマン！うんこマンじゃないか！"
                try:
                    await reaction.message.author.edit(nick="うんこマン💩")
                except discord.HTTPException:
                    pass
        elif str(reaction.emoji) == '<:hennano:1247814839024488460>':  #また変なの見ちゃった
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"### また[変なの](<{reaction.message.jump_url}>)見ちゃった！<:hennano:1247814839024488460>"
        elif str(reaction.emoji) == '<:kyuunikita:1253701288458326076>':  #急に来た？
            if reaction.count == 6 and reaction.message.id not in processed_messages:
                processed_messages.add(reaction.message.id)
                message_dsc = f"> [急に来た？](<{reaction.message.jump_url}>)\n## <:kyuuya:1247821553262006282>"


        # 埋め込みを作成して投稿
        # メッセージ本文は60文字まででうちきり
        if message_dsc != "":
            react_embed = discord.Embed(
                title=emb_title,
                description=message_dsc,
                color=0xff1493  # 色を指定 (ピンク)
            )
            react_embed.set_image(url=imgurl)
            #react_embed.set_author(
            #    name=reaction.message.author.display_name, # ユーザー名
            #    icon_url=reaction.message.author.display_avatar # アイコン
            #)
            message_content = reaction.message.content
            message_time = reaction.message.created_at.astimezone(server_timezone)  #JSTに変換
            if len(message_content) > 60:
                message_content = '```' + message_content[:60] + '...' + '```'
            elif len(message_content) >0:
                message_content = '```' + message_content + '```'
            elif len(message_content) ==0:
                message_content = ''
            react_embed.add_field(name="[元のレス：" +
                                  message_time.strftime("%Y年%m月%d日 %H:%M") +
                                  f"{server_timezone}]({reaction.message.jump_url})",
                                  value=message_content,
                                  inline=False)
            await reaction.message.reply(embed=react_embed, silent=True)


### --------------on_messageコーナー-------------- ###
@bot.event
async def on_message(message):

    # メッセージがボット自身からのものであれば無視する
    if message.author == bot.user:
        return

    # 「ちせい」と「ごはん」が含まれていた場合、レシピを表示
    if "ちせい" in message.content and "ごはん" in message.content:
        for attempt in range(5):  # 最大5回まで試行
            recipe_id = random.randint(1000000, 9999999)  # 適当なレシピIDの範囲
            url = f"https://cookpad.com/recipe/{recipe_id}"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

            if response.status_code == 200:
                await message.reply(f"URL: {url}")
                return
        return
    """
    # 特定のユーザーが発言したら消す
    if message.author.id == 111222333444:
        await message.delete()
        return
    """

    """
    # BOTコマンドの利用に対する警告
    # 特定のチャンネル以外でのメッセージか確認する
    global is_enabled_onmessage_bot
    if is_enabled_onmessage_bot:
        if message.channel.id not in BOTCOMMAND_ALERT_CHANNEL_ID:  # 指定のチャンネル以外で実行
            if message.content.lower().startswith('m!'):# m!で始まるものの場合実行
                await message.reply(
                    'ログが流れちゃうので音楽botのコマンドは https://discord.com/channels/1247402487531700234/1255871958512439306 とか https://discord.com/channels/1247402487531700234/1247402487531700238 でやろうね\n\n※このメッセージは自動的に消えます',
                    delete_after=30,
                    silent=True)
            elif message.author.id in BOT_AUTODELETE_ID:# 特定のBOTのメッセージに対して実行
                await asyncio.sleep(15)  # 15秒待機
                await message.delete()
    """

    # 気温に関する発言があったら気温を表示
    if is_enabled_onmessage_temp:
        global temp_time_before
        temp_time_now = time.time()
        if temp_time_now - temp_time_before > 30:  #30秒以内には再登場しない
            temp_words = ["暑い", "寒い", "あつい", "さむい", "暑くね", "寒くね"]
            for s in temp_words:
                if s in message.content:
                    #ループ処理で取得した天気リストを使う
                    global temp_list

                    # ランダム天気
                    lis = [
                        "",
                        f"\nなお、富山県富山市は現在{temp_list['toyama'][4]}ですが、回線速度への影響はありません",
                        f"\n最高気温タイトルホルダー埼玉県熊谷市の現在の気温は{temp_list['kumagaya'][1]}度です",
                        f"\nまた、長崎は{temp_list['nagasaki'][4]}でした",
                        f"\nちなみに日本最北端、宗谷岬（北海道稚内市）の現在の気温は{temp_list['souya'][1]}度です",
                        f"\n一方、キテレツ大百科で有名な静岡県浜松市は{temp_list['shizuoka'][4]}なう"
                    ]

                    # 埋め込み作成
                    temp_title = f"本日({temp_list['attu'][0]})の天気をお知らせします"
                    temp_message = (
                        f"- 🥶__**サムイ島**__は現在{temp_list['samui'][4]}、気温は**{temp_list['samui'][1]}度**です\n"
                        f" - 本日の体感気温は__最高**{temp_list['samui'][2]}度**__、__最低**{temp_list['samui'][3]}度**__です\n"
                        f"- 🥵__**アッツ島**__は現在{temp_list['attu'][4]}、気温は**{temp_list['attu'][1]}度**です\n"
                        f" - 本日の体感気温は__最高**{temp_list['attu'][2]}度**__、__最低**{temp_list['attu'][3]}度**__です"
                        f"{random.choice(lis)}")
                    temp_embed = discord.Embed(
                        title=temp_title,
                        description=temp_message,
                        color=0x3498db  # 色を指定 (青色)
                    )
                    # 返信でメッセージを送信
                    await message.reply(embed=temp_embed,
                                        silent=True,
                                        delete_after=30)
                    temp_time_before = time.time()
                    return

    # 雑談スレの速度監視
    if is_enabled_channelspeed:
        if message.channel.id == SPEED_CHANNEL_ID[0] and not message.author.bot:
            now = datetime.datetime.now()
            user_id = message.author.id
            global beforeslot
            global nextslot
            # 現在の10分スロットを計算
            slot = (now.minute // TIME_WINDOW_MINUTES) % 7
            nextslot = 0 if nextslot == 7 else slot + 1

            print(f"User {user_id} message at {now}, slot {slot}")
            message_log[user_id][slot] += 1

            # 過去60分間のメッセージの合計をカウント
            total_messages = sum(message_log[user_id])
            print(f"User {user_id} total messages: {total_messages}")
            #if total_messages >= THRESHOLD:
            #    await lock_user_in_channel_a(message.guild, message.author)

            for user_id in list(message_log.keys()):
                # スロットが変更された場合、次のスロットを全員分0に
                if slot != beforeslot:
                    message_log[user_id][nextslot] = 0
                # スロットの合計が0である場合、リスト内のそのユーザーに関する項目を削除
                if sum(message_log[user_id]) == 0:
                    del message_log[user_id]
            beforeslot = slot
            # デバッグのため、現在のmessage_logの状況をプリント
            print(f'Current message log at {now}:')
            for user_id, log in message_log.items():
                print(f'User ID {user_id}: {list(log)}')

    # 指定チャンネルの発言を匿名変換
    if is_enabled_anochange:
        if not message.author.bot and message.channel.id in ANO_CHANGE_CHANNEL_ID:  # 発言者がbotでない場合、指定のチャンネル以外で実行
            # 特定のユーザーだったら実行しない
            if not message.author.id == 726752221500276746:
                # 添付ファイルを取得
                attachment_file = None
                attachment_file_log = None
                if message.attachments:
                    attachment = message.attachments[0]
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as response:
                            if response.status == 200:
                                data = await response.read()
                                # ファイル名をクリーンアップ
                                filename = re.sub(r'[^\w\.\-]', '_', attachment.filename)
                                # バイナリデータをメモリに保存
                                attachment_file = discord.File(io.BytesIO(data), filename=filename)
                                attachment_file_log = discord.File(io.BytesIO(data), filename=filename)# ログに添付する用

                # 返信かどうかを確認
                res_message = None
                resmode = False
                if message.reference:
                    res_message = await message.channel.fetch_message(message.reference.message_id)
                    resmode = True

                await ano_post(message.content, message.author.id, False, None, None, resmode, res_message,message.channel.id,attachment_file,attachment_file_log)
            await message.delete()

    """
    # 特定のワードに反応
    if is_enabled_autoreply:
        if not message.author.bot:  # 発言者がbotでない場合、指定のチャンネル以外で実行
            global temp_time_before
            temp_time_now = time.time()
            if temp_time_now - temp_time_before > 30:  #30秒以内には再登場しない
                temp_words = ["伝説って？"]
                for s in temp_words:
                    if s in message.content:
                        autoreply_message = "> 伝説って？\nああ！"
                        await message.reply(content=autoreply_message,silent=True)
    """
### --------------loopコーナー-------------- ###
# 地震速報
# 5秒に1回取得
@tasks.loop(seconds=10)
async def fetch_earthquake():
    global is_enabled_earthquake
    if not is_enabled_earthquake:
        return

    global last_eq_id
    eq_json_url = "https://api.p2pquake.net/v2/history?codes=556&limit=1"
    response = requests.get(eq_json_url)
    if response.status_code == 200:
        eq_json_dict = response.json()
        eq_id   = eq_json_dict[0]["id"]
        if eq_id != last_eq_id:
            print(eq_id,last_eq_id)
            last_eq_id = eq_id
            config['last_eq_id'] = last_eq_id
            a_time    = eq_json_dict[0]["earthquake"]["arrivalTime"]
            magnitude = eq_json_dict[0]["earthquake"]["hypocenter"]["magnitude"]
            area_name = eq_json_dict[0]["earthquake"]["hypocenter"]["name"]
            max_area  = eq_json_dict[0]["areas"][0]["name"]
            max_scale = str(eq_json_dict[0]["areas"][0]["scaleTo"])
            max_scale = "{}{}{}".format(max_scale[:1], ".", max_scale[1:])
            eq_embed = discord.Embed(
                title="地震もいいけど大槍の描く尻は芸術だと思う",
                description=f"発信時刻：**{a_time}**\nマグニチュード：**{magnitude}**\n震源地：**{area_name}**\n最大震度：**{max_scale} @ {max_area}**",
                color=0xff0000  # 赤
            )
            eq_embed.set_image(url="https://media.discordapp.net/attachments/1261752672856444948/1271014746849677353/D6KdwHiUwAA8wY8.jpg")
            for channel_id in EARTHQUAKE_CHANNEL_ID:
                await bot.get_channel(channel_id).send(embed=eq_embed)
            save_config(config, CONFIG_FILE)

# 温度取り
# 30分ごとに値を再取得する
@tasks.loop(seconds=1800)
async def fetch_weather():
    global temp_list
    temp_list = {}
    temp_posi = {
        'attu': ['52.8763', '172.8904'],
        'samui': ['9.5357', '99.9357'],
        'toyama': ['36.7', '137.2167'],
        'kumagaya': ['36.135', '139.3901'],
        'nagasaki': ['32.75', '129.8833'],
        'souya': ['45.3121', '141.5612'],
        'shizuoka': ['34.9833', '138.3833']
    }

    with open("configs/weather_code.json", 'r') as f:
        weather_code = json.load(f)

    for city, coordinates in temp_posi.items():
        latitude, longitude = coordinates
        url = f'https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,apparent_temperature,weather_code&daily=weather_code,apparent_temperature_max,apparent_temperature_min&timezone=Asia%2FTokyo&forecast_days=1'

        response = requests.get(url)
        if response.status_code == 200:
            json_dict_temp = response.json()
            ttime = json_dict_temp["daily"]["time"][0]
            tnow = json_dict_temp["current"]["temperature_2m"]
            tmax = json_dict_temp["daily"]["apparent_temperature_max"][0]
            tmin = json_dict_temp["daily"]["apparent_temperature_min"][0]
            temoji = weather_code[str(
                json_dict_temp["daily"]["weather_code"][0])]
            temp_list[city] = [ttime, tnow, tmax, tmin, temoji]
        else:
            print(
                f"Failed to get data for {city}, HTTP status code: {response.status_code}"
            )

    # ファイルに書き込み（別に必要ないけど）
    with open("configs/temp.json", "w", encoding="utf-8") as json_file:
        json.dump(temp_list, json_file, ensure_ascii=False, indent=4)
    return

@fetch_weather.before_loop
async def before_fetch_weather():
    await bot.wait_until_ready()


# mayとimgのカタログをスクレイピングする
@tasks.loop(seconds=333)
async def fetch_data():
    global is_enabled_futaba
    if not is_enabled_futaba:
        return
    global keyword_list
    target_urls = ['https://may.2chan.net/b/', 'https://img.2chan.net/b/']
    count = 0
    for site_url in target_urls:
        cookie = {
            'cxyl': '14x15x18x0x1'
        }  #横x縦x文字数x?x画像サイズ(画像サイズ0だとURLが変わるので注意)
        get_url = f'{site_url}futaba.php?mode=cat&sort=6'  #勢順
        get_response = requests.get(get_url, cookies=cookie)
        soup = BeautifulSoup(get_response.text, 'html.parser')

        #出力済みのURL一覧を取得
        with open('configs/result.txt', 'r', encoding='utf-8') as file:
            results = [line.strip() for line in file]

        threads = [str(i) for i in soup.find_all('td')]

        filtered_threads = []

        for thread in threads:
            if any(key in thread.lower()
                   for key in keyword_list) and not any(res in thread for res in results):
                filtered_threads.append(str(thread))
                count += 1
                if count == 2: # 2スレ紹介したらループを終わる
                    break
            if count == 2: # 2スレ紹介したらループを終わる
                break

        for key, server_ids in keyword_list.items():
            for thread in filtered_threads:
                idx = thread.find('res/')
                link = thread[idx:]
                idx = link.find('.htm')
                link = link[:idx + 4]
                full_link = site_url + link

                idx = thread.find('thumb/')
                thumb = thread[idx:]
                idx = thumb.find('.jpg')
                thumb = thumb[:idx + 4]
                thumb = site_url + thumb

                idx = thread.find('<small>')
                text = thread[idx + 7:]
                idx = text.find('</small>')
                text = text[:idx]
                # 正規表現パターン
                pattern = r'http[s]?(?:[^\s<>"]*|$)'
                # URL を削除
                cleaned_text = re.sub(pattern, '', html.unescape(text))
                if cleaned_text == '':
                    cleaned_text = "ｷﾀ━━━━(ﾟ∀ﾟ)━━━━!!"

                idx = thread.find('<font size="2">')
                res = thread[idx + 15:]
                idx = res.find('</font>')
                res = res[:idx]

                futaba_embed = discord.Embed(
                    title='',
                    description=
                    f"__**↓こんなスレを見つけました↓**__\n### [{cleaned_text}]({full_link}) [現在{res}レス]",
                    color=0xf0e0d6  # 色を指定
                )
                futaba_embed.set_thumbnail(url=thumb)
                if site_url == 'https://may.2chan.net/b/':
                    futaba_embed.set_footer(text='†二次裏観測情報@may†')
                else:
                    futaba_embed.set_footer(text='†二次裏観測情報@img†')

                if key in thread.lower() and not any(res in thread for res in results):
                    print(text,full_link)
                    for server_id, channel_ids in server_ids.items():
                        for channel_id in channel_ids:
                            await bot.get_channel(channel_id).send(embed=futaba_embed)
                        results.append(link)  #重複排除用
                        if len(results) > 40:
                            del results[0]  #重複リストがいっぱいになったら古いものを削除

            str_ = '\n'.join(results)
            with open("configs/result.txt", 'wt') as f:
                f.write(str_)

@fetch_data.before_loop
async def before_fetch_data():
    await bot.wait_until_ready()


# スレッドの時限停止処理
@tasks.loop(seconds=312)
async def check_threads():
    global is_enabled_threadstop
    if is_enabled_threadstop:
        now = datetime.datetime.today().astimezone(server_timezone)

        for target_channel_id in TARGET_CHANNEL_ID: # スレッド監視対象チャンネルリストに載ってるそれぞれのチャンネルについて
            target_channel = bot.get_channel(target_channel_id)
            for thread in target_channel.threads: # チャンネル内の各スレッドについて
                # スレッドがアーカイブまたはロックされていないこと、スレッド作成時間がNoneではないこと、ピン止めされていないことを確認
                if thread.created_at is not None and not thread.flags.pinned:
                    thread_creation_time = thread.created_at
                    time_diff = now - thread_creation_time

                    # 指定時間経過でスレッドロックからの自動削除
                    if target_channel_id in AUTODELETE_CHANNEL_ID: #スレッド自動削除対象チャンネルリストに載っている場合
                        # スレッドが2時間以上前に作成されている場合
                        if time_diff > timedelta(minutes=180):  #3時間
                            if not thread.archived or not thread.locked:
                                thread_embed = discord.Embed(
                                    title='',
                                    description="このスレッドはロックされました。そのうち消えます（削除予定：120分後）",
                                    color=0x3498db  # 色を指定 (青色)
                                )
                                await thread.send(embed=thread_embed)
                                await thread.edit(archived=True, locked=True)
                        elif time_diff > timedelta(minutes=175):  #5分前
                            if not thread.archived or not thread.locked:
                                thread_embed = discord.Embed(
                                    title='',
                                    description="このスレッドは古いのでもうすぐ書き込めなくなります（ロック予定：5分後）",
                                    color=0x3498db  # 色を指定 (青色)
                                )
                                await thread.send(embed=thread_embed)

                        # アーカイブされているスレッドに対する処理
                        archived_thread = target_channel.archived_threads(limit=None)
                        async for thread in archived_thread:

                            # スレッド作成時間がNoneではないこと、ピン止めされていないことを確認
                            if thread.created_at is not None and not thread.flags.pinned:
                                thread_creation_time = thread.created_at  #タイムゾーン情報をutcに
                                time_diff = now - thread_creation_time
                                if time_diff > timedelta(minutes=300):  #5時間
                                    await thread.delete()
                                    print(f"Thread '{thread.name}' deleted.")


@check_threads.before_loop
async def before_check_threads():
    await bot.wait_until_ready()


# スレッドの時限停止処理（新）
@tasks.loop(seconds=312)
async def check_threads_2nd():
    created_thread_list = load_config(CREATED_THREAD_LIST)
    now = datetime.datetime.today().astimezone(server_timezone)
    # リストにあるスレッドのロック時間が経過しているかを確認する
    for thread_id,config in list(created_thread_list.items()):
        # json読み込み
        guild = bot.get_guild(config["guild"])
        thread = guild.get_channel_or_thread(int(thread_id))
        if not thread: # スレッドが存在しない（取得できない）場合はリストから消す
            del created_thread_list[thread_id]
            save_config(created_thread_list,CREATED_THREAD_LIST)
            continue
        if thread.flags.pinned: # ピン留めされてるスレッドは触らない
            continue
        ロックまでの時間 = config["lock_time"][0]
        削除までの時間 = config["delete_time"][0]
        lock_time_str = config["lock_time"][1]
        delete_time_str = config["delete_time"][1]
        try:
            lock_time = datetime.datetime.strptime(lock_time_str, '%Y年%m月%d日%H時%M分').astimezone(server_timezone)
        except Exception:
            pass
        try:
            delete_time = datetime.datetime.strptime(delete_time_str, '%Y年%m月%d日%H時%M分').astimezone(server_timezone)
        except Exception:
            pass
        now = datetime.datetime.now(server_timezone)

        # ロック・クローズ処理　※クローズしたスレッドは取り出すのが面倒なので削除予定がある場合はロックのみ
        if ロックまでの時間 != 0:
            if not thread.locked:
                if now > lock_time:# ロック予定時刻を過ぎてたら
                    if delete_time_str == "0":
                        thread_embed = discord.Embed(
                            title='',
                            description="このスレッドはロックされました。過去ログとして保管されています。",
                            color=0x3498db  # 色を指定 (青色)
                        )
                        await thread.send(embed=thread_embed)
                        await thread.edit(archived=True, locked=True)
                        del created_thread_list[thread_id]
                        save_config(created_thread_list,CREATED_THREAD_LIST)
                    else:
                        thread_embed = discord.Embed(
                            title='',
                            description=f"このスレッドはロックされました。そのうち消えます（削除予定：{delete_time_str}）",
                            color=0x3498db  # 色を指定 (青色)
                        )
                        await thread.send(embed=thread_embed)
                        await thread.edit(locked=True)
                elif now > lock_time - datetime.timedelta(minutes=5): # ロック予定時刻5分前を切ってたら
                    description="このスレッドは古いのでもうすぐ書き込めなくなります（ロック予定：5分後）"
                    thread_embed = discord.Embed(
                        title='',
                        description=description,
                        color=0x3498db  # 色を指定 (青色)
                    )
                    await thread.send(embed=thread_embed)

        # 削除処理
        if 削除までの時間 != 0:
            if now > delete_time:
                await thread.delete()
                del created_thread_list[thread_id]
                save_config(created_thread_list,CREATED_THREAD_LIST)
                print(f"Thread '{thread.name}' deleted.")


@check_threads.before_loop
async def before_check_threads_2nd():
    await bot.wait_until_ready()


# 指定チャンネル・スレッドでのメッセージ自動削除
@tasks.loop(minutes=15)
async def delete_old_messages():
    now = datetime.datetime.today().astimezone(server_timezone)
    fourteen_days_ago = now - timedelta(days=14)
    to_delete_id=[]
    for target_id, settings in autodelete_config.items():
        try:
            target = bot.get_channel(int(target_id)) or bot.get_thread(int(target_id))
        except Exception: # 指定したチャンネルが見つからなかった場合、設定を削除する
            to_delete_id.append(target_id)
            continue
        if target:
            minutes = settings['minutes']
            to_delete = []
            threshold = now - timedelta(minutes=minutes)
            async for message in target.history(before=threshold, limit=None):
                message_creation_time = message.created_at
                if message.id == int(target_id) or message.pinned or message.type == discord.MessageType.channel_name_change or message_creation_time < fourteen_days_ago:
                    continue  # スターターメッセージとピン止めと削除できないシステムメッセージと14日以上前のメッセージは削除しない
                if now - message_creation_time > timedelta(minutes=minutes):
                    to_delete.append(message)
                if len(to_delete) >= 100:
                    await target.delete_messages(to_delete)
                    if settings['ログ保存'] is True:
                        log_deleted_messages(target.name, to_delete)#削除した分だけログファイルに書き込み
                    to_delete = []
                    await asyncio.sleep(2)  # レートリミットを避けるための待機

            # 残りのメッセージを削除
            if len(to_delete) >= 1:
                await target.delete_messages(to_delete)
                if settings['ログ保存'] is True:
                    log_deleted_messages(target.name, to_delete)#削除した分だけログファイルに書き込み
                to_delete = []

    # 見つからなかったチャンネルIDをリストから削除
    for target_id in to_delete_id:
        del autodelete_config[target_id]
    save_config(autodelete_config,AUTODELETE_LIST)


@delete_old_messages.before_loop
async def before_delete_old_messages():
    await bot.wait_until_ready()


@bot.tree.command(name="onoff", description="各種設定を行う")
@app_commands.describe(
    スレッド監視="スレッドを一定時間でロックする機能のオンオフを設定します。オプションを指定しないと現在の設定を表示します。",
    リアクション監視="リアクションが一定数溜まると通知する機能のオンオフを設定します",
    二次裏監視="二次裏のスレ本文を監視して通知する機能のオンオフを設定します",
    bot発言監視="BOTの発言を監視して通知する機能のオンオフを設定します",
    温度発言監視="温度に関する発言にリアクションする機能のオンオフを設定します",
    チャンネル速度監視="特定のチャンネルの速度を監視する機能のオンオフを設定します",
    メッセージ削除ログ="メッセージ削除ログ取得機能のオンオフを設定します",
    地震速報通知="緊急地震速報の情報取得オンオフを設定します"
)
async def onoff(interaction: discord.Interaction,
                スレッド監視: bool = None,
                リアクション監視: bool = None,
                二次裏監視: bool = None,
                bot発言監視: bool = None,
                温度発言監視: bool = None,
                チャンネル速度監視: bool = None,
                メッセージ削除ログ: bool = None,
                地震速報通知: bool = None):
    global config
    global is_enabled_threadstop, is_enabled_react, is_enabled_futaba
    global is_enabled_channelspeed,is_enabled_msgdellog
    global is_enabled_onmessage_bot, is_enabled_onmessage_temp,is_enabled_earthquake

    if スレッド監視 is not None:
        is_enabled_threadstop = スレッド監視
    if リアクション監視 is not None:
        is_enabled_react = リアクション監視
    if 二次裏監視 is not None:
        is_enabled_futaba = 二次裏監視
    if bot発言監視 is not None:
        is_enabled_onmessage_bot = bot発言監視
    if 温度発言監視 is not None:
        is_enabled_onmessage_temp = 温度発言監視
    if チャンネル速度監視 is not None:
        is_enabled_channelspeed = チャンネル速度監視
    if メッセージ削除ログ is not None:
        is_enabled_msgdellog = メッセージ削除ログ
    if 地震速報通知 is not None:
        is_enabled_earthquake = 地震速報通知

    config['is_enabled_threadstop'] = is_enabled_threadstop
    config['is_enabled_react'] = is_enabled_react
    config['is_enabled_futaba'] = is_enabled_futaba
    config['is_enabled_onmessage_bot'] = is_enabled_onmessage_bot
    config['is_enabled_onmessage_temp'] = is_enabled_onmessage_temp
    config['is_enabled_channelspeed'] = is_enabled_channelspeed
    config['is_enabled_msgdellog'] = is_enabled_msgdellog
    config['is_enabled_earthquake'] = is_enabled_earthquake
    save_config(config, CONFIG_FILE)

    status1 = "有効" if is_enabled_threadstop else "無効"
    status2 = "有効" if is_enabled_react else "無効"
    status3 = "有効" if is_enabled_futaba else "無効"
    status4 = "有効" if is_enabled_onmessage_bot else "無効"
    status5 = "有効" if is_enabled_onmessage_temp else "無効"
    status6 = "有効" if is_enabled_channelspeed else "無効"
    status7 = "有効" if is_enabled_msgdellog else "無効"
    status8 = "有効" if is_enabled_earthquake else "無効"

    await interaction.response.send_message(
        f"- 現在の設定は次のとおりです\n - スレッド監視： {status1}\n - リアクション監視： {status2}\n - 二次裏監視： {status3}\n - bot発言監視： {status4}\n - 温度発言監視： {status5}\n - チャンネル速度監視： {status6}\n - メッセージ削除ログ： {status7}\n - 地震速報通知： {status8}"
    )


### --------------on_guild_channel_createコーナー-------------- ###
@bot.event
async def on_guild_channel_create(channel):
    event_guild = str(channel.guild.id)
    list = CREATED_ALERT_CHANNEL_ID[event_guild]
    # 通知先チャンネルの指定
    alert_channel = bot.get_channel(list[0])
    # ボイスチャンネルが作成された場合
    if channel.type == discord.ChannelType.voice:
        # NSFW指定する
        await channel.edit(nsfw=True,position=1)
        # ViewとButtonを作成
        view = View()
        button = Button(label="チャンネルに参加", url=channel.jump_url)
        view.add_item(button)
        now = datetime.datetime.now(server_timezone).strftime('%H時%M分')

        message = await alert_channel.send(
            f"{now}にボイス🔊チャンネル __**{channel.name}**__ が作成されたよ\n※`/rename`コマンドでチャンネルの名前を変更できます",
            view=view)

        # 削除用にチャンネルIDとメッセージIDを記録
        new_channel_dict = load_config(NEWCHANNEL_LIST)
        new_channel_dict[channel.id] = message.id
        save_config(new_channel_dict, NEWCHANNEL_LIST)

### --------------on_guild_channel_deleteコーナー-------------- ###
@bot.event
async def on_guild_channel_delete(channel):
    event_guild = str(channel.guild.id)
    list = CREATED_ALERT_CHANNEL_ID[event_guild]
    alert_channel = bot.get_channel(list[0])
    target_channel_id = str(channel.id)
    # 通知済みリストにあるチャンネルが削除された場合
    new_channel_dict = load_config(NEWCHANNEL_LIST)
    if target_channel_id in new_channel_dict:
        try:
            message = await alert_channel.fetch_message(new_channel_dict[target_channel_id])
            await message.delete()
        except Exception:
            pass
        del new_channel_dict[target_channel_id]
        save_config(new_channel_dict, NEWCHANNEL_LIST)

### --------------on_guild_channel_updateコーナー-------------- ###
@bot.event
async def on_guild_channel_update(channel, after):
    event_guild = str(channel.guild.id)
    list = CREATED_ALERT_CHANNEL_ID[event_guild]
    alert_channel = bot.get_channel(list[0])
    target_channel_id = str(channel.id)
    # 通知済みリストにあるチャンネルが更新された場合
    new_channel_dict = load_config(NEWCHANNEL_LIST)
    if target_channel_id in new_channel_dict:
        try:
            message = await alert_channel.fetch_message(new_channel_dict[target_channel_id])
            await message.edit(content=f"ボイス🔊チャンネル __**{after.name}**__ が更新されたよ\n※`/rename`コマンドでチャンネルの名前を変更できます")
        except Exception:
            del new_channel_dict[target_channel_id]
            save_config(new_channel_dict, NEWCHANNEL_LIST)


### --------------on_thread_createコーナー-------------- ###
@bot.event
async def on_thread_create(thread):
    # 監視対象のチャンネルに新規スレッドが立った場合、同じサーバーの指定されたチャンネルにリンクを投稿する
    if TARGET_CHANNEL_ID: # リストが空の場合は実行しない
        if thread.parent.id in TARGET_CHANNEL_ID: # 対象チャンネルかどうかの確認
            # リストの各IDごとにアラートを飛ばす先のテキストチャンネルを取得
            for channel_id in FORUM_ALERT_CHANNEL_ID:
                text_channel = bot.get_channel(channel_id)
                if text_channel.guild == thread.guild: # 同じサーバーかどうかの確認
                    # メッセージの基本部分を作成
                    message_content = f"## __★★★新スレ速報__\n- **[{thread.parent.name}]({thread.parent.jump_url})**に__{thread.jump_url}__が作成されたよ"

                    # 画像の有無を確認して分岐
                    images=None
                    try:
                        starter_message = await thread.fetch_message(thread.id) # スターターメッセージを取得
                        if starter_message and starter_message.attachments:
                            images = [att.url for att in starter_message.attachments if att.content_type and 'image' in att.content_type]
                    except discord.NotFound:
                        print("Starter message not found.")

                    embed = discord.Embed(
                        title="",
                        description=message_content,
                        color=discord.Color.green()
                    )
                    #添付ファイルがあったらイメージを追加
                    if images:
                        embed.set_image(url=images[0])

                    await text_channel.send(embed=embed)

    # 自動削除対象のフォーラムだった場合は自動削除情報を書き込む
    if AUTODELETE_CHANNEL_ID: # リストが空の場合は実行しない
        if thread.owner != bot.user: # このbot自身の機能で作成されたスレッドは対象外
            parent_channel_id = str(thread.parent.id)
            if parent_channel_id in AUTODELETE_CHANNEL_ID: # 対象チャンネルかどうかの確認
                lock_minutes = AUTODELETE_CHANNEL_ID[parent_channel_id][0]
                delete_minutes = AUTODELETE_CHANNEL_ID[parent_channel_id][1]
                if lock_minutes > 0:
                    lock_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=lock_minutes)
                    lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                    if delete_minutes > 0:
                        delete_time = lock_time + datetime.timedelta(minutes=delete_minutes)
                        delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')
                    else:
                        delete_time_str = "なし"
                else:
                    lock_time_str = "なし"
                    delete_time_str = "未定"

                # JSONデータの保存
                data = load_config(CREATED_THREAD_LIST)
                data[thread.id] = {
                    "guild": thread.guild.id,
                    "lock_time": [lock_minutes,lock_time_str],
                    "delete_time": [delete_minutes,delete_time_str],
                    "password": "qawsedrftgyhujikolp"
                }
                save_config(data, CREATED_THREAD_LIST)

                await thread.send(f"このスレッドは自動で消えます。\n書き込み終了予定：{lock_time_str}\n削除予定：{delete_time_str}")

### --------------on_message_deleteコーナー-------------- ###
# メッセージ削除ログの保存
@bot.event
async def on_raw_message_delete(payload):
    if not is_enabled_msgdellog:
        return
    if payload.guild_id is None:
        return  # DMチャンネルでの削除は無視

    # ログチャンネルを取得
    log_channel = bot.get_channel(DELETE_LOG_CHANNEL_ID[0])
    if log_channel is None:
        print("ログチャンネルが見つかりません。")
        return

    delete_time = datetime.datetime.now(server_timezone)#削除実行時間は監査ログではなく現時点とする（監査ログは複数件まとまるので）
    deleter = None
    guild = bot.get_guild(payload.guild_id)

    if payload.cached_message is None:  # キャッシュに存在しない場合
        channel = bot.get_channel(payload.channel_id)
        embed = discord.Embed(
            title="",
            description=f"### メッセージ削除ログ（古いメッセージ）\n\
                **チャンネル**：<#{channel.id}> [`{channel.name}`]\n\
                **メッセージID**：`{payload.message_id}`",
            color=discord.Color.red()
        )
    else:
        message = payload.cached_message

        async for entry in guild.audit_logs(limit=7, action=discord.AuditLogAction.message_delete):
            if entry.target.id == message.author.id and (delete_time - entry.created_at).total_seconds() < 300:
                deleter = entry.user
                break

        # 発言者がbotで、かつ削除者の情報が取得できない場合は無視。そうでなければdeleter_infoを入れて進む   
        if deleter is None:
            if message.author.bot:
                return
            else:
                deleter_info = "不明（たぶん本人かbot）"
        else:
            deleter_info = f"<@{deleter.id}> [`{deleter.name}`]"

        previous_message = None
        # 削除されたメッセージの直前のメッセージを取得
        async for previous_message in message.channel.history(before=message, limit=1):
            if previous_message:
                prev_message_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{previous_message.id}"
                prev_msg = f"[メッセージ削除ログ]({prev_message_link})"
                break
        else:
            prev_msg = "メッセージ削除ログ"

        # 削除されたメッセージが埋め込み（embed）だった場合、descriptionを本文として扱う
        if message.embeds:
            embed_description = message.embeds[0].description
        else:
            embed_description = message.content or "（本文なし）"

        # 削除されたメッセージの情報を埋め込み形式で作成
        post_time = message.created_at
        post_time_tz = (post_time.astimezone(server_timezone)).strftime(f"%Y/%m/%d %H:%M:%S {server_timezone}")
        delete_time_tz = (delete_time.astimezone(server_timezone)).strftime(f"%Y/%m/%d %H:%M:%S {server_timezone}")
        embed = discord.Embed(
            title="",
            description=f"### {prev_msg}\n\
                **チャンネル**：<#{message.channel.id}> [`{message.channel.name}`]\n\
                **発言者**：<@{message.author.id}> [`{message.author.name}`]\n\
                **削除者**：{deleter_info}\n\
                **発言時刻**：{post_time_tz}\n\
                **削除時刻**：{delete_time_tz}",
            color=discord.Color.red()
        )
        embed.add_field(name="本文", value=embed_description, inline=False)

        # 削除されたメッセージの添付ファイルがある場合、それを埋め込みに追加
        if message.attachments:
            for attachment in message.attachments:
                # URLのクエリパラメータを取り除くための正規表現
                url_without_query = re.sub(r'\?.*$', '', attachment.url.lower())
                if url_without_query.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    embed.set_image(url=url_without_query)
                #set_imageに乗らないタイミングがあるっぽいので苦肉の策
                embed.add_field(name="添付ファイル", value=url_without_query, inline=False)

    # ログチャンネルに埋め込みメッセージを送信
    await log_channel.send(embed=embed)

# クライアントの実行
bot.run(os.environ['TOKEN'])
