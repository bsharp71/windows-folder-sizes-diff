"""Theme-aware message and confirmation dialogs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import customtkinter as ctk

MessageKind = Literal["info", "error", "confirm"]


class ThemedMessageDialog(ctk.CTkToplevel):
    """Small modal message dialog that follows the CustomTkinter theme."""

    def __init__(
        self,
        master,
        *,
        title: str,
        message: str,
        kind: MessageKind,
        confirm_label: str = "OK",
        cancel_label: str | None = None,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("440x220")
        self.minsize(360, 180)
        self.transient(master)
        self.resizable(False, False)
        self.result = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(self)
        frame.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        heading = _heading_for_kind(kind, title)
        ctk.CTkLabel(frame, text=heading, font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(14, 6), sticky="w"
        )
        ctk.CTkLabel(frame, text=message, justify="left", wraplength=380, anchor="w").grid(
            row=1, column=0, padx=14, pady=(0, 12), sticky="nsew"
        )

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=2, column=0, padx=14, pady=(0, 14), sticky="e")
        if cancel_label:
            ctk.CTkButton(
                buttons,
                text=cancel_label,
                width=120,
                fg_color="transparent",
                border_width=1,
                text_color=("gray10", "gray90"),
                command=self._cancel,
            ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            buttons,
            text=confirm_label,
            width=150 if cancel_label else 100,
            command=self._confirm,
        ).grid(row=0, column=1 if cancel_label else 0)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(10, self._make_modal)

    def _make_modal(self) -> None:
        self.focus_force()
        self.grab_set()

    def _confirm(self) -> None:
        self.result = True
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.result = False
        self.grab_release()
        self.destroy()


def show_info(master, title: str, message: str) -> None:
    _show_message(master, title=title, message=message, kind="info")


def show_error(master, title: str, message: str) -> None:
    _show_message(master, title=title, message=message, kind="error")


def ask_yes_no(
    master,
    title: str,
    message: str,
    *,
    yes_label: str = "Yes",
    no_label: str = "No",
) -> bool:
    dialog = ThemedMessageDialog(
        master,
        title=title,
        message=message,
        kind="confirm",
        confirm_label=yes_label,
        cancel_label=no_label,
    )
    dialog.wait_window()
    return dialog.result


def _show_message(master, *, title: str, message: str, kind: MessageKind) -> None:
    dialog = ThemedMessageDialog(master, title=title, message=message, kind=kind)
    dialog.wait_window()


def _heading_for_kind(kind: MessageKind, title: str) -> str:
    if kind == "error":
        return "Error"
    if kind == "confirm":
        return title
    return title
