import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

class DatabaseManager:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ Supabase Credentials missing. DB operations will fail.")
            self.supabase = None
        else:
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Connected to Supabase")



    # --- API Methods ---
    
    def get_config(self, guild_id):
        if not self.supabase: return None
        try:
            response = self.supabase.table("server_config").select("*").eq("guild_id", str(guild_id)).execute()
            if response.data:
                d = response.data[0]
                return (
                    d.get('guild_id'),
                    d.get('scrim_admin_role_id'),
                    d.get('timezone'),
                    d.get('staff_channel_id'),
                    d.get('results_channel_id'),
                    d.get('reg_channel_id'),
                    d.get('host_name'),
                    d.get('host_logo')
                )
            return None
        except Exception as e:
            print(f"DB Error get_config: {e}")
            return None

    def upsert_config(self, guild_id, role_id, staff_id, results_id):
        data = {
            "guild_id": str(guild_id),
            "scrim_admin_role_id": str(role_id),
            "staff_channel_id": str(staff_id),
            "results_channel_id": str(results_id)
        }
        self.supabase.table("server_config").upsert(data).execute()

    def update_branding(self, guild_id, host_name, host_logo=None):
        data = {"guild_id": str(guild_id), "host_name": host_name}
        if host_logo:
             data["host_logo"] = host_logo
        self.supabase.table("server_config").upsert(data).execute()

    # --- Lobbies ---

    def create_lobby(self, guild_id, name, max_teams):
        data = {
            "guild_id": str(guild_id),
            "name": name,
            "max_teams": max_teams,
            "state": "ACTIVE"
        }
        res = self.supabase.table("lobbies").insert(data).execute()
        return res.data[0]['id']

    def get_lobby(self, lobby_id):
        res = self.supabase.table("lobbies").select("*").eq("id", lobby_id).execute()
        if res.data:
            d = res.data[0]
            # Map to tuple: id, guild_id, name, state, max_teams, reg_start, match_start, channel_id
            return (
                d['id'], d['guild_id'], d['name'], d['state'], d['max_teams'],
                d.get('reg_start_time'), d.get('match_start_time'), d.get('channel_id')
            )
        return None
    
    def close_lobby(self, lobby_id):
        self.supabase.table("lobbies").update({"state": "COMPLETED"}).eq("id", lobby_id).execute()

    # --- Teams ---

    def create_team(self, lobby_id, team_name, slot_no):
        data = {"lobby_id": lobby_id, "team_name": team_name, "slot_no": slot_no}
        self.supabase.table("teams").insert(data).execute()

    def get_teams_in_lobby(self, lobby_id):
        # Return list of (slot_no, id, team_name)
        res = self.supabase.table("teams").select("slot_no, id, team_name").eq("lobby_id", lobby_id).order("slot_no").execute()
        return [(r['slot_no'], r['id'], r['team_name']) for r in res.data]

    def add_team_player(self, team_id, ign):
        data = {"team_id": team_id, "ign": ign}
        res = self.supabase.table("team_players").upsert(data, on_conflict="team_id, ign").execute()
        return len(res.data)

    def get_team_by_player(self, lobby_id, discord_id):
        # 1. Get IGN from Players
        res_p = self.supabase.table("players").select("ign").eq("discord_id", str(discord_id)).execute()
        if not res_p.data: return None
        ign = res_p.data[0]['ign']
        
        # 2. Get Team from TeamPlayers
        res_t = self.supabase.table("team_players").select("team_id, teams!inner(id, team_name, lobby_id)")\
            .eq("ign", ign).eq("teams.lobby_id", lobby_id).execute()
        
        if res_t.data:
            t = res_t.data[0]['teams']
            return (t['id'], t['team_name'])
        return None

    def get_discord_id_by_ign(self, team_id, ign):
        res = self.supabase.table("players").select("discord_id").eq("ign", ign).execute()
        if res.data:
            return res.data[0]['discord_id']
        return None

    # --- Matches Support Methods ---
    
    def get_lobby_roster(self, lobby_id):
        # Join teams -> team_players
        # Returns [(team_id, ign), ...]
        res = self.supabase.table("team_players").select("team_id, ign, teams!inner(lobby_id)").eq("teams.lobby_id", lobby_id).execute()
        return [(r['team_id'], r['ign']) for r in res.data]

    def get_player_by_ign(self, ign):
        # Returns discord_id
        res = self.supabase.table("players").select("discord_id").ilike("ign", ign).execute() # Case insensitive? ilike
        if res.data:
            return res.data[0]['discord_id']
        return None

    def get_all_players(self):
        # Returns [(discord_id, ign)]
        res = self.supabase.table("players").select("discord_id, ign").execute()
        return [(r['discord_id'], r['ign']) for r in res.data]

    # --- Matches ---

    def create_match(self, guild_id, lobby_id, match_no):
        data = {
            "guild_id": str(guild_id),
            "lobby_id": lobby_id,
            "match_no": match_no,
            "confirmed": 1
        }
        res = self.supabase.table("matches").insert(data).execute()
        return res.data[0]['id']

    def insert_match_result(self, match_id, team_id, ign, discord_id, kills, position):
        data = {
            "match_id": match_id,
            "team_id": team_id,
            "player_ign": ign,
            "player_discord_id": discord_id,
            "kills": kills,
            "position": position
        }
        self.supabase.table("match_results").insert(data).execute()

    def get_match(self, match_id):
        res = self.supabase.table("matches").select("*").eq("id", match_id).execute()
        return res.data[0] if res.data else None

    def get_match_results(self, match_id):
        # Join with teams to get team_name if needed, but for ConfirmationView we mostly need ign, kills, position, team_id
        res = self.supabase.table("match_results").select("team_id, player_ign, kills, position, teams(team_name)").eq("match_id", match_id).execute()
        return res.data

    def delete_match_results(self, match_id):
        self.supabase.table("match_results").delete().eq("match_id", match_id).execute()

    def get_matches_in_lobby(self, lobby_id):
        res = self.supabase.table("matches").select("id, match_no, created_at").eq("lobby_id", lobby_id).order("match_no").execute()
        return res.data



    # --- Player Stats ---

    def get_player_ign(self, discord_id):
        res = self.supabase.table("players").select("ign").eq("discord_id", str(discord_id)).execute()
        return res.data[0]['ign'] if res.data else None
    
    def get_player_stats_summary(self, discord_id, guild_id):
        res = self.supabase.table("player_stats").select("total_kills, booyahs, matches_played").eq("discord_id", str(discord_id)).eq("guild_id", str(guild_id)).execute()
        if res.data:
            d = res.data[0]
            return (d['total_kills'], d['booyahs'], d['matches_played'])
        return None

    def update_player_stats(self, discord_id, guild_id, kills, is_booyah):
        curr = self.get_player_stats_summary(discord_id, guild_id)
        if curr:
            k, b, m = curr
            data = {
                "total_kills": k + kills,
                "booyahs": b + (1 if is_booyah else 0),
                "matches_played": m + 1
            }
            self.supabase.table("player_stats").update(data).eq("discord_id", str(discord_id)).eq("guild_id", str(guild_id)).execute()
        else:
            data = {
                "discord_id": str(discord_id),
                "guild_id": str(guild_id),
                "total_kills": kills,
                "booyahs": 1 if is_booyah else 0,
                "matches_played": 1
            }
            self.supabase.table("player_stats").insert(data).execute()

    # --- Stats Aggregation ---

    def get_lobby_team_stats(self, lobby_id):
        teams = self.get_teams_in_lobby(lobby_id)
        results = []
        for slot, t_id, t_name in teams:
            res = self.supabase.table("match_results").select("kills, match_id").eq("team_id", t_id).execute()
            mr = res.data
            total_kills = sum(r['kills'] for r in mr)
            matches_played = len(set(r['match_id'] for r in mr))
            results.append((t_name, t_id, total_kills, matches_played))
        return results

    def get_team_match_positions(self, team_id):
        res = self.supabase.table("match_results").select("match_id, position").eq("team_id", team_id).execute()
        pos_map = {}
        for r in res.data:
            mid = r['match_id']
            p = r['position']
            if mid not in pos_map or p < pos_map[mid]:
                pos_map[mid] = p
        return list(pos_map.items())

# Singleton Instance
db = DatabaseManager()
