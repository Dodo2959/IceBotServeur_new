import os, json
from dotenv import load_dotenv
from operator import add
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

load_dotenv() 

# Constantes
SHEET_ID = "1xyQKMbJ0Sv1EZajQMXAOQOG49o-oyPYfXUlUy65Sr7k"
TABS = {
    "MAIN": "list0",
    "ARCHIVE": "archive",
    "LE": "LE",
    "LR": "LR",
    "WAITING": "waitinglist",
    "LX": "LX",
    "PLAYERS_LIST": "Players Lists",
    "LEADERBOARD": "Leaderboard"
}

class GoogleSheet:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets']
        self.service_account_info = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
        self.credentials = Credentials.from_service_account_info(self.service_account_info, scopes=self.scopes)
        self.client = gspread.authorize(self.credentials)
        self.sheet = self.client.open_by_key(SHEET_ID)

    def get_ws(self, name):
        return self.sheet.worksheet(TABS[name])

    def get_players(self):
        return self.get_ws("MAIN").row_values(1)

    def get_levels(self):
        return self.get_ws("MAIN").col_values(1)[1:76]

    def normalize_level_name(self, level_name):
        """Normalise le nom du niveau (supprime les espaces en trop et convertit en minuscules)"""
        return ' '.join(level_name.lower().split())

    def get_level_rank(self, level_name):
        try:
            levels = self.get_ws("MAIN").col_values(1)
            normalized_name = self.normalize_level_name(level_name)
            for idx, level in enumerate(levels):
                if self.normalize_level_name(level) == normalized_name:
                    return idx
            return None
        except ValueError:
            return None

    def get_level_verifier(self, level_name):
        """Trouve le verifier d'un niveau en cherchant l'étoile ⭐ dans list0"""
        try:
            ws = self.get_ws("MAIN")
            normalized_name = self.normalize_level_name(level_name)
            levels = ws.col_values(1)
            players = ws.row_values(1)
            
            # Trouver la ligne du niveau
            level_row = None
            for idx, level in enumerate(levels):
                if self.normalize_level_name(level) == normalized_name:
                    level_row = idx + 1
                    break
                    
            if level_row is None:
                return "Inconnu"
                
            # Récupérer toute la ligne du niveau
            row_data = ws.row_values(level_row)
            
            # Chercher l'étoile ⭐
            for idx, cell in enumerate(row_data[1:], start=1):
                if cell == "⭐":
                    return players[idx]
                    
            return "Inconnu"
        except Exception:
            return "Inconnu"

    def add_archive(self, player_name, level_name, link):
        rank = self.get_level_rank(level_name)
        date = datetime.now().strftime("%d/%m/%Y")
        new_row = ["beat", player_name, level_name, rank, link, date]
        self.get_ws("ARCHIVE").insert_row(new_row, 2)

    def update_cell(self, tab, row, col, value):
        ws = self.get_ws(tab)
        cell = gspread.utils.rowcol_to_a1(row, col)
        ws.update(cell, [[value]], value_input_option="USER_ENTERED")

    def update_completion(self, player_name, level_name):
        ws = self.get_ws("MAIN")
        players = ws.row_values(1)
        levels = ws.col_values(1)
        try:
            player_col = players.index(player_name) + 1
            level_row = levels.index(level_name) + 1
            self.update_cell("MAIN", level_row, player_col, "✔")
        except ValueError:
            pass

    def update_enjoyment(self, player_name, level_name, enjoyment):
        self._update_stat("LE", player_name, level_name, enjoyment)

    def update_rating(self, player_name, level_name, rating):
        if rating:
            self._update_stat("LR", player_name, level_name, rating)

    def _update_stat(self, tab, player_name, level_name, value):
        ws = self.get_ws(tab)
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            level_row = ws.col_values(1).index(level_name) + 1
            # Utilisation de update avec value_input_option
            ws.update(f"{gspread.utils.rowcol_to_a1(level_row, player_col)}", 
                     [[value]], 
                     value_input_option="USER_ENTERED")
        except ValueError:
            pass

    def add_to_waiting_list(self, level_name, player_name, is_extreme, placement_opinion, 
                           comment=None, enjoyment=None, rating=None, link=None):
        date = datetime.now().strftime("%d/%m/%Y")
        new_row = [level_name, player_name, "XD" if is_extreme else "", placement_opinion,
                   comment or "", enjoyment or "", rating or "", link or "", date]
        self.get_ws("WAITING").append_row(new_row)

    def get_list_details(self):
        return self.get_ws("MAIN").col_values(1)[1:76]

    def _get_sorted_list(self, tab, value_col):
        ws = self.get_ws(tab)
        levels = ws.col_values(1)[1:]
        values = ws.col_values(value_col)[1:]
        data = []
        for level, val in zip(levels, values):
            if val:
                try:
                    data.append((level, float(val)))
                except ValueError:
                    continue
        return sorted(data, key=lambda x: x[1], reverse=True)

    def get_loved_list(self):
        return self._get_sorted_list("LE", 2)

    def get_best_list(self):
        return self._get_sorted_list("LR", 2)

    def get_player_completions(self, player_name):
        try:
            ws = self.get_ws("PLAYERS_LIST")
            player_col = ws.row_values(1).index(player_name) + 1
            return [lvl for lvl in ws.col_values(player_col)[1:] if lvl]
        except ValueError:
            return []

    def get_leaderboard(self):
        try:
            ws = self.get_ws("LEADERBOARD")
            players = ws.col_values(2)[1:]
            points = ws.col_values(3)[1:]
            data = []
            for p, pt in zip(players, points):
                if p and pt:
                    try:
                        data.append((p, float(pt)))
                    except ValueError:
                        continue
            return sorted(data, key=lambda x: x[1], reverse=True)
        except Exception:
            return []

    def place_level(self, level_name, player_name, rank):
        waiting_ws = self.get_ws("WAITING")
        waiting_rows = waiting_ws.get_all_values()[1:]
        row_idx, row_data = None, None
        for idx, row in enumerate(waiting_rows):
            if row and row[0] == level_name:
                row_idx, row_data = idx + 2, row
                break
#view
        first_victor = row_data[1] if row_data and len(row_data) > 1 else player_name

        # Insertion dans la liste principale
        self._insert_into_list("MAIN", level_name, first_victor, rank, mark="⭐")
        
        # Si c'est un extreme demon (XD dans la colonne 3)
        if row_data and len(row_data) > 2 and row_data[2] == "XD":
            # Ajout dans la liste des extremes
            self.get_ws("LX").insert_row([level_name, first_victor, row_data[4] if len(row_data) > 4 else "", row_data[7] if len(row_data) > 7 else ""], rank + 1)
            
            # Ajout de l'enjoyment si disponible
            if row_data and len(row_data) > 5 and row_data[5]:
                self._insert_into_list("LE", level_name, first_victor, rank, mark=row_data[5])
            
            # Ajout du rating si disponible
            if row_data and len(row_data) > 6 and row_data[6]:
                self._insert_into_list("LR", level_name, first_victor, rank, mark=row_data[6])

        if row_idx:
            waiting_ws.delete_rows(row_idx)

        self.get_ws("ARCHIVE").insert_row(["Added", first_victor, level_name, rank, row_data[7] if row_data and len(row_data) > 7 else "", datetime.now().strftime("%d/%m/%Y")], 2)

    def _insert_into_list(self, tab, level_name, player_name, rank, mark=""):
        ws = self.get_ws(tab)
        players = ws.row_values(1)
        
        if tab == "MAIN":
            new_row = [level_name] + ["X" for _ in range(104)]
        else:
            new_row = [level_name] + ["" for _ in range(len(players) - 1)]
            
        try:
            col_idx = players.index(player_name)
            new_row[col_idx] = mark
            # Utilisation de value_input_option="USER_ENTERED" pour l'insertion
            ws.insert_row(new_row, rank + 1, value_input_option="USER_ENTERED")
        except ValueError:
            pass

    def move_level(self, level_name, new_rank):
        # Récupérer le rang actuel
        old_rank = self.get_level_rank(level_name)
        if old_rank is None:
            raise ValueError("Niveau non trouvé dans la liste")

        # Pour chaque liste concernée
        for tab in ["MAIN", "LE", "LR", "LX"]:
            ws = self.get_ws(tab)
            levels = ws.col_values(1)
            
            if level_name in levels:
                # Récupérer toute la ligne
                row_idx = levels.index(level_name)
                row_data = ws.row_values(row_idx + 1)
                
                # Supprimer l'ancienne ligne
                ws.delete_rows(row_idx + 1)
                
                # Insérer à la nouvelle position

                ws.insert_row(row_data, new_rank + 1)
                
    def add_player(self, player_name, discord_name):
        try:
            # Liste des feuilles où ajouter le joueur
            sheets = ["MAIN", "LE", "LR"]
            
            # Vérifier si le joueur existe déjà
            main_ws = self.get_ws("MAIN")
            header_row = main_ws.row_values(1)
            if player_name in header_row:
                return False

            # Ajouter dans les feuilles principales
            for sheet_name in sheets:
                ws = self.get_ws(sheet_name)
                header_row = ws.row_values(1)
                empty_col = len(header_row) + 1
                
                # Ajouter le nom du joueur dans l'en-tête
                ws.update(f"{gspread.utils.rowcol_to_a1(1, empty_col)}", 
                         [[player_name]], 
                         value_input_option="USER_ENTERED")
                
                # Si c'est la feuille principale, remplir la colonne avec "X"
                if sheet_name == "MAIN":
                    levels = ws.col_values(1)[1:]
                    cells = [["X"] for _ in range(len(levels))]
                    ws.update(f"{gspread.utils.rowcol_to_a1(2, empty_col)}:{gspread.utils.rowcol_to_a1(len(levels)+1, empty_col)}", 
                             cells,
                             value_input_option="USER_ENTERED")

            # Ajouter dans Players Lists
            players_list_ws = self.sheet.worksheet("Players Lists")
            empty_col = len(players_list_ws.row_values(1)) + 1
            players_list_ws.update(f"{gspread.utils.rowcol_to_a1(1, empty_col)}", 
                                 [[player_name]], 
                                 value_input_option="USER_ENTERED")

            # Ajouter dans infoplayer
            infoplayer_ws = self.sheet.worksheet("infoplayer")
            empty_col = len(infoplayer_ws.row_values(1)) + 1
            infoplayer_ws.update(f"{gspread.utils.rowcol_to_a1(1, empty_col)}", 
                                [[player_name]], 
                                value_input_option="USER_ENTERED")
            infoplayer_ws.update(f"{gspread.utils.rowcol_to_a1(2, empty_col)}", 
                                [[discord_name]], 
                                value_input_option="USER_ENTERED")
            
            return True
            
        except Exception as e:
            print(f"Erreur lors de l'ajout du joueur: {e}")
            return False

    def get_player_from_discord(self, discord_name):
        """Récupère le nom du joueur à partir de son pseudo Discord"""
        try:
            infoplayer_ws = self.sheet.worksheet("infoplayer")
            discord_names = infoplayer_ws.row_values(2)  # Ligne des pseudos Discord
            player_names = infoplayer_ws.row_values(1)   # Ligne des noms de joueurs
            
            # Cherche le pseudo Discord (en minuscules)
            for i, name in enumerate(discord_names):
                if name.lower() == discord_name.lower():
                    return player_names[i]
            return None
        except Exception as e:
            print(f"Erreur lors de la recherche du joueur: {e}")
            return None

    def get_levels_without_rating(self, player_name):
        """Retourne la liste des niveaux où le joueur n'a pas mis de rating"""
        ws = self.get_ws("LR")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            all_levels = ws.col_values(1)[1:]  # Tous les niveaux
            ratings = ws.col_values(player_col)[1:]  # Ratings du joueur
            return [level for level, rating in zip(all_levels, ratings) if not rating and level]
        except ValueError:
            return []

    def get_levels_without_enjoyment(self, player_name):
        """Retourne la liste des niveaux où le joueur n'a pas mis d'enjoyment"""
        ws = self.get_ws("LE")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            all_levels = ws.col_values(1)[1:]  # Tous les niveaux
            enjoyments = ws.col_values(player_col)[1:]  # Enjoyments du joueur
            return [level for level, enj in zip(all_levels, enjoyments) if not enj and level]
        except ValueError:
            return []

    def count_completions(self, level_name):
        """Compte le nombre de joueurs ayant complété un niveau"""
        ws = self.get_ws("MAIN")
        try:
            level_row = ws.col_values(1).index(level_name) + 1
            row_data = ws.row_values(level_row)[1:]  # Ignorer la première colonne (nom du niveau)
            return sum(1 for cell in row_data if cell == "✔")
        except ValueError:
            return 0

    def get_level_average_enjoyment(self, level_name):
        """Calcule l'enjoyment moyen d'un niveau"""
        ws = self.get_ws("LE")
        try:
            level_row = ws.col_values(1).index(level_name) + 1
            row_data = ws.row_values(level_row)[1:]  # Ignorer la première colonne
            values = [float(val) for val in row_data if val and val.replace('.', '').isdigit()]
            return sum(values) / len(values) if values else 0
        except ValueError:
            return 0

    def get_level_average_rating(self, level_name):
        """Calcule le rating moyen d'un niveau"""
        ws = self.get_ws("LR")
        try:
            level_row = ws.col_values(1).index(level_name) + 1
            row_data = ws.row_values(level_row)[1:]  # Ignorer la première colonne
            values = [float(val) for val in row_data if val and val.replace('.', '').isdigit()]
            return sum(values) / len(values) if values else 0
        except ValueError:
            return 0

    def get_level_verifier_and_date(self, level_name):
        """Récupère le verifier et la date d'ajout d'un niveau"""
        try:
            verifier = self.get_level_verifier(level_name)
            archive_ws = self.get_ws("ARCHIVE")
            archive_data = archive_ws.get_all_values()
            normalized_name = self.normalize_level_name(level_name)
            
            # Chercher l'entrée "Added" pour ce niveau
            for row in archive_data:
                if (row and len(row) >= 6 and row[0] == "Added" and 
                    self.normalize_level_name(row[2]) == normalized_name):
                    return verifier, row[5]  # verifier, date
                    
            return verifier, "Date inconnue"
        except Exception:
            return "Inconnu", "Date inconnue"

    def get_player_average_enjoyment(self, player_name):
        """Calcule l'enjoyment moyen donné par un joueur sur tous les niveaux"""
        ws = self.get_ws("LE")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            values = ws.col_values(player_col)[1:]  # Ignorer l'en-tête
            nums = [float(val) for val in values if val and val.replace('.', '').isdigit()]
            return sum(nums) / len(nums) if nums else 0
        except ValueError:
            return 0

    def get_player_average_rating(self, player_name):
        """Calcule le rating moyen donné par un joueur sur tous les niveaux"""
        ws = self.get_ws("LR")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            values = ws.col_values(player_col)[1:]  # Ignorer l'en-tête
            nums = [float(val) for val in values if val and val.replace('.', '').isdigit()]
            return sum(nums) / len(nums) if nums else 0
        except ValueError:
            return 0

    def get_player_rank(self, player_name):
        """Retourne le rang du joueur dans le leaderboard (1 = meilleur)"""
        leaderboard = self.get_leaderboard()
        for idx, (name, _) in enumerate(leaderboard, start=1):
            if name == player_name:
                return idx
        return "N/A"

    def get_player_favorite_level(self, player_name):
        """Retourne le niveau préféré d'un joueur (plus haut enjoyment)"""
        ws = self.get_ws("LE")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            levels = ws.col_values(1)[1:]  # Ignorer l'en-tête
            enjoyments = ws.col_values(player_col)[1:]  # Enjoyments du joueur
            max_enjoyment = 0
            favorite_level = "Aucun"
            
            for level, enjoyment in zip(levels, enjoyments):
                if enjoyment and level:
                    try:
                        enj_value = float(enjoyment)
                        if enj_value > max_enjoyment:
                            max_enjoyment = enj_value
                            favorite_level = level
                    except ValueError:
                        continue
            
            return favorite_level, max_enjoyment
        except ValueError:
            return "Aucun", 0

    def get_player_least_favorite_level(self, player_name):
        """Retourne le niveau le moins apprécié d'un joueur (plus bas enjoyment)"""
        ws = self.get_ws("LE")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            levels = ws.col_values(1)[1:]  # Ignorer l'en-tête
            enjoyments = ws.col_values(player_col)[1:]  # Enjoyments du joueur
            min_enjoyment = 101  # Plus que le maximum possible
            least_favorite = "Aucun"
            
            for level, enjoyment in zip(levels, enjoyments):
                if enjoyment and level:
                    try:
                        enj_value = float(enjoyment)
                        if enj_value < min_enjoyment:
                            min_enjoyment = enj_value
                            least_favorite = level
                    except ValueError:
                        continue
            
            return least_favorite, min_enjoyment
        except ValueError:
            return "Aucun", 0

    def get_player_best_rated_level(self, player_name):
        """Retourne le niveau le mieux noté par un joueur"""
        ws = self.get_ws("LR")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            levels = ws.col_values(1)[1:]  # Ignorer l'en-tête
            ratings = ws.col_values(player_col)[1:]  # Ratings du joueur
            max_rating = 0
            best_level = "Aucun"
            
            for level, rating in zip(levels, ratings):
                if rating and level:
                    try:
                        rate_value = float(rating)
                        if rate_value > max_rating:
                            max_rating = rate_value
                            best_level = level
                    except ValueError:
                        continue
            
            return best_level, max_rating
        except ValueError:
            return "Aucun", 0

    def get_player_worst_rated_level(self, player_name):
        """Retourne le niveau le moins bien noté par un joueur"""
        ws = self.get_ws("LR")
        try:
            player_col = ws.row_values(1).index(player_name) + 1
            levels = ws.col_values(1)[1:]  # Ignorer l'en-tête
            ratings = ws.col_values(player_col)[1:]  # Ratings du joueur
            min_rating = 101  # Plus que le maximum possible
            worst_level = "Aucun"
            
            for level, rating in zip(levels, ratings):
                if rating and level:
                    try:
                        rate_value = float(rating)
                        if rate_value < min_rating:
                            min_rating = rate_value
                            worst_level = level
                    except ValueError:
                        continue
            
            return worst_level, min_rating
        except ValueError:
            return "Aucun", 0
