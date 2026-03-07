"""
Settings Page — HD patches by category, graphic settings, integrity check.
CustomTkinter version with modern toggles and UI.
"""

import customtkinter as ctk
from tkinter import messagebox
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    COLOR_BG, COLOR_BG_CARD, COLOR_BG_SECONDARY, COLOR_ACCENT, COLOR_ACCENT_HOVER,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_TEXT_MUTED, COLOR_SUCCESS, COLOR_ERROR,
    COLOR_WARNING, COLOR_BORDER,
    GAMES, UPDATE_MANIFEST_URL, load_settings, save_settings,
)
from core.hd_manager import toggle_patch_group, get_patch_status
from core.game_launcher import read_config_wtf, write_config_wtf
from core.updater import UpdateChecker


class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=COLOR_BG, corner_radius=0)
        self.app = app
        self.settings = load_settings()
        self.game_id = self.settings.get("active_game", "chronos")
        self.game_cfg = GAMES.get(self.game_id, {})
        self.game_path = self.settings.get("game_paths", {}).get(self.game_id, "")
        self.hd_vars = {}
        self.graphic_widgets = {}

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Настройки", font=ctk.CTkFont("Segoe UI", 22, "bold"),
            text_color=COLOR_ACCENT,
        ).pack(anchor="w", padx=35, pady=(25, 12))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=COLOR_BG,
                                              scrollbar_button_color=COLOR_BORDER,
                                              scrollbar_button_hover_color=COLOR_ACCENT)
        self.scroll.pack(fill="both", expand=True, padx=35, pady=(0, 15))

        self._build_hd_section()
        self._build_graphics_section()
        self._build_integrity_section()

    # ===================== HD MODELS =====================
    def _build_hd_section(self):
        if not self.game_path or not os.path.isdir(self.game_path):
            card = self._section("HD Графика (Gaame Pack)")
            ctk.CTkLabel(card, text="Укажите папку с игрой на главной странице",
                         font=ctk.CTkFont("Segoe UI", 12),
                         text_color=COLOR_WARNING).pack(anchor="w")
            return

        hd_cfg = self.game_cfg.get("hd_patches", {})
        if not hd_cfg:
            return

        # Group by category
        categories = {}
        for key, cfg in hd_cfg.items():
            cat = cfg.get("category", "Другое")
            categories.setdefault(cat, []).append((key, cfg))

        for cat_name, patches in categories.items():
            card = self._section(cat_name)

            for key, cfg in patches:
                files = cfg.get("files", [])
                folder = cfg.get("folder", "Data")
                status = get_patch_status(self.game_path, files, folder)

                if not status["installed"]:
                    row = ctk.CTkFrame(card, fg_color="transparent")
                    row.pack(fill="x", pady=2)
                    ctk.CTkLabel(row, text=cfg["name"],
                                 font=ctk.CTkFont("Segoe UI", 12),
                                 text_color=COLOR_TEXT_MUTED).pack(side="left")
                    ctk.CTkLabel(row, text="не установлен",
                                 font=ctk.CTkFont("Segoe UI", 10),
                                 text_color=COLOR_TEXT_MUTED).pack(side="right")
                    continue

                size_str = f"{status['total_size_mb']} MB"
                self._add_hd_toggle(card, key, files, folder,
                                    cfg["name"], cfg.get("description", ""),
                                    size_str, status["enabled"])

    def _add_hd_toggle(self, parent, key, files, folder, name, desc, size, enabled):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)

        switch = ctk.CTkSwitch(
            row, text=name,
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=COLOR_TEXT,
            progress_color=COLOR_ACCENT,
            button_color=COLOR_ACCENT if enabled else COLOR_TEXT_MUTED,
            button_hover_color=COLOR_ACCENT_HOVER,
            command=lambda k=key: self._toggle_hd(k),
        )
        if enabled:
            switch.select()
        switch.pack(side="left")

        self.hd_vars[key] = (switch, files, folder)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="right")

        ctk.CTkLabel(info, text=size, font=ctk.CTkFont("Segoe UI", 10),
                     text_color=COLOR_TEXT_MUTED).pack(side="right", padx=(8, 0))

        if desc:
            ctk.CTkLabel(info, text=desc, font=ctk.CTkFont("Segoe UI", 10),
                         text_color=COLOR_TEXT_MUTED).pack(side="right")

    def _toggle_hd(self, key):
        switch, files, folder = self.hd_vars[key]
        enable = bool(switch.get())
        ok, msg = toggle_patch_group(self.game_path, files, enable, folder)
        if not ok:
            messagebox.showerror("Ошибка HD", msg)
            if enable:
                switch.deselect()
            else:
                switch.select()

    # ===================== GRAPHICS =====================
    def _build_graphics_section(self):
        card = self._section("Графика (Config.wtf)")

        if not self.game_path or not os.path.isdir(self.game_path):
            ctk.CTkLabel(card, text="Укажите папку с игрой",
                         font=ctk.CTkFont("Segoe UI", 12),
                         text_color=COLOR_WARNING).pack(anchor="w")
            return

        config = read_config_wtf(self.game_path)
        graphic_defs = self.game_cfg.get("graphic_settings", {})

        for key, defn in graphic_defs.items():
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", pady=4)

            ctk.CTkLabel(row, text=defn["label"], font=ctk.CTkFont("Segoe UI", 12),
                         text_color=COLOR_TEXT, width=220, anchor="w").pack(side="left")

            current = config.get(key, "")
            stype = defn.get("type", "text")

            if stype == "bool":
                switch = ctk.CTkSwitch(row, text="", width=50,
                                       progress_color=COLOR_ACCENT,
                                       button_color=COLOR_ACCENT,
                                       button_hover_color=COLOR_ACCENT_HOVER)
                if current == "1":
                    switch.select()
                switch.pack(side="left")
                self.graphic_widgets[key] = ("bool", switch)

            elif stype in ("choice", "resolution"):
                if stype == "resolution":
                    options = ["800x600", "1024x768", "1280x720", "1280x1024",
                               "1366x768", "1600x900", "1920x1080", "2560x1440"]
                else:
                    options = defn.get("options", [])

                default = current if current in options else (options[0] if options else "")
                combo = ctk.CTkComboBox(
                    row, values=options, width=160, height=30,
                    font=ctk.CTkFont("Segoe UI", 11),
                    fg_color=COLOR_BG_SECONDARY,
                    border_color=COLOR_BORDER,
                    button_color=COLOR_BORDER,
                    button_hover_color=COLOR_ACCENT,
                    dropdown_fg_color=COLOR_BG_CARD,
                    dropdown_hover_color=COLOR_ACCENT,
                    text_color=COLOR_TEXT,
                    state="readonly",
                )
                combo.set(default)
                combo.pack(side="left")
                self.graphic_widgets[key] = ("choice", combo)

        ctk.CTkButton(
            card, text="Сохранить настройки", width=180, height=34,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000", corner_radius=8,
            command=self._save_graphics,
        ).pack(anchor="w", pady=(12, 0))

    def _save_graphics(self):
        new_settings = {}
        for key, (wtype, widget) in self.graphic_widgets.items():
            if wtype == "bool":
                new_settings[key] = "1" if widget.get() else "0"
            else:
                new_settings[key] = widget.get()

        write_config_wtf(self.game_path, new_settings)
        messagebox.showinfo("Графика", "Настройки сохранены в Config.wtf")

    # ===================== INTEGRITY =====================
    def _build_integrity_section(self):
        card = self._section("Проверка целостности")

        self.integrity_status = ctk.CTkLabel(
            card, text="Проверяет файлы игры по манифесту с сервера",
            font=ctk.CTkFont("Segoe UI", 12), text_color=COLOR_TEXT_DIM)
        self.integrity_status.pack(anchor="w")

        self.integrity_progress = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont("Segoe UI", 10),
            text_color=COLOR_TEXT_MUTED)
        self.integrity_progress.pack(anchor="w", pady=(2, 0))

        self.progress_bar = ctk.CTkProgressBar(card, width=400, height=6,
                                                progress_color=COLOR_ACCENT,
                                                fg_color=COLOR_BG_SECONDARY)
        self.progress_bar.set(0)
        self.progress_bar.pack(anchor="w", pady=(8, 0))
        self.progress_bar.pack_forget()  # hidden initially

        self.btn_check = ctk.CTkButton(
            card, text="Проверить файлы", width=160, height=34,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            text_color="#000000", corner_radius=8,
            command=self._run_check,
        )
        self.btn_check.pack(anchor="w", pady=(10, 0))

    def _run_check(self):
        if not self.game_path or not os.path.isdir(self.game_path):
            messagebox.showwarning("Ошибка", "Укажите папку с игрой")
            return

        self.btn_check.configure(state="disabled")
        self.integrity_status.configure(text="Проверка...", text_color=COLOR_ACCENT)
        self.progress_bar.pack(anchor="w", pady=(8, 0))
        self.progress_bar.set(0)

        checker = UpdateChecker(UPDATE_MANIFEST_URL, "")

        def _progress(text, pct):
            self.after(0, lambda: self._update_progress(text, pct))

        checker.set_progress_callback(_progress)

        def _worker():
            results = checker.verify_integrity(self.game_path)
            self.after(0, lambda: self._on_done(results))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_progress(self, text, pct):
        self.integrity_progress.configure(text=text)
        if pct is not None:
            self.progress_bar.set(pct / 100)

    def _on_done(self, results):
        self.btn_check.configure(state="normal")
        self.progress_bar.pack_forget()

        if not results:
            self.integrity_status.configure(
                text="Манифест не найден. Загрузите его с сервера.",
                text_color=COLOR_WARNING)
            return

        ok = sum(1 for r in results if r["status"] == "ok")
        modified = sum(1 for r in results if r["status"] == "modified")
        missing = sum(1 for r in results if r["status"] == "missing")

        if modified == 0 and missing == 0:
            self.integrity_status.configure(
                text=f"Все файлы ({ok}) в порядке!",
                text_color=COLOR_SUCCESS)
        else:
            self.integrity_status.configure(
                text=f"ОК: {ok}  |  Изменено: {modified}  |  Отсутствует: {missing}",
                text_color=COLOR_ERROR if missing else COLOR_WARNING)

    # ===================== HELPERS =====================
    def _section(self, title):
        card = ctk.CTkFrame(self.scroll, fg_color=COLOR_BG_CARD,
                            corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=(0, 12))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)

        ctk.CTkLabel(inner, text=title, font=ctk.CTkFont("Segoe UI", 14, "bold"),
                     text_color=COLOR_ACCENT).pack(anchor="w", pady=(0, 8))

        return inner
