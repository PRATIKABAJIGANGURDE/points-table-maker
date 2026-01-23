from database import db
import discord

def get_scrim_admin_role(guild_id: int):
    """Retrieves the scrim admin role ID for a guild."""
    config = db.get_config(guild_id)
    # config: guild_id, role, time, staff, results, reg, host, logo
    if config and config[1]:
        return int(config[1])
    return None

def get_config(guild_id: int):
    """Retrieves the configuration for a guild."""
    config = db.get_config(guild_id)
    if config:
        return {
            "role_id": int(config[1]) if config[1] else None,
            "staff_channel_id": int(config[3]) if config[3] else None,
            "results_channel_id": int(config[4]) if config[4] else None,
            "reg_channel_id": int(config[5]) if config[5] else None
        }
    return None

def is_scrim_admin(member: discord.Member):
    """Checks if a member has the scrim admin role."""
    if member.guild_permissions.administrator:
        return True
        
    role_id = get_scrim_admin_role(member.guild.id)
    if not role_id:
        return False
        
    return any(role.id == role_id for role in member.roles)
