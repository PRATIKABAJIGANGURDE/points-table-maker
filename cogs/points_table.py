import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils import is_scrim_admin, get_config
from image_gen import generate_points_table
from config import PLACEMENT_POINTS, KILL_POINTS
import os

class PointsManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="end_scrim", description="Finalize scrim and generate Points Table")
    @app_commands.describe(lobby_id="The ID of the lobby to end")
    async def end_scrim(self, interaction: discord.Interaction, lobby_id: int):
        if not is_scrim_admin(interaction.user):
            return await interaction.response.send_message("You don't have permission.", ephemeral=True)

        await interaction.response.defer(thinking=True)

        # Get Lobby Name
        lobby_row = db.get_lobby(lobby_id)
        if not lobby_row:
             return await interaction.followup.send("Lobby not found.")
        lobby_name = lobby_row[2] # Index 2 is name

        # Get Stats
        team_rows = db.get_lobby_team_stats(lobby_id)
        
        teams_data = []
        for team_name, team_id, total_kills, matches_played in team_rows:
            total_kills = total_kills or 0
            matches_played = matches_played or 0
            
            # Calculate placement points
            match_positions = db.get_team_match_positions(team_id)
            total_placement_points = sum(PLACEMENT_POINTS.get(pos, 0) for _, pos in match_positions)
            booyahs = sum(1 for _, pos in match_positions if pos == 1)
            
            # Calculate total points
            total_points = (total_kills * KILL_POINTS) + total_placement_points
            
            teams_data.append({
                "team": team_name,
                "matches": matches_played,
                "booyah": booyahs,
                "kills": total_kills,
                "pts": total_points
            })

        # Mark this lobby as COMPLETED
        db.close_lobby(lobby_id)

        # Sort by points
        teams_data.sort(key=lambda x: x['pts'], reverse=True)

        # Generate Image
        # 1. Get Host Name
        config_row = db.get_config(interaction.guild.id)
        # 0:guild_id, 1:role, 2:time, 3:staff, 4:results, 5:reg, 6:host_name, 7:host_logo
        host_name = config_row[6] if config_row and len(config_row) > 6 and config_row[6] else (interaction.guild.name if interaction.guild else "Unknown Host")
        
        # 2. Get Logo URL from DB
        logo_path = config_row[7] if config_row and len(config_row) > 7 else None
        
        # Fallback (optional, logic inside image_gen handles None)

        img_path = generate_points_table(lobby_name, host_name, teams_data, logo_path=logo_path)
        
        # Prepare the embed
        embed = discord.Embed(title=f"🏆 Final Points Table - {lobby_name}", color=discord.Color.gold())
        embed.set_image(url="attachment://points_table.png")

        # Post to results channel if configured
        config = get_config(interaction.guild.id)
        if config and config["results_channel_id"]:
            results_channel = interaction.guild.get_channel(config["results_channel_id"])
            if results_channel:
                file_results = discord.File(img_path, filename="points_table.png")
                await results_channel.send(file=file_results, embed=embed)

        await interaction.followup.send(file=discord.File(img_path, filename="points_table.png"), embed=embed)
        
        # Cleanup
        if os.path.exists(img_path):
            os.remove(img_path)

async def setup(bot):
    await bot.add_cog(PointsManager(bot))
