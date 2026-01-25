import discord
from discord import app_commands
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all available commands")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Scrim Bot Help Menu",
            description="Manage your Free Fire scrims, automate slot lists, and generate Points Tables with AI.",
            color=discord.Color.gold()
        )
        
        # 1. Scrim Management
        embed.add_field(
            name="🎮 Scrim Management",
            value=(
                "`/start_scrim` - Create a new lobby & paste slot list.\n"
                "`/upload_lobby_ss` - (Alternative) Upload screenshot to auto-fill slots.\n"
                "`/slots [lobby_id]` - View current slot list.\n"
                "`/end_scrim [lobby_id]` - End scrim & generate final Points Table."
            ),
            inline=False
        )
        
        # 2. Match Results
        embed.add_field(
            name="📊 Match Results",
            value=(
                "`/submit_match [lobby_id] [match_no] [images]` - Upload match screenshots for AI processing.\n"
                "*The bot will automatically extract kills/ranks & ask for confirmation.*"
            ),
            inline=False
        )
        
        # 3. Admin & Setup
        embed.add_field(
            name="⚙️ Admin & Setup",
            value=(
                "`/setup [role] [channels...]` - Configure admin role & channels.\n"
                "`/set_branding [host_name] [logo]` - Set your Tournament Banner & Logo.\n"
                "`/sync` - Sync bot commands (Fix if commands are missing)."
            ),
            inline=False
        )
        
        embed.set_footer(text="Developed for High-Precision Scrims")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Help(bot))
