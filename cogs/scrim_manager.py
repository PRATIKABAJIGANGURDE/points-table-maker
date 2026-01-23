import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils import is_scrim_admin
import google.generativeai as genai
from config import GEMINI_API_KEY
import aiohttp
import json
import re

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
# Model selection (Flash is faster/cheaper, Pro is better for OCR)
# Strictly prefer 1.5-flash for free tier limits
# Strict Preference: 2.5 Flash
# This has a limit of 20/day, but with 5 keys = 100/day.
# All other models (2.0 Flash, Lite, Exp) returned Limit 0 for this user.
target_model_name = 'models/gemini-2.5-flash'

try:
    available_models = [m.name for m in genai.list_models()]
    if target_model_name not in available_models:
        # Fallback to anything with 'flash' if 2.5 is somehow missing
        if any('flash' in m for m in available_models):
             target_model_name = next(m for m in available_models if 'flash' in m)
except:
    pass
model = genai.GenerativeModel(target_model_name)

class SlotListModal(discord.ui.Modal, title="Paste Slot List"):
    lobby_name = discord.ui.TextInput(label="Lobby Name", placeholder="e.g. 8 PM Scrim", max_length=50)
    slot_text = discord.ui.TextInput(label="Slot List", placeholder="1. Team A\n2. Team B...", style=discord.TextStyle.paragraph, max_length=4000)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        name = self.lobby_name.value
        raw_text = self.slot_text.value
        guild_id = str(interaction.guild.id)

        # Parse slots
        teams_to_insert = []
        lines = raw_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Match "1. TeamName" or "01) TeamName" or just "TeamName" (auto-increment?) 
            # Sticking to explicit numbering for safety, or index if failed.
            match = re.search(r"^(\d+)[\.\)\-\:]\s*(.+)", line)
            if match:
                slot_no = int(match.group(1))
                team_name = match.group(2).strip()
                teams_to_insert.append((slot_no, team_name))
        
        if not teams_to_insert:
            # Fallback: Treat every line as a team, numbered 1..N
            for i, line in enumerate(lines, 1):
                if line.strip():
                    teams_to_insert.append((i, line.strip()))

        if not teams_to_insert:
            return await interaction.followup.send("❌ Could not parse any teams from the list.")

        try:
            # 1. Create Lobby
            lobby_id = db.create_lobby(guild_id, name, max(t[0] for t in teams_to_insert))

            # 2. Insert Teams
            for slot, t_name in teams_to_insert:
                db.create_team(lobby_id, t_name, slot)
            
            summary = "\n".join([f"**S{s}:** {n}" for s, n in teams_to_insert[:10]])
            if len(teams_to_insert) > 10: summary += f"\n...and {len(teams_to_insert)-10} more."
            
            embed = discord.Embed(title=f"✅ Lobby Created: {name}", description=f"**ID:** {lobby_id}\n\n{summary}", color=discord.Color.green())
            embed.set_footer(text="Next: Upload Lobby Screenshots using /upload_lobby_ss")
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

class ScrimManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start_scrim", description="Create a new lobby and paste slot list")
    async def start_scrim(self, interaction: discord.Interaction):
        if not is_scrim_admin(interaction.user):
            return await interaction.response.send_message("No permission.", ephemeral=True)
        await interaction.response.send_modal(SlotListModal())

    @app_commands.command(name="upload_lobby_ss", description="Upload lobby screenshot(s) to map players to teams")
    @app_commands.describe(
        lobby_id="Lobby ID", 
        image1="Lobby Screenshot 1",
        image2="Lobby Screenshot 2 (Optional)",
        image3="Lobby Screenshot 3 (Optional)"
    )
    async def upload_lobby_ss(self, interaction: discord.Interaction, lobby_id: int, image1: discord.Attachment, image2: discord.Attachment = None, image3: discord.Attachment = None):
        if not is_scrim_admin(interaction.user):
            return await interaction.response.send_message("No permission.", ephemeral=True)
            
        images = [img for img in [image1, image2, image3] if img is not None]
        if not images:
            return await interaction.response.send_message("Please upload at least one image.", ephemeral=True)

        for img in images:
            if not img.content_type.startswith("image/"):
                return await interaction.response.send_message(f"Invalid file type: {img.filename}", ephemeral=True)

        await interaction.response.defer(thinking=True)

        # 1. Get Lobby Teams Dictionary (Slot -> ID)
        rows = db.get_teams_in_lobby(lobby_id)
        
        if not rows:
            return await interaction.followup.send("❌ Lobby not found or no teams registered.")
            
        slot_map = {row[0]: {"id": row[1], "name": row[2]} for row in rows}
        
        # 2. Process Images
        async with aiohttp.ClientSession() as session:
            mapped_count = 0
            details = []
            
            prompt = """
            Analyze these Free Fire custom room lobby screenshots (combined).
            Extract the SLOT NUMBER and the PLAYER IGN (In-Game Name) for every player visible across ALL images.

            Rules:
            - The slot number is usually on the left or part of the box (1, 2, 3.. 12).
            - Ignore "Spectators" or non-player slots.
            - Return strictly a single JSON list: [{"slot": 1, "ign": "Name"}, {"slot": 1, "ign": "Name2"}]
            - If a slot has multiple players, list them all with the same slot number.
            - Be precise with IGNs.
            """

            try:
                # Batch Image Processing
                content_parts = [prompt]
                for idx, image in enumerate(images):
                    async with session.get(image.url) as resp:
                        if resp.status == 200:
                            img_data = await resp.read()
                            content_parts.append({
                                "mime_type": image.content_type, 
                                "data": img_data
                            })
                
                # Single API Call with Rotation
                from config import GEMINI_API_KEYS
                
                keys = GEMINI_API_KEYS if isinstance(GEMINI_API_KEYS, list) and GEMINI_API_KEYS else [GEMINI_API_KEY]
                response = None
                last_error = None
                
                for key_index, api_key in enumerate(keys):
                    try:
                        genai.configure(api_key=api_key)
                        current_model = genai.GenerativeModel(target_model_name)
                        response = current_model.generate_content(content_parts)
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        if "429" in str(e) or "Quota" in str(e):
                            continue
                        else:
                            raise e
                
                if last_error: raise last_error
                
                raw_text = response.text.replace("```json", "").replace("```", "").strip()
                if "[" in raw_text and "]" in raw_text:
                    raw_text = raw_text[raw_text.find("["):raw_text.rfind("]")+1]
                else:
                    return await interaction.followup.send("❌ AI failed to find structured data.")
                
                extracted = json.loads(raw_text)
                
                for entry in extracted:
                    slot = entry.get("slot")
                    ign = entry.get("ign")
                    
                    if slot in slot_map and ign:
                        team_id = slot_map[slot]["id"]
                        team_name = slot_map[slot]["name"]
                        
                        # Insert mapping using DB
                        if db.add_team_player(team_id, ign) > 0:
                            mapped_count += 1
                            details.append(f"Slot {slot} ({team_name}) <- {ign}")

            except Exception as e:
                print(f"Error processing images: {e}")
                return await interaction.followup.send(f"⚠️ Error: {e}")

        # No commit needed

        
        # Summary Embed
        embed = discord.Embed(title="📸 Lobby Screenshots Processed", color=discord.Color.blue())
        embed.add_field(name="Images Processed", value=str(len(images)), inline=True)
        embed.add_field(name="Mappings Updated", value=str(mapped_count), inline=True)
        
        preview = "\n".join(details[:15])
        if len(details) > 15: preview += f"\n...and {len(details)-15} more"
        if not preview and mapped_count == 0: preview = "No new players found matching the slots."
        
        embed.description = f"**Mappings Added/Updated:**\n{preview}"
        embed.set_footer(text="You can upload more screenshots if needed.")
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ScrimManager(bot))
