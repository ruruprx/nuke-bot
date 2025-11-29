import subprocess
import sys
import os
import json
import random
import time
import asyncio
import discord 
from datetime import datetime
from discord.ext import commands
from colorama import Fore, init, Style; init()
from flask import Flask
from threading import Thread

sys.tracebacklimit = 0

# --- 24/7 Webサーバー機能 (Render/Gunicorn対応) ---
# GunicornがこのFlaskアプリ (app) をメインとしてロードします
app = Flask(__name__)

@app.route('/')
def home():
    # UptimeRobotからのPingに応答するエンドポイント
    return "Server Management Bot is alive!", 200

def run_server():
    # Gunicorn実行時にFlaskサーバー自体は不要ですが、ログ目的として
    port = os.environ.get('PORT', 8080) 
    print(f"{Fore.CYAN}Web Server running to keep the bot alive! Port {port}.")

async def start_web_server():
    # Botの非同期処理を邪魔しないように、Gunicornが実行していることを前提にログを出す
    server_thread = Thread(target=run_server)
    server_thread.start()
# ----------------------------------------------------

# --- スパムフィルターの設定とログ (簡易版) ---
spam_settings = {
    "word_filter_enabled": False,
    "link_filter_enabled": False,
    "blocked_words": ["死ね", "殺す", "くそ", "fxxk"],
    "punishment_action": "delete" # 'delete' or 'warn'
}
spam_log_data = []
# ----------------------------------------------------

class Config:
    def __init__(self):
        self.load_config()
        
    def load_config(self):
        # 1. 環境変数からトークンを読み込む (Renderで推奨される方法)
        self.token = os.environ.get('BOT_TOKEN')
        
        if not self.token:
            print(f"{Fore.RED}FATAL: トークンが見つかりません。Renderの環境変数に BOT_TOKEN を設定してください。")
            sys.exit(1)
            
        # 2. config.jsonから他の設定を読み込む（ファイルがない場合はデフォルト値を使用）
        try:
             with open("./config.json", "r") as f:
                 config_data = json.load(f)
                 # 以前の「荒らしBot」の設定を引き継いだ項目
                 self.minimum_dm = config_data.get("minimum_dm_delay", 1)
                 self.maximum_dm = config_data.get("maximum_dm_delay", 3)
                 self.skip_booting = config_data.get("skip_booting", False)
                 self.skip_disclaimer = config_data.get("skip_disclaimer", False)
                 self.min_ban = config_data.get("minimum_ban_delay", 1)
                 self.max_ban = config_data.get("maximum_ban_delay", 3)
                 self.min_general = config_data.get("minimum_general_delay", 0.5)
                 self.max_general = config_data.get("maximum_general_delay", 1.5)
        except (FileNotFoundError, json.JSONDecodeError):
             print(f"{Fore.YELLOW}Warning: config.jsonが見つからないか破損しています。デフォルト設定を使用します。")
             self.minimum_dm = 1
             self.maximum_dm = 3
             self.skip_booting = False
             self.skip_disclaimer = False
             self.min_ban = 1
             self.max_ban = 3
             self.min_general = 0.5
             self.max_general = 1.5
        except Exception as e:
            print(f"{Fore.RED}Error loading config: {e}")
            sys.exit(1)

config = Config()

def random_cooldown(minimum, maximum):
    return random.uniform(minimum, maximum)

async def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

# --- Botクラスの定義とDiscordコマンドの設定 ---
class ServerManagerBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.members = True          # メンバーリストの取得
        intents.guilds = True           # サーバー情報の取得
        intents.message_content = True  # メッセージ内容の読み取り (重要)
        super().__init__(command_prefix='!', intents=intents, *args, **kwargs)
        
    async def on_ready(self):
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Server Management"
            ),
            status=discord.Status.online
        )
        await clear_console()
        await start_web_server() 
        print(f"{Fore.LIGHTGREEN_EX}Logged in as: {Fore.YELLOW}{self.user}")
        
        # 起動時にコマンドラインのメニューを表示
        await main_menu(self)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            permission = str(error.missing_permissions[0]).replace('_', ' ').title()
            await ctx.send(f"❌ 権限がありません。必要な権限: **{permission}**")
        elif isinstance(error, commands.CommandNotFound):
            # コマンドが見つからないエラーは無視（CLIメニュー操作が優先のため）
            pass 
        else:
            print(f"{Fore.RED}Discord Command Error: {error}")
            # raise error # デバッグ用にエラーを再発生させることも可能

    async def on_message(self, message):
        # Bot自身やシステムメッセージは無視
        if message.author.bot or message.webhook_id:
            await self.process_commands(message)
            return

        # ------------------- スパムフィルターの実行 -------------------
        content = message.content.lower()
        detected = False
        reason = ""

        # ワードスパムチェック
        if spam_settings["word_filter_enabled"]:
            for word in spam_settings["blocked_words"]:
                if word in content:
                    detected = True
                    reason = f"禁止ワード検出: `{word}`"
                    break
        
        # リンクスパムチェック (簡易版)
        if not detected and spam_settings["link_filter_enabled"]:
            if "discord.gg/" in content or "discord.com/invite/" in content:
                detected = True
                reason = "招待リンクスパム検出"
                
        # スパムが検出された場合の処理
        if detected:
            if spam_settings["punishment_action"] == "delete":
                try:
                    await message.delete()
                except discord.Forbidden:
                    print(f"{Fore.RED}メッセージ削除権限がありません。")
                    
            # ログを記録
            log_entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user": str(message.author),
                "user_id": message.author.id,
                "channel": message.channel.name,
                "reason": reason,
                "content": message.content
            }
            spam_log_data.append(log_entry)
            print(f"{Fore.YELLOW}🚨 スパム検出: {reason} by {message.author}")

        # ------------------- Discordコマンドの処理 -------------------
        await self.process_commands(message)

# Botインスタンスの作成
client = ServerManagerBot()

# --- Discordコマンドの定義 (Chat Commands) ---

@client.command(name="ping")
async def ping_command(ctx):
    """コマンド実行者の応答速度を確認します"""
    latency = client.latency * 1000 
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"現在の応答速度 (Latency): **{latency:.2f}ms**",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@client.command(name="serverinfo")
async def serverinfo_command(ctx):
    """現在のサーバー情報が表示されます"""
    guild = ctx.guild 
    embed = discord.Embed(
        title=f"【 {guild.name} 】のサーバー情報",
        color=discord.Color.green(),
        timestamp=ctx.message.created_at
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="🌐 サーバーID", value=guild.id, inline=True)
    embed.add_field(name="👑 オーナー", value=guild.owner.mention, inline=True)
    embed.add_field(name="📅 作成日", value=guild.created_at.strftime("%Y/%m/%d"), inline=True)
    embed.add_field(name="👥 メンバー数", value=guild.member_count, inline=True)
    embed.add_field(name="🛡️ ロール数", value=len(guild.roles), inline=True)
    embed.add_field(name="💬 チャンネル数", value=len(guild.channels), inline=True)
    await ctx.send(embed=embed)

@client.command(name="get_avatar")
async def get_avatar_command(ctx, member: discord.Member = None):
    """指定したユーザー（または実行者）のアバターURLを表示します"""
    if member is None:
        member = ctx.author
    avatar_url = member.display_avatar.url
    embed = discord.Embed(
        title=f"👤 {member.display_name} のアバター",
        color=discord.Color.blue()
    )
    embed.set_image(url=avatar_url)
    embed.add_field(name="🔗 URL", value=f"[画像を直接表示]({avatar_url})", inline=False)
    await ctx.send(embed=embed)

@client.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode_command(ctx, seconds: int):
    """チャンネルの低速モードを設定し、スパムを防ぎます。"""
    if seconds < 0 or seconds > 21600:
        await ctx.send("設定できる秒数は0秒から21600秒（6時間）の間です。", ephemeral=True)
        return
    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send(f"✅ {ctx.channel.mention} の低速モードを**解除**しました。")
        else:
            await ctx.send(f"✅ {ctx.channel.mention} の低速モードを**{seconds}秒**に設定しました。")
    except discord.Forbidden:
        await ctx.send("🚨 権限不足：Botにチャンネル管理権限がありません。", ephemeral=True)

@client.command(name="spam_filter")
@commands.has_permissions(administrator=True)
async def spam_filter_command(ctx, filter_type: str = None, action: str = None):
    """スパムフィルターの設定を行います (メモリ内保存)"""
    if filter_type is None:
        await ctx.send(f"現在の設定: ワードブロック: {spam_settings['word_filter_enabled']}, リンクブロック: {spam_settings['link_filter_enabled']}")
        return
        
    filter_type = filter_type.lower()
    
    if filter_type == "word" and action in ["on", "off"]:
        spam_settings["word_filter_enabled"] = (action == "on")
        await ctx.send(f"✅ ワードスパムフィルターを {'有効' if action == 'on' else '無効'} にしました。")
    elif filter_type == "link" and action in ["on", "off"]:
        spam_settings["link_filter_enabled"] = (action == "on")
        await ctx.send(f"✅ 招待リンクフィルターを {'有効' if action == 'on' else '無効'} にしました。")
    else:
        await ctx.send("無効な引数です。使い方: `!spam_filter word on` または `!spam_filter link off`")

@client.command(name="spam_log")
@commands.has_permissions(manage_messages=True)
async def spam_log_command(ctx, count: int = 5):
    """最新のスパム検出ログを表示します (メモリ内保存)"""
    if not spam_log_data:
        await ctx.send("現在、記録されているスパムログはありません。")
        return

    logs_to_display = spam_log_data[-count:]
    embed = discord.Embed(
        title=f"📋 最新 {len(logs_to_display)} 件のスパム検出ログ",
        color=discord.Color.orange()
    )
    for entry in reversed(logs_to_display):
        log_text = (
            f"**理由**: {entry['reason']}\n"
            f"**ユーザー**: {entry['user']} ({entry['user_id']})\n"
            f"**チャンネル**: {entry['channel']}\n"
            f"**メッセージ**: `{entry['content'][:50]}...`"
        )
        embed.add_field(name=f"[{entry['time']}]", value=log_text, inline=False)
    await ctx.send(embed=embed)


# --- CLIメニュー定義 (Console Operations) ---

async def show_disclaimer():
    if not config.skip_disclaimer:
        messages = [
            f"{Fore.LIGHTWHITE_EX}{Style.BRIGHT}DISCLAIMER (免責事項):",
            f"{Fore.LIGHTWHITE_EX}このツールはサーバー管理の学習目的で提供されています。",
            f"{Fore.LIGHTGREEN_EX}{Style.BRIGHT}Botトークンは環境変数 BOT_TOKEN に設定されています。{Style.RESET_ALL}{Fore.RESET}",
            f"{Fore.LIGHTWHITE_EX}大量DMなどの機能は削除され、健全な管理機能に置き換えられています。"
        ]
        for msg in messages:
            print(msg)
            await asyncio.sleep(0.3)

async def show_boot_animation():
    if not config.skip_booting:
        stages = ["Booting Management Tool", "25%", "50%", "75%", "100%"]
        delays = [0.3, 0.5, 0.6, 0.7, 0.2]
        for stage, delay in zip(stages, delays):
            print(f"{Fore.LIGHTWHITE_EX}{stage}")
            await asyncio.sleep(delay)

# CLI操作関数 (以前のnuke/raid機能を置き換え)
async def cli_kick_member(client, guild_id, user_id, reason="CLIからのキック"):
    guild = client.get_guild(guild_id)
    if not guild:
        print(f"{Fore.RED}サーバーID {guild_id} が見つかりません。")
        return
    member = guild.get_member(user_id)
    if not member:
        print(f"{Fore.RED}ユーザーID {user_id} がサーバーに見つかりません。")
        return
    try:
        await member.kick(reason=reason)
        print(f"{Fore.LIGHTGREEN_EX}{member.display_name} をキックしました。理由: {reason}")
    except discord.Forbidden:
        print(f"{Fore.RED}キック権限がありません（Botのロール順位を確認してください）。")
    except Exception as e:
        print(f"{Fore.RED}キック失敗: {e}")
    input("Press Enter to continue...")


async def main_menu(client):
    while True:
        await clear_console()
        
        # 簡易ASCIIアート
        print(f'''
{Fore.LIGHTYELLOW_EX}███████╗███████╗██████╗ ███████╗██╗   ██╗██████╗ 
{Fore.LIGHTYELLOW_EX}██╔════╝██╔════╝██╔══██╗██╔════╝██║   ██║██╔══██╗
{Fore.LIGHTYELLOW_EX}███████╗█████╗  ██████╔╝█████╗  ██║   ██║██████╔╝
{Fore.LIGHTYELLOW_EX}╚════██║██╔══╝  ██╔══██╗██╔══╝  ██║   ██║██╔══██╗
{Fore.LIGHTYELLOW_EX}███████║███████╗██║  ██║███████╗╚██████╔╝██║  ██║
{Fore.LIGHTYELLOW_EX}╚══════╝╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝''')
        
        stats = f"Servers: {len(client.guilds)} | Users: {len(client.users)}"
        
        print(f'''{Fore.LIGHTWHITE_EX}                          Server Management Tool

{Fore.LIGHTGREEN_EX}Logged in as: {Fore.YELLOW}{client.user}
{Fore.LIGHTGREEN_EX}{stats}

{Fore.LIGHTGREEN_EX}[1] CLI Kick Member (コンソールからのキック実行)
{Fore.LIGHTGREEN_EX}[2] Exit (Botを停止)

{Fore.LIGHTWHITE_EX}--- Discordコマンド (チャットで利用) ---
{Fore.LIGHTWHITE_EX}  !ping, !serverinfo, !get_avatar, !slowmode [秒数]
{Fore.LIGHTWHITE_EX}  !spam_filter [word/link] [on/off], !spam_log
''')
        
        choice = input(f"{Fore.LIGHTGREEN_EX}Select>> ").lower()
        
        if choice == '1':
            try:
                guild_id = int(input(f'{Fore.LIGHTYELLOW_EX}対象サーバーIDを入力: '))
                user_id = int(input(f'{Fore.LIGHTYELLOW_EX}キック対象のユーザーIDを入力: '))
                reason = input(f'{Fore.LIGHTYELLOW_EX}キックの理由を入力 (任意): ')
                await cli_kick_member(client, guild_id, user_id, reason)
            except ValueError:
                print(f'{Fore.RED}無効なIDが入力されました。')
                await asyncio.sleep(1)
                
        elif choice in ['2', 'quit', 'exit']:
            print(f"{Fore.LIGHTGREEN_EX}Goodbye!")
            await client.close()
            sys.exit(0)
        else:
            print(f"{Fore.RED}無効な選択です")
            await asyncio.sleep(1)


async def main():
    await show_disclaimer()
    await show_boot_animation()
    
    try:
        await client.start(config.token)
    except discord.LoginFailure:
        print(f"{Fore.RED}無効なトークンです - 環境変数 BOT_TOKEN を確認してください。")
        sys.exit(1)
    except Exception as e:
        print(f"{Fore.RED}致命的なエラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"{Fore.YELLOW}Botを停止します。")
