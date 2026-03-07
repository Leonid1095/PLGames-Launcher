"""
News Page — scrollable news feed with cards.
"""

import customtkinter as ctk
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    COLOR_BG, COLOR_BG_CARD, COLOR_ACCENT, COLOR_TEXT, COLOR_TEXT_DIM,
    COLOR_TEXT_MUTED, COLOR_SUCCESS, COLOR_ERROR, COLOR_BORDER,
    NEWS_API_URL,
)


class NewsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=COLOR_BG, corner_radius=0)
        self.app = app
        self._build_ui()
        self._load_news()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Новости", font=ctk.CTkFont("Segoe UI", 22, "bold"),
            text_color=COLOR_ACCENT,
        ).pack(anchor="w", padx=35, pady=(25, 12))

        # Scrollable frame
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=COLOR_BG,
                                              scrollbar_button_color=COLOR_BORDER,
                                              scrollbar_button_hover_color=COLOR_ACCENT)
        self.scroll.pack(fill="both", expand=True, padx=35, pady=(0, 15))

        self.loading_label = ctk.CTkLabel(
            self.scroll, text="Загрузка новостей...",
            font=ctk.CTkFont("Segoe UI", 13), text_color=COLOR_TEXT_DIM,
        )
        self.loading_label.pack(pady=20)

    def _load_news(self):
        def _worker():
            items = self._fetch_news()
            self.after(0, lambda: self._render_news(items))

        threading.Thread(target=_worker, daemon=True).start()

    def _fetch_news(self):
        try:
            import requests
            r = requests.get(NEWS_API_URL, timeout=5)
            if r.status_code == 200:
                return r.json().get("news", [])
        except Exception:
            pass

        return [
            {
                "title": "Добро пожаловать в PLGames: Chronos!",
                "text": "Living World сервер WoW 3.3.5a с динамическими событиями, "
                        "караванами, системой поселений и многим другим. "
                        "Присоединяйтесь к нашему сообществу!",
                "date": "2026-03-05",
                "tag": "Анонс",
            },
            {
                "title": "Лаунчер v2.0",
                "text": "Новый лаунчер с поддержкой HD моделей (Gaame Pack), "
                        "настройками графики, проверкой целостности и автообновлениями.",
                "date": "2026-03-05",
                "tag": "Обновление",
            },
            {
                "title": "HD Графика доступна",
                "text": "Включите HD модели персонажей, существ, текстуры и эффекты "
                        "через вкладку Настройки. Каждый патч можно включить/выключить отдельно.",
                "date": "2026-03-05",
                "tag": "Обновление",
            },
        ]

    def _render_news(self, items):
        self.loading_label.destroy()

        if not items:
            ctk.CTkLabel(self.scroll, text="Нет новостей",
                         font=ctk.CTkFont("Segoe UI", 13),
                         text_color=COLOR_TEXT_DIM).pack(pady=20)
            return

        for item in items:
            self._create_card(item)

    def _create_card(self, item):
        card = ctk.CTkFrame(self.scroll, fg_color=COLOR_BG_CARD,
                            corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=(0, 10))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)

        # Top row: tag + date
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        tag = item.get("tag", "")
        if tag:
            tag_colors = {"Анонс": COLOR_ACCENT, "Обновление": COLOR_SUCCESS,
                          "Исправление": COLOR_ERROR}
            ctk.CTkLabel(top, text=tag,
                         font=ctk.CTkFont("Segoe UI", 10, "bold"),
                         text_color="#000000",
                         fg_color=tag_colors.get(tag, COLOR_TEXT_DIM),
                         corner_radius=4, width=0,
                         ).pack(side="left", padx=(0, 8))

        date_str = item.get("date", "")
        if date_str:
            ctk.CTkLabel(top, text=date_str, font=ctk.CTkFont("Segoe UI", 10),
                         text_color=COLOR_TEXT_MUTED).pack(side="right")

        # Title
        ctk.CTkLabel(inner, text=item.get("title", ""),
                     font=ctk.CTkFont("Segoe UI", 15, "bold"),
                     text_color=COLOR_TEXT, anchor="w").pack(fill="x", pady=(6, 2))

        # Body
        ctk.CTkLabel(inner, text=item.get("text", ""),
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=COLOR_TEXT_DIM, anchor="w",
                     wraplength=550, justify="left").pack(fill="x")
