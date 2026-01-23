import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils import is_scrim_admin

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slots", description="Show the slot list for a lobby")
    @app_commands.describe(lobby_id="The ID of the lobby")
    async def slots(self, interaction: discord.Interaction, lobby_id: int):
        # Get lobby info
        lobby = db.get_lobby(lobby_id)
        if not lobby:
            return await interaction.response.send_message("Lobby not found.", ephemeral=True)

        lobby_name = lobby[2]
        max_teams = lobby[4]
        
        # Get registered teams with slots
        teams_rows = db.get_teams_in_lobby(lobby_id)
        # teams_rows is list of (slot, id, team_name)
        teams = {row[0]: row[2] for row in teams_rows}

        embed = discord.Embed(title=f"🎮 Slot List - {lobby_name}", color=discord.Color.blue())
        
        slot_list = ""
        for i in range(1, max_teams + 1):
            team_name = teams.get(i, "--- Empty ---")
            slot_list += f"**Slot {i}:** {team_name}\n"
        
        embed.description = slot_list
        await interaction.response.send_message(embed=embed)



async def setup(bot):
    await bot.add_cog(Slots(bot))
