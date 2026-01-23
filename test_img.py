from image_gen import generate_points_table
import os

# Sample data for 12 teams to verify full layout
if __name__ == "__main__":
    sample_data = [
        {"team": "Thunder Esports", "matches": 5, "booyah": 2, "kills": 45, "pts": 125},
        {"team": "Phoenix Gaming", "matches": 5, "booyah": 1, "kills": 38, "pts": 108},
        {"team": "Kalahari Warlords", "matches": 5, "booyah": 0, "kills": 32, "pts": 95},
        {"team": "Team Elite", "matches": 5, "booyah": 1, "kills": 30, "pts": 90},
        {"team": "Bermuda Strikers", "matches": 5, "booyah": 0, "kills": 28, "pts": 82},
        {"team": "Alpine Snipers", "matches": 5, "booyah": 1, "kills": 25, "pts": 78},
        {"team": "Nexus Galaxy", "matches": 5, "booyah": 0, "kills": 22, "pts": 70},
        {"team": "Vanguard Gaming", "matches": 5, "booyah": 0, "kills": 20, "pts": 65},
        {"team": "Crimson Vipers", "matches": 5, "booyah": 0, "kills": 18, "pts": 60},
        {"team": "Stealth Ops", "matches": 5, "booyah": 0, "kills": 15, "pts": 55},
        {"team": "Glacier Storm", "matches": 5, "booyah": 0, "kills": 12, "pts": 45},
        {"team": "Iron Legit", "matches": 4, "booyah": 0, "kills": 10, "pts": 40}
    ]
    
    output = generate_points_table(
        lobby_name="PMGC Scrims - Day 3",
        host_name="GamingHub",
        teams_data=sample_data
    )
    print(f"Points table generated: {output}")