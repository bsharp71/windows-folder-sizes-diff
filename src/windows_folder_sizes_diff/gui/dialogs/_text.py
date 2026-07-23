"""Shared read-only text dialog helpers."""

from __future__ import annotations

import customtkinter as ctk


class ReadOnlyTextDialog(ctk.CTkToplevel):
    """Simple selectable text dialog with a close button."""

    def __init__(self, master, *, title: str, text: str, width: int = 760) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry(f"{width}x520")
        self.minsize(520, 320)
        self.transient(master)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.text_widget = ctk.CTkTextbox(self, wrap="word", font=("Consolas", 12))
        self.text_widget.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="nsew")
        self.text_widget.insert("1.0", text)
        self.text_widget.configure(state="disabled")

        close = ctk.CTkButton(self, text="Close", width=100, command=self.destroy)
        close.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="e")
        close.focus_set()
