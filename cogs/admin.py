import discord
from discord import app_commands
from discord.ext import commands
from database import db

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configure the scrim bot for this server")
    @app_commands.describe(
        role="The role that will have scrim admin permissions",
        staff_channel="Channel for internal logs and registration alerts",
        results_channel="Channel where final Points Tables will be posted"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, role: discord.Role, staff_channel: discord.TextChannel, results_channel: discord.TextChannel):
        guild_id = str(interaction.guild.id)
        role_id = str(role.id)
        staff_id = str(staff_channel.id)
        results_id = str(results_channel.id)

        # Use DB Manager
        db.upsert_config(guild_id, role_id, staff_id, results_id)

        embed = discord.Embed(
            title="✅ Setup Complete",
            description=(
                f"**Admin Role:** {role.mention}\n"
                f"**Staff Channel:** {staff_channel.mention}\n"
                f"**Results Channel:** {results_channel.mention}\n\n"
                "The bot is now ready for use!"
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sync", description="Sync slash commands for this server (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            # Sync to the current guild for immediate availability
            self.bot.tree.copy_global_to(guild=interaction.guild)
            synced = await self.bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(f"✅ Synced {len(synced)} commands to this server! They should appear immediately.")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to sync: {e}")

    @app_commands.command(name="set_branding", description="Set the Host Name and Logo for the Points Table")
    @app_commands.describe(host_name="Name to display on header", logo="Logo image (PNG/JPG)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_branding(self, interaction: discord.Interaction, host_name: str, logo: discord.Attachment = None):
        guild_id = str(interaction.guild.id)
        
        await interaction.response.defer(ephemeral=True)
        
        # Use DB Manager
        db.update_branding(guild_id, host_name)
        
        # No SQLite connection needed here anymore
        
        msg = f"✅ Host Name set to **{host_name}**."
        
        # Save Logo if provided
        if logo:
            if not logo.content_type.startswith("image/"):
                return await interaction.followup.send("Invalid image format. Please upload PNG or JPG.")
                
            import aiohttp
            import os
            
            # Save to assets/logo_{guild_id}.png
            # Assuming assets folder exists from main.py or image_gen.py context
            save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
                
            save_path = os.path.join(save_dir, f"logo_{guild_id}.png")
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(logo.url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            with open(save_path, "wb") as f:
                                f.write(data)
                            msg += "\n✅ Logo updated successfully!"
                        else:
                            msg += "\n❌ Failed to download logo."
            except Exception as e:
                msg += f"\n❌ Error saving logo: {e}"

        await interaction.followup.send(msg)

    # --- PREFIX COMMANDS FOR ADMIN UTILITIES ---

    @commands.command()
    @commands.is_owner()
    async def sync_global(self, ctx):
        """Syncs all global slash commands."""
        synced = await self.bot.tree.sync()
        await ctx.send(f"✅ Globally synced {len(synced)} commands. (Note: Global sync can take up to 1 hour to reflect everywhere).")

    @commands.command()
    async def sync_guild(self, ctx):
        """Syncs commands to the current guild only (Instant refresh). Usage: !sync_guild"""
        if ctx.author.guild_permissions.administrator:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"✅ Synced {len(synced)} commands specifically to this server! This should refresh your command list instantly.")

    @commands.command()
    async def clear_guild(self, ctx):
        """Clears server-specific commands. Helps fix duplicates! Usage: !clear_guild"""
        if ctx.author.guild_permissions.administrator:
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send("🗑️ Cleared server-specific commands. If you had duplicates, they should be gone now. Only global commands will remain.")

    @commands.command()
    async def reset_commands(self, ctx):
        """NUCLEAR OPTION: Wipes ALL data, Reloads Cogs, and Re-syncs. Usage: !reset_commands"""
        if ctx.author.guild_permissions.administrator:
            msg = await ctx.send("🔄 **Step 1/4:** Wiping Global Commands (Discord)...")
            
            # 1. Clear Global Command State in Tree and Sync "Empty" to Discord
            self.bot.tree.clear_commands(guild=None) 
            await self.bot.tree.sync(guild=None)
            
            await msg.edit(content="🔄 **Step 2/4:** Wiping Guild Commands...")
            # 2. Clear Guild State
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            
            await msg.edit(content="🔄 **Step 3/4:** Reloading Code (Restoring Commands)...")
            # 3. Reload Cogs to restore commands to the Tree
            # We need to find all loaded extensions and reload them
            extensions = list(self.bot.extensions.keys())
            for ext in extensions:
                try:
                    await self.bot.reload_extension(ext)
                except Exception as e:
                    print(f"Failed to reload {ext}: {e}")
            
            await msg.edit(content="🔄 **Step 4/4:** Syncing Fresh Commands to Guild...")
            # 4. Copy Global -> Guild and Sync
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            
            await msg.edit(content=f"✅ **Reset Complete!**\n- Global cmds: Wiped.\n- Server cache: Wiped.\n- Freshly installed: **{len(synced)}** commands.\n(You may need to restart Discord app to see them).")

async def setup(bot):
    await bot.add_cog(Admin(bot))
