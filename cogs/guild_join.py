import discord
from discord.ext import commands

class GuildJoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a new server"""
        try:
            # 1. Sync Commands to the New Guild
            print(f"Syncing commands for new guild: {guild.name}")
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            print(f"✅ Synced {len(synced)} commands to: {guild.name}")
            
            # 2. Create Private Channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
            
            # Add admin role permissions if they exist
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True)
            
            private_channel = await guild.create_text_channel(
                "scrimhub-private",
                overwrites=overwrites,
                topic="🔒 Private channel for bot updates and announcements"
            )
            
            # Send message in private channel
            await private_channel.send(
                "🔒 **ScrimHub Private Channel**\n\n"
                "This channel is for important bot updates and announcements. "
                "Only admins can see this channel."
            )
            
            # 2. DM the Server Owner
            if guild.owner:
                embed = discord.Embed(
                    title="🎉 Thank you for adding ScrimHub!",
                    description="The Ultimate Free Fire Points Table & Tournament Bot",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Added to:",
                    value=f"**{guild.name}**",
                    inline=False
                )
                
                embed.add_field(
                    name="🚀 Quick Start",
                    value=(
                        "`/setup` - Configure the bot\n"
                        "`/set_branding` - Set your host logo\n"
                        "`/create_scrim` - Start a scrim\n"
                        "`/end_scrim` - Generate Points Table"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="🔥 Key Features",
                    value=(
                        "• Result Tracking - AI-powered screenshot analysis\n"
                        "• Points Table - Beautiful auto-generated tables\n"
                        "• Scrim Management - Easy scrim creation and tracking"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="📱 Mobile Optimized",
                    value="Perfect for Free Fire organizers! All commands work seamlessly on mobile devices.",
                    inline=False
                )
                
                embed.set_footer(text="Use /help to get started")
                
                try:
                    await guild.owner.send(embed=embed)
                except discord.Forbidden:
                    # If we can't DM the owner, send a message in the private channel instead
                    await private_channel.send(
                        f"{guild.owner.mention} - Welcome! I tried to DM you but your DMs are closed. "
                        "Here's your getting started guide:",
                        embed=embed
                    )
            
        except Exception as e:
            print(f"Error in on_guild_join for {guild.name}: {e}")

async def setup(bot):
    await bot.add_cog(GuildJoin(bot))
