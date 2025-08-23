import discord 
import os
from keep_alive import keep_alive
from dotenv import load_dotenv
import asyncio
from discord.ext import commands
from discord import app_commands
from ice import GoogleSheet
from datetime import datetime

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

i = discord.Intents.default()
i.message_content = True
i.members = True  # Activer explicitement l'intent members
bot = commands.Bot(command_prefix='!', intents=i)

google_s = GoogleSheet()

@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronisé avec {len(synced)} commande(s)")
    except Exception as e:
        print(e)

class PlayerSelect(discord.ui.Select):
    def __init__(self, players):
        # Crée les options à partir des noms de joueurs (str)
        options = [discord.SelectOption(label=player, value=player) for player in players if player]
        super().__init__(
            placeholder="Sélectionnez votre nom",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_player = self.values[0]
        embed = discord.Embed(
            title="Type de niveau",
            description="Le niveau que vous avez terminé existe-t-il déjà dans la liste ?",
            color=discord.Color.blue()
        )
        view = LevelTypeView(selected_player)
        await interaction.response.edit_message(embed=embed, view=view)

class RatingModal(discord.ui.Modal, title="Enjoyment & Rating"):
    def __init__(self, player_name, level_name):
        super().__init__()
        self.player_name = player_name  # nom choisi dans le menu déroulant
        self.level_name = level_name

    enjoyment = discord.ui.TextInput(
        label="Enjoyment (1-100)",
        placeholder="Entrez un nombre entre 1 et 100",
        required=True,
        min_length=1,
        max_length=3
    )

    rating = discord.ui.TextInput(
        label="Rating (1-100, facultatif)",
        placeholder="Entrez un nombre entre 1 et 100",
        required=False,
        min_length=1,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            enjoyment = int(self.enjoyment.value)
            rating = int(self.rating.value) if self.rating.value else None
            
            if not (1 <= enjoyment <= 100) or (rating and not (1 <= rating <= 100)):
                raise ValueError("Les valeurs doivent être entre 1 et 100")
            
            google_s.update_enjoyment(self.player_name, self.level_name, enjoyment)
            if rating:
                google_s.update_rating(self.player_name, self.level_name, rating)
            
            await interaction.followup.send(
                f"✅ Ratings enregistrés !\nEnjoyment: {enjoyment}\nRating: {rating if rating else 'Non spécifié'}",
                ephemeral=True
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

class ExtremeDemonView(discord.ui.View):
    def __init__(self, player_name, level_name):
        super().__init__()
        self.player_name = player_name
        self.level_name = level_name

    @discord.ui.button(label="Oui", style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RatingModal(self.player_name, self.level_name)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Non", style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Enregistrement terminé!", ephemeral=True)

class LinkModal(discord.ui.Modal, title="Lien de complétion"):
    def __init__(self, player_name, level_name):
        super().__init__()
        self.player_name = player_name
        self.level_name = level_name

    link = discord.ui.TextInput(
        label="Lien de votre complétion",
        placeholder="Collez le lien YouTube/Twitch de votre complétion ici",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            # Ajouter à l'archive et mettre à jour la completion
            google_s.add_archive(self.player_name, self.level_name, self.link.value)
            google_s.update_completion(self.player_name, self.level_name)
            
            # Obtenir le rang du niveau
            rank = google_s.get_level_rank(self.level_name)
            
            # Envoyer le message dans le salon des complétions
            completions_channel = interaction.guild.get_channel(1395778676544507934)  # Remplacer par l'ID réel du salon
            if completions_channel:
                await completions_channel.send(
                    f"🎉 Félicitations à **{self.player_name}** qui a fini **{self.level_name}** "
                    f"qui est en `{rank}ème` position dans la liste !\n"
                    f"🔗 Lien: {self.link.value}"
                )
            
            embed = discord.Embed(
                title="Ce niveau est-il un Extreme Demon ?",
                color=discord.Color.blue()
            )
            view = ExtremeDemonView(self.player_name, self.level_name)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                f"❌ Erreur lors de l'enregistrement: {str(e)}",
                ephemeral=True
            )

class PaginatedLevelSelect(discord.ui.Select):
    def __init__(self, levels, current_page, player_name):
        self.all_levels = levels
        self.pages = [levels[i:i + 25] for i in range(0, len(levels), 25)]
        self.current_page = current_page
        self.player_name = player_name
        
        options = [discord.SelectOption(label=level, value=level) 
                  for level in self.pages[current_page]]
        super().__init__(placeholder=f"Sélectionnez un niveau (Page {current_page + 1}/{len(self.pages)})", 
                        options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_level = self.values[0]
        modal = LinkModal(self.player_name, selected_level)
        await interaction.response.send_modal(modal)

class PaginatedLevelView(discord.ui.View):
    def __init__(self, levels, player_name):
        super().__init__()
        self.levels = levels
        self.player_name = player_name
        self.current_page = 0
        self.update_select()

    def update_select(self):
        self.clear_items()
        self.add_item(PaginatedLevelSelect(self.levels, self.current_page, self.player_name))
        if len(self.pages) > 1:
            self.add_item(self.previous_button)
            self.add_item(self.next_button)

    @property
    def pages(self):
        return [self.levels[i:i + 25] for i in range(0, len(self.levels), 25)]

    @discord.ui.button(label="Précédent", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.pages)
        self.update_select()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Suivant", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.pages)
        self.update_select()
        await interaction.response.edit_message(view=self)

class ContinueNewLevelView(discord.ui.View):
    def __init__(self, player_name, level_name, placement):
        super().__init__()
        self.player_name = player_name
        self.level_name = level_name
        self.placement = placement

    @discord.ui.button(label="Continuer", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NewLevelLinkModal(self.player_name, self.level_name, self.placement)
        await interaction.response.send_modal(modal)

class NewLevelModal(discord.ui.Modal, title="Nouveau Niveau"):
    def __init__(self, player_name):
        super().__init__()
        self.player_name = player_name

    level_name = discord.ui.TextInput(
        label="Nom du niveau",
        required=True,
        style=discord.TextStyle.short
    )

    placement = discord.ui.TextInput(
        label="Avis sur le placement",
        placeholder="Plus dur que X, moins dur que Y",
        required=True,
        style=discord.TextStyle.long  # Utiliser long pour texte multiligne
    )

    async def on_submit(self, interaction: discord.Interaction):
        view = ContinueNewLevelView(self.player_name, self.level_name.value, self.placement.value)
        await interaction.response.send_message(
            "Cliquez sur Continuer pour ajouter le lien de complétion.",
            view=view,
            ephemeral=True
        )

class NewLevelLinkModal(discord.ui.Modal, title="Lien de complétion"):
    def __init__(self, player_name, level_name, placement):
        super().__init__()
        self.player_name = player_name
        self.level_name = level_name
        self.placement = placement

    link = discord.ui.TextInput(
        label="Lien de votre complétion",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Ce niveau est-il un Extreme Demon ?",
            color=discord.Color.blue()
        )
        view = NewLevelExtremeView(
            self.player_name, 
            self.level_name,
            self.placement,
            self.link.value
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class NewLevelRatingModal(discord.ui.Modal, title="Détails du niveau"):
    def __init__(self, player_name, level_name, placement, link):
        super().__init__()
        self.player_name = player_name  # nom choisi dans le menu déroulant
        self.level_name = level_name
        self.placement = placement
        self.link = link

    enjoyment = discord.ui.TextInput(
        label="Enjoyment (1-100)",
        required=True,
        min_length=1,
        max_length=3
    )

    rating = discord.ui.TextInput(
        label="Rating (1-100, facultatif)",
        required=False,
        min_length=1,
        max_length=3
    )

    comment = discord.ui.TextInput(
        label="Commentaire sur le niveau",
        required=False,
        style=discord.TextStyle.long  # Utiliser long pour texte multiligne
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            enjoyment = int(self.enjoyment.value)
            rating = int(self.rating.value) if self.rating.value else None
            
            if not (1 <= enjoyment <= 100) or (rating and not (1 <= rating <= 100)):
                raise ValueError("Les valeurs doivent être entre 1 et 100")
            
            google_s.add_to_waiting_list(
                self.level_name,
                self.player_name,
                True,
                self.placement,
                self.comment.value,
                enjoyment,
                rating,
                self.link
            )
            
            await interaction.followup.send(
                "✅ Niveau ajouté à la waiting list!",
                ephemeral=True
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

class NewLevelExtremeView(discord.ui.View):
    def __init__(self, player_name, level_name, placement, link):
        super().__init__()
        self.player_name = player_name  # nom choisi dans le menu déroulant
        self.level_name = level_name
        self.placement = placement
        self.link = link

    @discord.ui.button(label="Oui", style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NewLevelRatingModal(
            self.player_name,
            self.level_name,
            self.placement,
            self.link
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Non", style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        google_s.add_to_waiting_list(
            self.level_name,
            self.player_name,
            False,  # is_extreme
            self.placement,
            link=self.link
        )
        try:
            await interaction.response.send_message(
                "✅ Niveau ajouté à la waiting list!", 
                ephemeral=True
            )
        except discord.errors.NotFound:
            await interaction.followup.send(
                "✅ Niveau ajouté à la waiting list!", 
                ephemeral=True
            )

class LevelTypeView(discord.ui.View):
    def __init__(self, player_name):
        super().__init__()
        self.player_name = player_name

    @discord.ui.button(label="Niveau Existant", style=discord.ButtonStyle.primary)
    async def existing_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        levels = google_s.get_levels()
        embed = discord.Embed(
            title="Sélection du niveau",
            description=f"Quel niveau avez-vous terminé, {self.player_name} ?",
            color=discord.Color.blue()
        )
        view = PaginatedLevelView(levels, self.player_name)
        await interaction.response.send_message(embed=embed, view=view)

    @discord.ui.button(label="Nouveau Niveau", style=discord.ButtonStyle.green)
    async def new_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NewLevelModal(self.player_name)
        await interaction.response.send_modal(modal)

class PlayerView(discord.ui.View):
    def __init__(self, players):
        super().__init__()
        self.add_item(PlayerSelect(players))

def has_player_role():
    async def predicate(interaction: discord.Interaction):
        role = interaction.guild.get_role(1366763282244829184)
        if role is None:
            await interaction.response.send_message("❌ Erreur: Rôle non trouvé.", ephemeral=True)
            return False
        if role not in interaction.user.roles:
            await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

@bot.tree.command(name="beat", description="Enregistre un niveau terminé par un joueur")
async def beat(interaction: discord.Interaction):
    players = google_s.get_players()
    embed = discord.Embed(title="Veuillez sélectionner un joueur", color=discord.Color.blue())
    view = PlayerView(players)
    await interaction.response.send_message(embed=embed, view=view)

class ListPaginatedView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.levels = google_s.get_list_details()
        self.current_page = 0
        self.items_per_page = 15

    @property
    def max_pages(self):
        return -(-len(self.levels) // self.items_per_page)  # Ceiling division

    def get_page_content(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_levels = self.levels[start:end]
        
        content = "📊 __Liste des niveaux actuels :__\n\n"
        for i, level in enumerate(page_levels, start=start+1):
            content += f"`{i:02d}.` {level}\n"
        
        return content

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % self.max_pages
        await self.update_message(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % self.max_pages
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Liste Complète des Niveaux",
            description=self.get_page_content(),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"📄 Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="list", description="Affiche la liste des niveaux")
async def list_levels(interaction: discord.Interaction):
    view = ListPaginatedView()
    embed = discord.Embed(
        title="📋 Liste Complète des Niveaux",
        description=view.get_page_content(),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"📄 Page 1/{view.max_pages}")
    await interaction.response.send_message(embed=embed, view=view)

class LovedListView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.levels = google_s.get_loved_list()
        self.current_page = 0
        self.items_per_page = 10

    @property
    def max_pages(self):
        return -(-len(self.levels) // self.items_per_page)

    def get_page_content(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_levels = self.levels[start:end]
        
        content = "❤️ __Les niveaux préférés de la ICE Team:__\n\n"
        for i, (level, enjoyment) in enumerate(page_levels, start=start+1):
            content += f"`{i:02d}.` **{level}**\n💫 Enjoyment: `{enjoyment:.1f}/100`\n"
        
        return content

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % self.max_pages
        await self.update_message(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % self.max_pages
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="❤️ Les Niveaux les Plus Appréciés",
            description=self.get_page_content(),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"📄 Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="lovedlist", description="Affiche les niveaux les plus appréciés")
async def loved_list(interaction: discord.Interaction):
    view = LovedListView()
    embed = discord.Embed(
        title="❤️ Les Niveaux les Plus Appréciés",
        description=view.get_page_content(),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"📄 Page 1/{view.max_pages}")
    await interaction.response.send_message(embed=embed, view=view)

class BestLevelsView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.levels = google_s.get_best_list()
        self.current_page = 0
        self.items_per_page = 10

    @property
    def max_pages(self):
        return -(-len(self.levels) // self.items_per_page)

    def get_page_content(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_levels = self.levels[start:end]
        
        content = "🏆 __Les meilleurs niveaux selon la communauté :__\n\n"
        for i, (level, rating) in enumerate(page_levels, start=start+1):
            content += f"`{i:02d}.` **{level}**\n⭐ Rating: `{rating:.1f}/100`\n"
        
        return content

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % self.max_pages
        await self.update_message(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % self.max_pages
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏆 Les Meilleurs Niveaux",
            description=self.get_page_content(),
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"📄 Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="bestlevels", description="Affiche les niveaux les mieux notés")
async def best_levels(interaction: discord.Interaction):
    view = BestLevelsView()
    embed = discord.Embed(
        title="🏆 Les Meilleurs Niveaux",
        description=view.get_page_content(),
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"📄 Page 1/{view.max_pages}")
    await interaction.response.send_message(embed=embed, view=view)

class PlayerCompletionsView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.levels = []
        self.player_name = ""
        self.current_page = 0
        self.items_per_page = 15

    @property
    def max_pages(self):
        return max(1, -(-len(self.levels) // self.items_per_page))

    def get_page_content(self):
        if not self.levels:
            return "🚫 Ce joueur n'a pas encore terminé de niveau."
            
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_levels = self.levels[start:end]
        
        content = f"🎮 __Niveaux complétés par {self.player_name} :__\n\n"
        for i, level in enumerate(page_levels, start=start+1):
            content += f"`{i:02d}.` **{level}** ✅\n"
        
        total = len(self.levels)
        content += f"\n📊 Total: **{total}** niveau{'x' if total > 1 else ''}"
        
        return content

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.levels:
            self.current_page = (self.current_page - 1) % self.max_pages
            await self.update_message(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.levels:
            self.current_page = (self.current_page + 1) % self.max_pages
            await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"Liste des niveaux de {self.player_name}",
            description=self.get_page_content(),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

class PlayerListSelect(discord.ui.Select):
    def __init__(self, options):
        # options doit être une liste de discord.SelectOption
        super().__init__(
            placeholder="Sélectionnez un joueur",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view = PlayerCompletionsView()
        view.player_name = self.values[0]
        view.levels = google_s.get_player_completions(self.values[0])
        
        embed = discord.Embed(
            title=f"Liste des niveaux de {self.values[0]}",
            description=view.get_page_content(),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Page 1/{view.max_pages}")
        await interaction.response.edit_message(embed=embed, view=view)

class PlayerSelectView(discord.ui.View):
    def __init__(self, players):
        super().__init__()
        options = [discord.SelectOption(label=player, value=player) for player in players if player]
        self.add_item(PlayerListSelect(options))

@bot.tree.command(name="playerlist", description="Affiche la liste des niveaux complétés par un joueur")
async def player_list(interaction: discord.Interaction):
    players = google_s.get_players()
    embed = discord.Embed(
        title="👤 Liste des Niveaux par Joueur",
        description="🎮 Choisissez le joueur dont vous voulez voir la liste des complétions",
        color=discord.Color.green()
    )
    view = PlayerSelectView(players)
    await interaction.response.send_message(embed=embed, view=view)

class LeaderboardView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.leaderboard = google_s.get_leaderboard()
        self.current_page = 0
        self.items_per_page = 10

    @property
    def max_pages(self):
        return max(1, -(-len(self.leaderboard) // self.items_per_page))

    def get_page_content(self):
        if not self.leaderboard:
            return "🏆 Le leaderboard est actuellement vide."
            
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_entries = self.leaderboard[start:end]
        
        content = "🏆 __Classement des Joueurs__\n\n"
        for i, (player, points) in enumerate(page_entries, start=start+1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👑"
            content += f"`#{i:02d}` {medal} **{player}**\n💫 Points: `{points:.2f}`\n"
        
        return content

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.leaderboard:
            self.current_page = (self.current_page - 1) % self.max_pages
            await self.update_message(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.leaderboard:
            self.current_page = (self.current_page + 1) % self.max_pages
            await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏆 Leaderboard",
            description=self.get_page_content(),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"📄 Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="leaderboard", description="Affiche le classement des joueurs")
async def show_leaderboard(interaction: discord.Interaction):
    view = LeaderboardView()
    embed = discord.Embed(
        title="🏆 Leaderboard",
        description=view.get_page_content(),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"📄 Page 1/{view.max_pages}")
    await interaction.response.send_message(embed=embed, view=view)

def in_admin_channel():
    async def predicate(interaction: discord.Interaction):
        if interaction.channel_id != 1373254018805141624:
            await interaction.response.send_message(
                "❌ Cette commande ne peut être utilisée que dans le salon <#1373254018805141624>",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

@bot.tree.command(name="place", description="Place un niveau de la waitinglist dans la liste principale")
@in_admin_channel()
async def place_level(interaction: discord.Interaction):
    # Récupère les niveaux de la waitinglist
    worksheet = google_s.sheet.worksheet("waitinglist")
    levels = worksheet.col_values(1)[1:]  # Colonne A, sans l'en-tête
    levels = [lvl for lvl in levels if lvl]
    if not levels:
        await interaction.response.send_message("Aucun niveau dans la waitinglist.", ephemeral=True)
        return
    view = PlaceLevelView(levels)
    embed = discord.Embed(
        title="Quel niveau veux-tu placer ?",
        description="Sélectionne un niveau à placer dans la liste principale.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class WaitingListLevelSelect(discord.ui.Select):
    def __init__(self, levels):
        options = [discord.SelectOption(label=level, value=level) for level in levels]
        super().__init__(
            placeholder="Sélectionnez le niveau à placer",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PlaceRankModal(self.values[0], interaction.user.display_name))

class PlaceLevelView(discord.ui.View):
    def __init__(self, levels):
        super().__init__()
        self.add_item(WaitingListLevelSelect(levels))

class PlaceRankModal(discord.ui.Modal, title="Placer le niveau"):
    def __init__(self, level_name, player_name):
        super().__init__()
        self.level_name = level_name
        self.player_name = player_name

    rank = discord.ui.TextInput(
        label="Rang dans la liste (1-75)",
        placeholder="Entrez un nombre entre 1 et 75",
        required=True,
        min_length=1,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            rank_int = int(self.rank.value)
            if not (1 <= rank_int <= 75):
                raise ValueError("Le rang doit être entre 1 et 75.")
            
            # Utilise la méthode existante pour effectuer le placement
            google_s.place_level(self.level_name, self.player_name, rank_int)
            
            # Construction du message
            worksheet = google_s.sheet.worksheet("list0")
            levels = worksheet.col_values(1)[1:76]
            idx = rank_int - 1
            above = levels[idx-1] if idx > 0 else None
            below = levels[idx+1] if idx < len(levels) else None
            pushed = levels[-1] if len(levels) == 76 else None

            if rank_int == 1:
                msg = f"⭐ **{self.level_name}** détrône **{below}** et prend la première place de la Ice list !"
            elif rank_int == 75:
                msg = f"⭐ **{self.level_name}** rejoint la dernière place de la Ice list, juste en dessous de **{above}**."
            else:
                msg = (
                    f"⭐ **{self.level_name}** a été placé en position #{rank_int} "
                    f"en dessous de **{above}** et au dessus de **{below}**"
                )
            if pushed:
                msg += f"\n❗ **{pushed}** est poussé hors de la Ice list."

            # Envoi du message dans le salon d'annonce
            try:
                announce_channel = interaction.client.get_channel(1371064624061087886)
                if announce_channel:
                    await announce_channel.send(msg)
                else:
                    print("Channel d'annonce non trouvé!")
                    await interaction.followup.send("⚠️ Erreur: Channel d'annonce non trouvé", ephemeral=True)
            except Exception as channel_error:
                print(f"Erreur lors de l'envoi de l'annonce: {channel_error}")
                await interaction.followup.send(
                    "⚠️ Erreur lors de l'envoi de l'annonce", 
                    ephemeral=True
                )

            await interaction.followup.send(
                f"✅ Niveau **{self.level_name}** placé à la position {rank_int} dans la liste !",
                ephemeral=True
            ) 
        except Exception as e:
            print(f"Erreur lors du placement: {e}")
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

class MoveLevelSelect(discord.ui.Select):
    def __init__(self, levels):
        options = [discord.SelectOption(label=level, value=level) for level in levels]
        super().__init__(
            placeholder="Sélectionnez le niveau à déplacer",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MoveRankModal(self.values[0]))

class MoveLevelView(discord.ui.View):
    def __init__(self, levels):
        super().__init__()
        self.add_item(MoveLevelSelect(levels))

class MoveRankModal(discord.ui.Modal, title="Déplacer le niveau"):
    def __init__(self, level_name):
        super().__init__()
        self.level_name = level_name

    rank = discord.ui.TextInput(
        label="Nouveau rang (1-75)",
        placeholder="Entrez un nombre entre 1 et 75",
        required=True,
        min_length=1,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            new_rank = int(self.rank.value)
            if not (1 <= new_rank <= 75):
                raise ValueError("Le rang doit être entre 1 et 75.")
            
            # Récupérer le rang actuel avant le déplacement
            old_rank = google_s.get_level_rank(self.level_name)
            
            # Effectuer le déplacement
            google_s.move_level(self.level_name, new_rank)
            
            # Récupérer les niveaux adjacents pour le message
            worksheet = google_s.sheet.worksheet("list0")
            levels = worksheet.col_values(1)[1:76]
            above = levels[new_rank-2] if new_rank > 1 else None
            below = levels[new_rank] if new_rank < len(levels) else None

            # Construire le message d'annonce
            direction = "monté" if new_rank < old_rank else "descendu"
            if new_rank == 1:
                msg = f"📊 **{self.level_name}** a été {direction} à la première place, au dessus de **{below}** !"
            elif new_rank == 75:
                msg = f"📊 **{self.level_name}** a été {direction} à la dernière place, en dessous de **{above}** !"
            else:
                msg = f"📊 **{self.level_name}** a été {direction} en position #{new_rank} en dessous de **{above}** et au dessus de **{below}** !"

            # Envoyer l'annonce
            announce_channel = interaction.client.get_channel(1371064624061087886)
            if announce_channel:
                await announce_channel.send(msg)

            await interaction.followup.send(
                f"✅ **{self.level_name}** a été déplacé à la position {new_rank} !",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

@bot.tree.command(name="move", description="Déplace un niveau existant dans la liste")
@in_admin_channel()
async def move_level(interaction: discord.Interaction):
    levels = google_s.get_levels()
    if not levels:
        await interaction.response.send_message("La liste est vide.", ephemeral=True)
        return

    view = MoveLevelView(levels)
    embed = discord.Embed(
        title="Quel niveau voulez-vous déplacer ?",
        description="Sélectionnez un niveau à déplacer dans la liste.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)







if __name__ == "__main__":
    keep_alive()
    bot.run(token)




