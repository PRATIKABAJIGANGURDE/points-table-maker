import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import json
import google.generativeai as genai
from config import GEMINI_API_KEY
from database import db
from utils import is_scrim_admin, get_config
import aiohttp
import io
import re
import difflib
from collections import defaultdict, Counter

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Dynamic Model Selection
# Fallback to 2.5 Flash as Pro models are rate-limited for this user.
target_model_name = 'models/gemini-2.5-flash'

try:
    available_models = [m.name for m in genai.list_models()]
    if target_model_name not in available_models:
        print(f"⚠️ {target_model_name} not found! Checking alternatives...")
        # Fallback priority: 1.5 Pro -> 2.0 Flash Exp -> 1.5 Flash
        if 'models/gemini-1.5-pro-latest' in available_models:
             target_model_name = 'models/gemini-1.5-pro-latest'
        elif any('gemini-2.0-flash' in m for m in available_models):
             target_model_name = next(m for m in available_models if 'gemini-2.0-flash' in m)
        elif any('flash' in m for m in available_models):
             target_model_name = next(m for m in available_models if 'flash' in m)
except Exception as e:
    print(f"⚠️ Error listing models: {e}")

print(f"🤖 Selected AI Model: {target_model_name}")
model = genai.GenerativeModel(target_model_name)

class ResultValidator:
    """
    Advanced Logic to clean up AI OCR hallucinations and enforce game rules.
    """
    @staticmethod
    def validate_and_correct(raw_data, registered_teams):
        """
        raw_data: List of dicts [{'ign': '...', 'kills': 5, 'position': 1, 'team_name': '...'}, ...]
        registered_teams: List of tuples (team_id, team_name, slot_number)
        
        Returns: List of cleaned player dicts
        """
        cleaned_data = []
        
        # 1. Sanity Filter
        for p in raw_data:
            # Basic Type Conversions
            try:
                p['kills'] = int(p.get('kills', 0))
            except:
                p['kills'] = 0
            
            try:
                p['position'] = int(p.get('position', 99))
            except:
                p['position'] = 99
                
            # Filter Noise
            if not p.get('ign') or len(p['ign']) < 2: continue
            if "Eliminations" in p['ign'] or "Kills" in p['ign']: continue # OCR header artifact
            if p['kills'] < 0 or p['kills'] > 60: p['kills'] = 0 # Implausible
            
            cleaned_data.append(p)
            
        # 2. Team Grouping Correction
        # If we have Rank #1 with 2 players, and Rank #2 with 2 players, but they look like same clan, 
        # usually the AI messed up the rank reading (e.g. 5th player on newline).
        # For now, we trust the AI correctly identifying Rank 1, 2, 3 unless major conflict.
        
        # 3. Fuzzy IGN/Team Matching
        # This is handled during MatchConfirmationView but we can pre-process hints here
        # to ensure consistency.
        
        # Sort by Position then Kills
        cleaned_data.sort(key=lambda x: (x['position'], -x['kills']))
        
        return cleaned_data

class MatchConfirmationView(discord.ui.View):
    def __init__(self, lobby_id, match_no, stats_data, admin_id, existing_match_id=None):
        super().__init__(timeout=None)
        self.lobby_id = lobby_id
        self.match_no = match_no
        self.stats_data = stats_data 
        self.admin_id = admin_id
        self.existing_match_id = existing_match_id


    @discord.ui.button(label="Confirm & Save", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.admin_id:
            return await interaction.response.send_message("Only the admin who submitted can confirm.", ephemeral=True)
            
        await interaction.response.defer()

        # Disable all buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        # Use DB Manager
        match_id = None
        if self.existing_match_id:
             # We are editing an existing match. 
             # Simplest approach: Delete old results and insert new ones using the SAME match_id.
             db.delete_match_results(self.existing_match_id)
             match_id = self.existing_match_id
             # match entry itself remains, we just replaced the detailed results
        else:
             match_id = db.create_match(interaction.guild.id, self.lobby_id, self.match_no)

        # Process each player's result
        print(f"[DEBUG] Confirming match with {len(self.stats_data)} players")


        # Fetch Lobby Teams for Team Name Matching
        lobby_teams_raw = db.get_teams_in_lobby(self.lobby_id) # -> [(slot, id, team_name), ...]
        lobby_team_map = {} # name_lower -> id
        lobby_team_candidates = [] # (id, name) for fuzzy
        
        for _, t_id, t_name in lobby_teams_raw:
            lobby_team_map[t_name.lower()] = t_id
            lobby_team_candidates.append((t_id, t_name))


        # Helper functions
        def normalize_spaced(text):
            if not text: return ""
            text = re.sub(r'[^a-zA-Z0-9]', ' ', text)
            return ' '.join(text.split()).lower()

        def normalize_strict(text):
            if not text: return ""
            return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

        def get_best_fuzzy_match(target, candidates, cutoff=0.8):
            target_strict = normalize_strict(target)
            best_match = None
            best_score = 0
            if len(target_strict) < 3: return None

            for cand_id, cand_ign in candidates:
                cand_strict = normalize_strict(cand_ign)
                if not cand_strict: continue
                score = difflib.SequenceMatcher(None, target_strict, cand_strict).ratio()
                if len(cand_strict) > 3 and (target_strict in cand_strict or cand_strict in target_strict):
                    score = max(score, 0.9)
                if score > best_score and score >= cutoff:
                    best_score = score
                    best_match = (cand_id, cand_ign)
            return best_match[0] if best_match else None

        # PASS 1: Identify players
        processed_players = []
        for player_result in self.stats_data:
            ign = player_result.get('ign')
            kills = player_result.get('kills', 0)
            position = player_result.get('position', 12)
            extracted_team_name = player_result.get('team_name') # New field
            
            if not ign: continue

            discord_id = None
            team_id = None

            # Match against Lobby Roster
            # Match against Lobby Roster
            lobby_players = db.get_lobby_roster(self.lobby_id) 
            
            # --- STRATEGY 1: Match by TEAM NAME (Strongest) ---
            if extracted_team_name:
                # 1. Exact Name
                if extracted_team_name.lower() in lobby_team_map:
                    team_id = lobby_team_map[extracted_team_name.lower()]
                
                # 2. Fuzzy Name
                if not team_id:
                     team_id = get_best_fuzzy_match(extracted_team_name, lobby_team_candidates, cutoff=0.7)

            # --- STRATEGY 2: Match by IGN (Fallback) ---
            if not team_id:
                # 1. Exact
                for tid, tign in lobby_players:
                    if tign.lower() == ign.lower():
                        team_id = tid
                        break
                # 2. Spaced Norm

            if not team_id:
                norm_ign = normalize_spaced(ign)
                for tid, tign in lobby_players:
                    if normalize_spaced(tign) == norm_ign:
                        team_id = tid
                        break
            # 3. Strict Norm
            if not team_id:
                strict_ign = normalize_strict(ign)
                for tid, tign in lobby_players:
                    if normalize_strict(tign) == strict_ign:
                        team_id = tid
                        break
            # 4. Fuzzy
            if not team_id:
                team_id = get_best_fuzzy_match(ign, lobby_players)

            # Match against Discord Users (Fallback)
            if not team_id:
                discord_id = db.get_player_by_ign(ign)
                if discord_id:
                    pass # Got it
                else:
                    all_players = db.get_all_players()
                    norm_ign = normalize_spaced(ign)
                    for pid, pign in all_players:
                        if normalize_spaced(pign) == norm_ign:
                            discord_id = pid
                            break
                    if not discord_id:
                        strict_ign = normalize_strict(ign)
                        for pid, pign in all_players:
                            if normalize_strict(pign) == strict_ign:
                                discord_id = pid
                                break
                    if not discord_id:
                        discord_id = get_best_fuzzy_match(ign, all_players)

                if discord_id:
                    team_row = db.get_team_by_player(self.lobby_id, discord_id)
                    if team_row: team_id = team_row[0]
            
            if team_id and not discord_id:
                d_id = db.get_discord_id_by_ign(team_id, ign)
                if d_id: discord_id = d_id

            processed_players.append({
                'match_id': match_id,
                'ign': ign,
                'discord_id': discord_id,
                'team_id': team_id,
                'kills': kills,
                'position': position
            })

        # PASS 2: Team Inference
        group_map = defaultdict(list)
        for p in processed_players: group_map[p['position']].append(p)
        
        for pos, group in group_map.items():
            found_teams = [p['team_id'] for p in group if p['team_id']]
            if found_teams:
                common_team_id = Counter(found_teams).most_common(1)[0][0]
                for p in group:
                    if not p['team_id']: p['team_id'] = common_team_id

        # PASS 3: Insert
        for p in processed_players:
            ign = p['ign']
            team_id = p['team_id']
            discord_id = p.get('discord_id')
            kills = p['kills']
            position = p['position']

            if team_id:
                db.insert_match_result(match_id, team_id, ign, discord_id, kills, position)
            # else:
            #     # Global stats tracking disabled per user request
            #     pass
        
        
        # No commit/close needed


        await interaction.followup.send(embed=discord.Embed(title=f"✅ Match Confirmed (ID: {match_id})", description="Results saved successfully!", color=discord.Color.green()))

        self.stop()
        config = get_config(interaction.guild.id)
        if config and config["staff_channel_id"]:
            staff_channel = interaction.guild.get_channel(config["staff_channel_id"])
            if staff_channel:
                await staff_channel.send(embed=discord.Embed(
                    title="📊 Match Confirmed",
                    description=f"**Lobby ID:** {self.lobby_id}\n**Match No:** {self.match_no}\n**Match ID:** {match_id}\n**Confirmed By:** {interaction.user.mention}",
                    color=discord.Color.green()
                ))


    @discord.ui.button(label="Edit Results", style=discord.ButtonStyle.gray)
    async def edit_results(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.admin_id:
            return await interaction.response.send_message("Only the admin who submitted can edit.", ephemeral=True)
        await interaction.response.send_message("Select the team (position) you want to edit:", view=TeamSelectView(self, interaction.message), ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.admin_id:
            return await interaction.response.send_message("Only the admin who submitted can reject.", ephemeral=True)
        await interaction.response.send_message("Match submission rejected.", ephemeral=True)
        self.stop()
        
    def update_stats(self, position, new_players):
        print(f"[DEBUG] Updating stats for Pos {position}. Old len: {len(self.stats_data)}")
        self.stats_data = [p for p in self.stats_data if int(p.get('position', 0)) != position]
        self.stats_data.extend(new_players)
        print(f"[DEBUG] New len: {len(self.stats_data)}")

        
    def generate_embed(self):
        embed = discord.Embed(title=f"📊 Match #{self.match_no} Analysis (Edited)", description=f"Found {len(self.stats_data)} unique players.", color=discord.Color.gold())
        embed.set_footer(text="Data has been manually edited. Please verify before confirming.")
        
        position_groups = defaultdict(list)
        for entry in self.stats_data:
            position_groups[int(entry.get('position', 0))].append(entry)
            
        sorted_positions = sorted(position_groups.keys())
        for position in sorted_positions:
            players = position_groups[position]
            players.sort(key=lambda x: x.get('kills', 0), reverse=True)
            player_lines = [f"**{p['ign']}** - {p['kills']} K" for p in players]
            rank_emoji = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else f"#{position}"
            embed.add_field(name=f"{rank_emoji} Position {position}", value="\n".join(player_lines) if player_lines else "No players", inline=True)
        
        if len(sorted_positions) > 25:
            embed.set_footer(text="⚠️ Some teams hidden due to Discord limits. Use Edit to check.")
        return embed

    async def update_embed(self, interaction: discord.Interaction):
        embed = self.generate_embed()
        if interaction.message:
            await interaction.message.edit(embed=embed, view=self)

class TeamSelect(discord.ui.Select):
    def __init__(self, parent_view, original_message):
        self.parent_view = parent_view
        self.original_message = original_message
        
        # Get existing positions
        found_positions = set([int(p.get('position', 0)) for p in self.parent_view.stats_data])
        # Ensure 1-12 are always available for adding missing teams
        all_positions = sorted(list(found_positions.union(set(range(1, 13)))))
        
        options = []
        for pos in all_positions:
            # Mark if it exists or is new
            label = f"Position {pos}"
            if pos in found_positions:
                label += f" ({len([p for p in self.parent_view.stats_data if int(p.get('position', 0)) == pos])} players)"
            else:
                label += " (Add Team)"
                
            options.append(discord.SelectOption(label=label, value=str(pos)))
            if len(options) >= 25: break
        super().__init__(placeholder="Select a position to edit/add...", min_values=1, max_values=1, options=options)


    async def callback(self, interaction: discord.Interaction):
        position = int(self.values[0])
        players = [p for p in self.parent_view.stats_data if int(p.get('position', 0)) == position]
        players.sort(key=lambda x: x.get('kills', 0), reverse=True)
        default_text = ""
        for p in players: default_text += f"{p['ign']} : {p['kills']}\n"
        await interaction.response.send_modal(EditTeamModal(self.parent_view, position, default_text, self.original_message))

class TeamSelectView(discord.ui.View):
    def __init__(self, parent_view, original_message):
        super().__init__(timeout=60)
        self.add_item(TeamSelect(parent_view, original_message))

class EditTeamModal(discord.ui.Modal):
    def __init__(self, parent_view, position, default_text, original_message):
        super().__init__(title=f"Edit Position {position}")
        self.parent_view = parent_view
        self.position = position
        self.original_message = original_message
        self.data_input = discord.ui.TextInput(label="Format: IGN : Kills (One per line)", style=discord.TextStyle.paragraph, default=default_text, required=False, max_length=1000)
        self.add_item(self.data_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_text = self.data_input.value
        new_players = []
        print(f"[DEBUG] EditTeamModal submitted. Raw: {raw_text!r}")

        for line in raw_text.split('\n'):
            line = line.strip()
            if not line: continue
            parts = line.rsplit(':', 1)
            ign = parts[0].strip()
            kills = 0
            if len(parts) > 1:
                try: kills = int(parts[1].strip())
                except: pass
            if ign: new_players.append({"ign": ign, "kills": kills, "position": self.position})
        
        print(f"[DEBUG] New players parsed: {new_players}")
        self.parent_view.update_stats(self.position, new_players)

        try:
            embed = self.parent_view.generate_embed()
            await self.original_message.edit(embed=embed, view=self.parent_view)
            await interaction.response.send_message(f"✅ Position {self.position} updated!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to update message: {e}", ephemeral=True)

class Matches(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="submit_match", description="Submit match result (up to 3 images) for AI processing")
    @app_commands.describe(lobby_id="Lobby ID", match_no="Match Number", image1="Screenshot 1", image2="Screenshot 2 (Optional)", image3="Screenshot 3 (Optional)")
    async def submit_match(self, interaction: discord.Interaction, lobby_id: int, match_no: int, image1: discord.Attachment, image2: discord.Attachment = None, image3: discord.Attachment = None):
        if not is_scrim_admin(interaction.user):
            return await interaction.response.send_message("You don't have permission.", ephemeral=True)

        images = [img for img in [image1, image2, image3] if img is not None]
        if not images:
             return await interaction.response.send_message("Please upload at least one image.", ephemeral=True)

        for img in images:
            if not img.content_type.startswith("image/"):
                return await interaction.response.send_message(f"Invalid file type: {img.filename}", ephemeral=True)

        await interaction.response.defer(thinking=True)

        # Prompt
        # Advanced "Referee" Prompt
        prompt = """
        You are an official Esports Referee. Your job is to DIGITIZE this Free Fire results screenshot with 100% precision.
        
        INSTRUCTIONS:
        1. Read the scoreboard ROW by ROW.
        2. Verify columns: Rank (#), Player Name (IGN), Eliminations/Kills.
        3. Ignore "Assists", "Damage", or "Total Points" columns if present. Focus ONLY on Kills.
        4. CRITICAL: Distinguish between "Total Kills" (Team Kills) and "Individual Kills". 
           - Usually, the Team Header shows Total Kills.
           - The rows below it show Individual Kills.
           - ONLY extract the INDIVIDUAL Kills.
        
        OUTPUT FORMAT:
        Return a strict JSON list of objects.
        [
          {"ign": "Player1", "kills": 5, "position": 1, "team_name": "TeamA"},
          {"ign": "Player2", "kills": 2, "position": 1, "team_name": "TeamA"},
          {"ign": "EnemyX", "kills": 0, "position": 2, "team_name": "TeamB"}
        ]
        
        RULES:
        - "position": The Rank of the TEAM (1, 2, 3...). All players in the same squad get the SAME position.
        - "ign": Exact spelling, case-sensitive. Capture special characters if possible.
        - "kills": Must be a number.
        - If a team has 4 players, output 4 entries with the same "position".
        - Do not hallucinate players not in the image.
        """

        combined_stats = []
        
        try:
            # Batch Image Processing
            content_parts = [prompt]
            async with aiohttp.ClientSession() as session:
                for idx, img in enumerate(images):
                    async with session.get(img.url) as resp:
                        if resp.status == 200:
                            img_data = await resp.read()
                            content_parts.append({
                                "mime_type": img.content_type, 
                                "data": img_data
                            })
            
            # Key Rotation Logic
            from config import GEMINI_API_KEYS
            import random

            # Ensure we have a list
            keys = GEMINI_API_KEYS if isinstance(GEMINI_API_KEYS, list) and GEMINI_API_KEYS else [GEMINI_API_KEY]
            
            response = None
            last_error = None
            
            # Try each key until one works
            for key_index, api_key in enumerate(keys):
                try:
                    # Configure with current key
                    genai.configure(api_key=api_key)
                    current_model = genai.GenerativeModel(target_model_name)
                    
                    print(f"[AI] Attempting with Key #{key_index+1}...")
                    # Offload blocking call to thread
                    # response = current_model.generate_content(content_parts)
                    response = await asyncio.to_thread(current_model.generate_content, content_parts)
                    last_error = None # Success
                    break # Exit loop if successful

                    
                except Exception as e:
                    last_error = e
                    if "429" in str(e) or "Quota" in str(e):
                        print(f"⚠️ Key #{key_index+1} Quota Exceeded. Switching...")
                        continue # Try next key
                    else:
                        raise e # Not a quota error, probably something else
            
            if last_error:
                raise last_error

            raw_text = response.text.replace("```json", "").replace("```", "").strip()
            if "[" in raw_text and "]" in raw_text:
                raw_text = raw_text[raw_text.find("["):raw_text.rfind("]")+1]
            data = json.loads(raw_text)
            
            # --- POST PROCESSING VALIDATOR ---
            # Fetch registered teams strictly for context if needed (future upgrade)
            # For now, apply logic:
            
            cleaned_data = ResultValidator.validate_and_correct(data, [])
            
            for i, p in enumerate(cleaned_data):
                p['img_idx'] = 0 # Dummy index since we batch
                combined_stats.append(p)

        except Exception as e:
            print(f"Error processing images: {e}")
            err_msg = "⚠️ Error processing images. Please check the logs."
            if "429" in str(e) or "Quota" in str(e):
                err_msg = "⚠️ All API Keys have exceeded their quota! Please try again later."
            
            try:
                # Cleaner public error
                await interaction.edit_original_response(content=err_msg, embed=None)
                # Hidden details for the admin
                await interaction.followup.send(f"**Debug Error Details:**\n{e}", ephemeral=True)
            except:
                pass
            return

        # --- DEDUPLICATION LOGIC ---
        position_groups = defaultdict(list)
        for p in combined_stats:
            position_groups[p.get('position', 0)].append(p)
            
        final_stats = []
        for pos, group in position_groups.items():
            unique_team_players = []
            group.sort(key=lambda x: x.get('kills', 0), reverse=True)
            
            # --- DEDUPLICATION DISABLED (User Request) ---
            # We trust the AI extraction and simply sort by kills.
            # We will NOT merge players even if they have the same name.
            unique_team_players = []
            for player in group:
                unique_team_players.append(player)
            
            # Sort by kills descending
            unique_team_players.sort(key=lambda x: x.get('kills', 0), reverse=True)
            
            # Soft cap to prevent massive spam if visualization fails, but lenient (e.g. 8)
            if len(unique_team_players) > 8:
                unique_team_players = unique_team_players[:8]
                
            final_stats.extend(unique_team_players)

            
        combined_stats = final_stats
        
        if not combined_stats:
            return await interaction.followup.send("❌ Failed to extract data.")

        try:
            embed = discord.Embed(title=f"📊 Match #{match_no} Analysis", description=f"Processed {len(images)} image(s). Found {len(combined_stats)} unique players.", color=discord.Color.gold())
            embed.set_footer(text="Please verify the data before confirming.")
            
            position_groups = defaultdict(list)
            for entry in combined_stats:
                position_groups[entry.get('position', 0)].append(entry)
            
            sorted_positions = sorted(position_groups.keys())
            for position in sorted_positions:
                players = position_groups[position]
                player_lines = [f"**{p['ign']}** - {p['kills']} K" for p in players]
                rank_emoji = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else f"#{position}"
                embed.add_field(name=f"{rank_emoji} Position {position}", value="\n".join(player_lines) if player_lines else "No players", inline=True)
            
            if len(sorted_positions) > 25:
                embed.set_footer(text="⚠️ Some teams hidden due to Discord limits. Please verify via Edit.")

            await interaction.followup.send(embed=embed, view=MatchConfirmationView(lobby_id, match_no, combined_stats, interaction.user.id))

        except Exception as e:
            await interaction.followup.send(f"⚠️ Error assembling results. Check hidden logs.", ephemeral=True)
            print(f"Error assembling results: {str(e)}")

    @app_commands.command(name="edit_match", description="Edit a previously confirmed match")
    @app_commands.describe(match_id="The Match ID to edit")
    async def edit_match(self, interaction: discord.Interaction, match_id: int):
        if not is_scrim_admin(interaction.user):
            return await interaction.response.send_message("No permission.", ephemeral=True)
            
        match = db.get_match(match_id)
        if not match:
             return await interaction.response.send_message("Match not found.", ephemeral=True)
             
        # Check guild
        if str(match.get('guild_id')) != str(interaction.guild.id):
             return await interaction.response.send_message("This match belongs to another server.", ephemeral=True)
             
        await interaction.response.defer()
        
        # Get Results
        results = db.get_match_results(match_id)
        
        # Convert to stats_data format
        stats_data = []
        for r in results:
            t_name = None
            if r.get('teams'): t_name = r['teams'].get('team_name')
            
            stats_data.append({
                "ign": r['player_ign'],
                "kills": r['kills'],
                "position": r['position'],
                "team_name": t_name, # Pass existing team name if available
                "team_id": r['team_id'] # Pass existing team_id so we don't need to re-match if not changed? 
                # Actually MatchConfirmation will re-run matching logic usually. 
                # But since we have definitive ID, we might want to leverage it. 
                # However, current Logic relies on 'team_id' being in processed_players.
                # Let's trust the re-matching OR inject it.
            })
            
        lobby_id = match['lobby_id']
        match_no = match['match_no']
        
        embed = discord.Embed(title=f"📝 Editing Match #{match_no}", description=f"Loaded {len(stats_data)} player records.", color=discord.Color.orange())
        embed.set_footer(text="Click 'Edit Results' to modify kills/positions. Confirm to Save changes.")
        
        # We need to construct the embed fully like in submit_match
        # To do that, we need to basically call generate_embed on the view.
        view = MatchConfirmationView(lobby_id, match_no, stats_data, interaction.user.id, existing_match_id=match_id)
        embed = view.generate_embed()
        embed.title = f"📝 Editing Match #{match_no}"
        
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="matches", description="List all confirmed matches in a lobby")
    @app_commands.describe(lobby_id="Lobby ID to view matches for")
    async def list_matches(self, interaction: discord.Interaction, lobby_id: int):
        if not is_scrim_admin(interaction.user):
            return await interaction.response.send_message("No permission.", ephemeral=True)

        matches = db.get_matches_in_lobby(lobby_id)
        if not matches:
             return await interaction.response.send_message(f"No matches found for Lobby {lobby_id}.", ephemeral=True)
        
        desc = ""
        for m in matches:
             desc += f"**Match #{m['match_no']}** - ID: `{m['id']}`\n"
             
        embed = discord.Embed(title=f"📜 Matches in Lobby {lobby_id}", description=desc, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Matches(bot))

