"""
Game Page — main play screen with big launch button, server status, game path.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    COLOR_BG, COLOR_BG_CARD, COLOR_ACCENT, COLOR_ACCENT_HOVER,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_TEXT_MUTED, COLOR_SUCCESS, COLOR_ERROR,
    COLOR_BORDER, GAMES, load_settings, save_settings, STATUS_API_URL,
)
from core.game_launcher import set_realmlist, launch_game, detect_game_path


class GamePage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=COLOR_BG, corner_radius=0)
        self.app = app
        self.settings = load_settings()
        self.game_id = self.settings.get("active_game", "chronos")
        self.game_cfg = GAMES.get(self.game_id, {})

        self._build_ui()
        self._check_game_path()
        self._fetch_server_status()

    def _build_ui(self):
        # --- Title ---
        ctk.CTkLabel(
            self, text=self.game_cfg.get("name", "PLGames"),
            font=ctk.CTkFont("Segoe UI", 28, "bold"),
            text_color=COLOR_ACCENT,
        ).pack(anchor="w", padx=35, pady=(30, 0))

        ctk.CTkLabel(
            self, text=self.game_cfg.get("subtitle", ""),
            font=ctk.CTkFont("Segoe UI", 14),
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=35, pady=(2, 0))

        # --- Info card ---
        card = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=12, border_width=1,
                            border_color=COLOR_BORDER)
        card.pack(fill="x", padx=35, pady=(18, 0))

        ctk.CTkLabel(
            card, text=self.game_cfg.get("description", ""),
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=COLOR_TEXT_DIM, wraplength=550, justify="left",
        ).pack(anchor="w", padx=20, pady=16)

        # --- Server status ---
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.pack(fill="x", padx=35, pady=(16, 0))

        self.status_dot = ctk.CTkLabel(status_frame, text="\u25cf",
                                        font=ctk.CTkFont(size=16),
                                        text_color=COLOR_TEXT_MUTED)
        self.status_dot.pack(side="left")

        self.status_label = ctk.CTkLabel(status_frame, text="  Проверка сервера...",
                                          font=ctk.CTkFont("Segoe UI", 12),
                                          text_color=COLOR_TEXT_DIM)
        self.status_label.pack(side="left")

        self.players_label = ctk.CTkLabel(status_frame, text="",
                                           font=ctk.CTkFont("Segoe UI", 12),
                                           text_color=COLOR_TEXT_DIM)
        self.players_label.pack(side="right")

        # --- Game path ---
        path_card = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=10,
                                 border_width=1, border_color=COLOR_BORDER)
        path_card.pack(fill="x", padx=35, pady=(14, 0))

        path_inner = ctk.CTkFrame(path_card, fg_color="transparent")
        path_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(path_inner, text="Папка с игрой",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=COLOR_TEXT_MUTED).pack(anchor="w")

        path_row = ctk.CTkFrame(path_inner, fg_color="transparent")
        path_row.pack(fill="x", pady=(4, 0))

        game_path = self.settings.get("game_paths", {}).get(self.game_id, "")
        self.path_var = ctk.StringVar(value=game_path if game_path else "Не указана")

        ctk.CTkLabel(path_row, textvariable=self.path_var,
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=COLOR_TEXT).pack(side="left")

        ctk.CTkButton(
            path_row, text="Обзор", width=80, height=30,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=COLOR_BG_SECONDARY, hover_color=COLOR_BORDER,
            text_color=COLOR_TEXT, corner_radius=8,
            command=self._browse_game_path,
        ).pack(side="right")

        # --- Spacer ---
        ctk.CTkFrame(self, fg_color="transparent", height=1).pack(fill="both", expand=True)

        # --- Bottom: launch status + PLAY button ---
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=35, pady=(0, 30))

        self.launch_status = ctk.CTkLabel(bottom, text="",
                                           font=ctk.CTkFont("Segoe UI", 11),
                                           text_color=COLOR_TEXT_DIM)
        self.launch_status.pack(side="left")

        self.btn_play = ctk.CTkButton(
            bottom, text="ИГРАТЬ", width=200, height=52,
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000", corner_radius=12,
            command=self._on_play,
        )
        self.btn_play.pack(side="right")

    def _check_game_path(self):
        game_path = self.settings.get("game_paths", {}).get(self.game_id, "")
        if not game_path or not os.path.isdir(game_path):
            detected = detect_game_path()
            if detected:
                self._set_game_path(detected)

    def _browse_game_path(self):
        path = filedialog.askdirectory(title="Выберите папку с WoW")
        if path:
            exe = self.game_cfg.get("exe_name", "wow.exe")
            wow_exe = os.path.join(path, exe)
            if not os.path.isfile(wow_exe) and not os.path.isfile(wow_exe.replace("wow", "Wow")):
                messagebox.showwarning("Внимание",
                    f"В выбранной папке не найден {exe}.\n"
                    "Убедитесь, что выбрана правильная папка.")
            self._set_game_path(path)

    def _set_game_path(self, path: str):
        if "game_paths" not in self.settings:
            self.settings["game_paths"] = {}
        self.settings["game_paths"][self.game_id] = path
        save_settings(self.settings)
        self.path_var.set(path)

    def _on_play(self):
        game_path = self.settings.get("game_paths", {}).get(self.game_id, "")
        if not game_path or not os.path.isdir(game_path):
            messagebox.showerror("Ошибка", "Укажите папку с игрой через кнопку 'Обзор'.")
            return

        realmlist = self.game_cfg.get("realmlist", "")
        paths = self.game_cfg.get("realmlist_paths", [])
        if realmlist:
            set_realmlist(game_path, realmlist, paths)

        exe = self.game_cfg.get("exe_name", "wow.exe")
        self.launch_status.configure(text="Запуск...", text_color=COLOR_ACCENT)
        self.btn_play.configure(state="disabled")

        def _do():
            ok, err = launch_game(game_path, exe)
            self.after(0, lambda: self._on_launch_result(ok, err))

        threading.Thread(target=_do, daemon=True).start()

    def _on_launch_result(self, ok, err):
        self.btn_play.configure(state="normal")
        if ok:
            self.launch_status.configure(text="Игра запущена!", text_color=COLOR_SUCCESS)
        else:
            self.launch_status.configure(text=err, text_color=COLOR_ERROR)
            messagebox.showerror("Ошибка запуска", err)

    def _fetch_server_status(self):
        def _worker():
            try:
                import requests
                r = requests.get(STATUS_API_URL, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    self.after(0, lambda: self._update_status(data.get("online"), data.get("players", 0)))
                else:
                    self.after(0, lambda: self._update_status(None, "?"))
            except Exception:
                self.after(0, lambda: self._update_status(None, "?"))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_status(self, online, players):
        if online is True:
            self.status_dot.configure(text_color=COLOR_SUCCESS)
            self.status_label.configure(text="  Сервер онлайн", text_color=COLOR_SUCCESS)
            self.players_label.configure(text=f"Игроков: {players}", text_color=COLOR_TEXT)
        elif online is False:
            self.status_dot.configure(text_color=COLOR_ERROR)
            self.status_label.configure(text="  Сервер оффлайн", text_color=COLOR_ERROR)
        else:
            self.status_dot.configure(text_color=COLOR_TEXT_MUTED)
            self.status_label.configure(text="  Статус неизвестен", text_color=COLOR_TEXT_DIM)
