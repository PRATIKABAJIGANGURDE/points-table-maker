import discord
from discord.ext import commands
import os

from config import TOKEN
from database import db #, init_db

# Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class PTMaker(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        print("Initializing database...")

        
        # Ensure cogs directory exists
        if not os.path.exists("./cogs"):
            os.makedirs("./cogs")

        print("Loading extensions...")
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print(f"Loaded: {filename}")
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")
        
        print("Bot is ready to sync. Use !sync to sync global commands or !clear_guild to remove server-specific duplicates.")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print(f"Bot is in {len(self.guilds)} servers.")
        
        # Verbose Logging of commands in tree
        print("\nRegistered Slash Commands in Tree:")
        for command in self.tree.get_commands():
            print(f"- /{command.name}")
        
        print("\nSyncing commands to guilds...")
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"✅ Synced {len(synced)} commands to: {guild.name}")
            except Exception as e:
                print(f"❌ Failed to sync for {guild.name}: {e}")
        
        print("------\nBot is fully ready!")

if __name__ == "__main__":
    bot = PTMaker()
    bot.run(TOKEN)
