import os, json
from dotenv import load_dotenv
from operator import add
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

load_dotenv() 

# Constantes
SHEET_ID = "1BZuyJzJV1-KOUKwz60C-2tNHmu_uZ0pWxoGDkTGk7Bg"
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

    def get_level_rank(self, level_name):
        try:
            levels = self.get_ws("MAIN").col_values(1)
            return levels.index(level_name)
        except ValueError:
            return None

    def add_archive(self, player_name, level_name, link):
        rank = self.get_level_rank(level_name)
        date = datetime.now().strftime("%d/%m/%Y")
        new_row = ["beat", player_name, level_name, rank, link, date]
        self.get_ws("ARCHIVE").insert_row(new_row, 2)

    def update_cell(self, tab, row, col, value):
        ws = self.get_ws(tab)
        ws.update_cell(row, col, value)

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
            self.update_cell(tab, level_row, player_col, value)
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
        
        # Si c'est la feuille principale (list0) et qu'on ajoute une nouvelle ligne
        if tab == "MAIN":
            new_row = [level_name] + ["X" for _ in range(len(players) - 1)]
        else:
            new_row = [level_name] + ["" for _ in range(len(players) - 1)]
            
        try:
            col_idx = players.index(player_name)
            new_row[col_idx] = mark
        except ValueError:
            pass
        ws.insert_row(new_row, rank + 1)

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
