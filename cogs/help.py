import discord
from discord import app_commands
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show admin operations workflow")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ Scrim Operations Bot (Admin Only)",
            description=(
                "⚠️ **This bot is intended for Scrim Admins & Management only.**\n"
                "Player interaction is not supported.\n\n"
                "**Goal:** Manage Free Fire scrims end-to-end (Lobby → AI Results → Points Table)."
            ),
            color=discord.Color.gold()
        )
        
        # 1. Scrim Workflow
        embed.add_field(
            name="🧭 Scrim Workflow",
            value=(
                "**1️⃣ /start_scrim**\n"
                "Create a new lobby & paste/upload slot list.\n\n"
                "**2️⃣ Upload Slot List**\n"
                "(Done within /start_scrim or /slots)\n\n"
                "**3️⃣ Upload Lobby Screenshot**\n"
                "Use `/upload_lobby_ss` to auto-fill & verify slots.\n\n"
                "**4️⃣ /submit_match**\n"
                "Upload match result screenshots. AI extracts data (confirmation required).\n\n"
                "**5️⃣ /edit_match (if needed)**\n"
                "Fix any incorrect extraction or missing data.\n\n"
                "**6️⃣ /end_scrim**\n"
                "Automatically generate & send the final Points Table."
            ),
            inline=False
        )
        
        # 2. Recovery / Fixes
        embed.add_field(
            name="🛠️ Recovery & Fixes",
            value=(
                "• **Wrong match data?** → Use `/edit_match`\n"
                "• **Uploaded wrong image?** → Re-run `/submit_match` (overwrites)\n"
                "• **Missing commands?** → Run `/sync`\n"
                "• **New server setup?** → Run `/setup`"
            ),
            inline=False
        )
        
        # 3. AI Safety Notice
        embed.add_field(
            name="🤖 AI Notice",
            value="Screenshot analysis is assistive. **All results must be reviewed** before final submission.",
            inline=False
        )
        
        embed.set_footer(text="Internal Ops Tool v2.0")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Help(bot))
