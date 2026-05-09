from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Shark is online!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_flask).start()

import discord
from discord.ext import commands
import asyncio
import json
import requests

TOKEN = os.getenv("DISCORD_TOKEN")

def get_stats(player):
    try:
        url = f"https://api.playhive.com/v0/game/all/all/{player}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if "bed" in data:
                bed = data["bed"]
                return {
                    "games": bed.get("played", 0),
                    "wins": bed.get("victories", 0),
                    "kills": bed.get("kills", 0),
                    "final_kills": bed.get("final_kills", 0),
                    "beds": bed.get("beds_destroyed", 0),
                    "deaths": bed.get("deaths", 0),
                }
        return None
    except:
        return None

def tracking_embed(username, stats):
    embed = discord.Embed(title=f"Tracking {username}", color=0x2ECC71)
    embed.add_field(name="Games", value=f"{stats['games']:,}", inline=True)
    embed.add_field(name="Wins", value=f"{stats['wins']:,}", inline=True)
    embed.add_field(name="Kills", value=f"{stats['kills']:,}", inline=True)
    embed.set_footer(text="Shark Tracker • Every 3s")
    return embed

def alert_embed(username, match_stats):
    kills = match_stats.get('kills', 0)
    beds = match_stats.get('beds', 0)
    deaths = match_stats.get('deaths', 0)
    wins = match_stats.get('wins', 0)
    
    result = "WIN" if wins > 0 else "LOSS"
    color = 0x00FF00 if wins > 0 else 0xFF0000
    
    embed = discord.Embed(
        title=f"{username} Is Playing BedWars!",
        description=f"**Match - {result}**\nKills: **{kills}** | Beds: **{beds}** | Deaths: **{deaths}**",
        color=color
    )
    embed.set_footer(text="Shark • GO GO GO!")
    return embed

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

TRACKING_FILE = "tracking.json"
tracking = {}
alert_channel = {}
last_stats = {}

def save_tracking():
    try:
        with open(TRACKING_FILE, 'w') as f:
            json.dump({"players": tracking, "channels": alert_channel, "last_stats": last_stats}, f)
    except:
        pass

def load_tracking():
    global tracking, alert_channel, last_stats
    try:
        with open(TRACKING_FILE, 'r') as f:
            data = json.load(f)
            tracking = data.get("players", {})
            alert_channel = data.get("channels", {})
            last_stats = data.get("last_stats", {})
    except:
        pass

load_tracking()

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Bot online. Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync error: {e}")
    for player in list(tracking.keys()):
        stats = get_stats(player)
        if stats:
            last_stats[player] = {
                "wins": stats["wins"], "kills": stats["kills"],
                "final_kills": stats["final_kills"], "beds": stats["beds"], "deaths": stats["deaths"]
            }
    save_tracking()
    bot.loop.create_task(tracking_loop())

@bot.tree.command(name="track", description="Track a BedWars player")
async def track(interaction: discord.Interaction, player: str):
    await interaction.response.defer()
    stats = get_stats(player)
    if stats is None:
        await interaction.followup.send(f"Could not find: {player}")
        return
    tracking[player] = stats["games"]
    last_stats[player] = {
        "wins": stats["wins"], "kills": stats["kills"],
        "final_kills": stats["final_kills"], "beds": stats["beds"], "deaths": stats["deaths"]
    }
    alert_channel[player] = interaction.channel.id
    save_tracking()
    embed = tracking_embed(player, stats)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="list", description="Show tracked players")
async def tracklist(interaction: discord.Interaction):
    await interaction.response.defer()
    if not tracking:
        await interaction.followup.send("Not tracking anyone!")
        return
    msg = "**Tracking List:**\n"
    for p, g in tracking.items():
        msg += f"{p}: {g:,} games\n"
    await interaction.followup.send(msg)

@bot.tree.command(name="stop", description="Stop tracking")
async def stoptrack(interaction: discord.Interaction, player: str):
    if player in tracking:
        del tracking[player]
        alert_channel.pop(player, None)
        last_stats.pop(player, None)
        save_tracking()
        await interaction.response.send_message(f"Stopped {player}")
    else:
        await interaction.response.send_message(f"Not tracking {player}")

@bot.tree.command(name="check", description="Check player stats")
async def check(interaction: discord.Interaction, player: str):
    await interaction.response.defer()
    stats = get_stats(player)
    if stats is None:
        await interaction.followup.send(f"Not found: {player}")
        return
    embed = tracking_embed(player, stats)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="ping", description="Test if Shark is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Shark is online!")

async def tracking_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for player, old_games in list(tracking.items()):
            new_stats = get_stats(player)
            if new_stats:
                new_games = new_stats["games"]
                if new_games > old_games:
                    old = last_stats.get(player, {})
                    match = {
                        "wins": max(0, new_stats["wins"] - old.get("wins", 0)),
                        "kills": max(0, new_stats["kills"] - old.get("kills", 0)),
                        "final_kills": max(0, new_stats["final_kills"] - old.get("final_kills", 0)),
                        "beds": max(0, new_stats["beds"] - old.get("beds", 0)),
                        "deaths": max(0, new_stats["deaths"] - old.get("deaths", 0)),
                    }
                    tracking[player] = new_games
                    last_stats[player] = {
                        "wins": new_stats["wins"], "kills": new_stats["kills"],
                        "final_kills": new_stats["final_kills"], "beds": new_stats["beds"], "deaths": new_stats["deaths"]
                    }
                    save_tracking()
                    ch = alert_channel.get(player)
                    if ch:
                        channel = bot.get_channel(ch)
                        if channel:
                            embed = alert_embed(player, match)
                            await channel.send("**SNIPE ALERT!**", embed=embed)
        await asyncio.sleep(3)

bot.run(TOKEN)
