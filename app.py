"""Desktop GUI for exporting a still frame from a video as JPG or WebP."""

from __future__ import annotations

import base64
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from video_tools import (
    FFmpegError,
    VideoInfo,
    export_frame,
    extract_preview,
    find_ffmpeg,
    format_timestamp,
    parse_timestamp,
    probe_video,
)


BG = "#0b111b"
CARD = "#141d2a"
CARD_ALT = "#101824"
BORDER = "#263448"
TEXT = "#edf3fb"
MUTED = "#9aa9bd"
ACCENT = "#77b5ff"
ACCENT_DARK = "#172e4b"
PREVIEW_BG = "#090f17"

PREVIEW_MAX_WIDTH = 720
PREVIEW_MAX_HEIGHT = 480


class FrameExporterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Vídeo para Imagem HD")
        self.root.geometry("1120x780")
        self.root.minsize(900, 690)
        self.root.configure(background=BG)

        self.ffmpeg_path = find_ffmpeg()
        self.video_path: Path | None = None
        self.video_info: VideoInfo | None = None
        self.preview_photo: tk.PhotoImage | None = None
        self._events: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        self._job_active = False
        self._manual_output = False
        self._busy_controls: list[tuple[ttk.Widget, str]] = []

        self.time_var = tk.StringVar(value="00:00:00.000")
        self.format_var = tk.StringVar(value="JPEG (.jpg)")
        self.quality_var = tk.DoubleVar(value=95)
        self.quality_text_var = tk.StringVar(value="95%")
        self.width_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.preview_time_var = tk.StringVar(value="Nenhum quadro selecionado")
        self.preview_detail_var = tk.StringVar(value="A prévia não reduz a qualidade do arquivo exportado.")

        self._configure_styles()
        self._build_ui()
        self.time_var.trace_add("write", self._on_time_changed)
        self.format_var.trace_add("write", self._on_format_changed)

        if self.ffmpeg_path:
            self._set_status("Pronto. Selecione um vídeo para começar.", "good")
        else:
            self._set_status("FFmpeg não encontrado. Consulte as instruções no README.", "warning")

        self.root.after(80, self._drain_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = ("TkDefaultFont", 10)
        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("CardInner.TFrame", background=CARD_ALT)
        style.configure("Header.TLabel", background=BG, foreground=TEXT, font=("TkDefaultFont", 24, "bold"))
        style.configure("Eyebrow.TLabel", background=BG, foreground=ACCENT, font=("TkDefaultFont", 9, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=default_font)
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=("TkDefaultFont", 12, "bold"))
        style.configure("SectionNumber.TLabel", background=CARD, foreground=ACCENT, font=("TkDefaultFont", 9, "bold"))
        style.configure("Field.TLabel", background=CARD, foreground=TEXT, font=("TkDefaultFont", 9, "bold"))
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("TkDefaultFont", 9))
        style.configure("PreviewTitle.TLabel", background=CARD, foreground=TEXT, font=("TkDefaultFont", 10, "bold"))
        style.configure("PreviewMeta.TLabel", background=CARD, foreground=MUTED, font=("TkDefaultFont", 9))
        style.configure("Badge.TLabel", background=ACCENT_DARK, foreground=ACCENT, padding=(9, 5), font=("TkDefaultFont", 9, "bold"))
        style.configure("Info.TLabel", background=CARD_ALT, foreground=MUTED, padding=(10, 9), font=("TkDefaultFont", 9))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("TkDefaultFont", 9))
        style.configure("StatusGood.TLabel", background=BG, foreground="#80d4ad", font=("TkDefaultFont", 9))
        style.configure("StatusWarning.TLabel", background=BG, foreground="#ffcb7d", font=("TkDefaultFont", 9))

        style.configure(
            "TEntry",
            fieldbackground=CARD_ALT,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(9, 8),
        )
        style.map("TEntry", fieldbackground=[("disabled", "#172130")])
        style.configure(
            "TCombobox",
            fieldbackground=CARD_ALT,
            background=CARD_ALT,
            foreground=TEXT,
            arrowcolor=ACCENT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(8, 7),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", CARD_ALT), ("disabled", "#172130")],
            foreground=[("readonly", TEXT), ("disabled", MUTED)],
            selectbackground=[("readonly", CARD_ALT)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure("TButton", background="#202d3e", foreground=TEXT, padding=(11, 8), bordercolor=BORDER)
        style.map(
            "TButton",
            background=[("disabled", "#202a38"), ("active", "#2b3b51")],
            foreground=[("disabled", "#738196"), ("active", TEXT)],
        )
        style.configure("Primary.TButton", background=ACCENT, foreground="#07111f", font=("TkDefaultFont", 10, "bold"), padding=(13, 11), bordercolor=ACCENT)
        style.map(
            "Primary.TButton",
            background=[("disabled", "#2a3a50"), ("active", "#9ccaff")],
            foreground=[("disabled", "#8798ad"), ("active", "#07111f")],
        )
        style.configure("TScale", background=CARD, troughcolor="#27364a", sliderthickness=14)
        style.configure("TProgressbar", background=ACCENT, troughcolor=CARD, bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=(22, 18, 22, 16))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="FRAME STUDIO  /  EXPORTAÇÃO LOCAL", style="Eyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        ttk.Label(header, text="Vídeo para imagem", style="Header.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(
            header,
            text="Escolha o instante, confira o quadro e exporte em JPG ou WebP.",
            style="Subtitle.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, text="PROCESSAMENTO NO SEU COMPUTADOR", style="Eyebrow.TLabel").grid(
            row=1, column=1, sticky="e", padx=(12, 0)
        )

        content = ttk.Frame(shell, style="App.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, minsize=348)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._build_controls_card(content)
        self._build_preview_card(content)
        self._build_footer(shell)

    def _build_controls_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(17, 15))
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=0)

        self._section_heading(card, 0, "01", "Vídeo")
        self.select_button = ttk.Button(
            card,
            text="＋  Selecionar vídeo",
            style="TButton",
            command=self._select_video,
        )
        self.select_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 7))
        self.video_name_label = ttk.Label(
            card,
            text="Nenhum vídeo selecionado",
            style="Field.TLabel",
            wraplength=300,
            justify="left",
        )
        self.video_name_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 3))
        self.video_detail_label = ttk.Label(
            card,
            text="MP4, MOV, MKV, AVI e outros formatos de vídeo",
            style="Muted.TLabel",
            wraplength=300,
            justify="left",
        )
        self.video_detail_label.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Separator(card).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(14, 12))

        self._section_heading(card, 5, "02", "Quadro")
        ttk.Label(card, text="Instante no vídeo", style="Field.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(11, 6)
        )
        self.time_entry = ttk.Entry(card, textvariable=self.time_var, width=20)
        self.time_entry.grid(row=7, column=0, sticky="ew", padx=(0, 8))
        self.preview_button = ttk.Button(card, text="Pré-visualizar", command=self._preview_clicked)
        self.preview_button.grid(row=7, column=1, sticky="ew")
        self._register_busy_control(self.time_entry)
        self._register_busy_control(self.preview_button)
        ttk.Label(
            card,
            text="Segundos ou HH:MM:SS.mmm  ·  ex.: 00:00:12.500",
            style="Muted.TLabel",
            wraplength=310,
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(5, 0))
        ttk.Separator(card).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(14, 12))

        self._section_heading(card, 10, "03", "Imagem de saída")
        ttk.Label(card, text="Formato", style="Field.TLabel").grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(11, 6)
        )
        self.format_combo = ttk.Combobox(
            card,
            textvariable=self.format_var,
            values=("JPEG (.jpg)", "WebP (.webp)"),
            state="readonly",
        )
        self.format_combo.grid(row=12, column=0, columnspan=2, sticky="ew")
        self._register_busy_control(self.format_combo, restore_state="readonly")

        quality_header = ttk.Frame(card, style="Card.TFrame")
        quality_header.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        quality_header.columnconfigure(0, weight=1)
        ttk.Label(quality_header, text="Qualidade", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(quality_header, textvariable=self.quality_text_var, style="Muted.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        self.quality_scale = ttk.Scale(
            card,
            from_=1,
            to=100,
            variable=self.quality_var,
            command=self._update_quality_text,
        )
        self.quality_scale.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self._register_busy_control(self.quality_scale)

        width_row = ttk.Frame(card, style="Card.TFrame")
        width_row.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(9, 0))
        width_row.columnconfigure(0, weight=1)
        ttk.Label(width_row, text="Largura final (px)", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.width_entry = ttk.Entry(width_row, textvariable=self.width_var, width=11)
        self.width_entry.grid(row=0, column=1, sticky="e")
        self._register_busy_control(self.width_entry)
        ttk.Label(
            card,
            text="Vazio = resolução original. A altura mantém a proporção.",
            style="Muted.TLabel",
            wraplength=310,
        ).grid(row=16, column=0, columnspan=2, sticky="w", pady=(5, 0))

        ttk.Label(card, text="Salvar como", style="Field.TLabel").grid(
            row=17, column=0, columnspan=2, sticky="w", pady=(12, 6)
        )
        self.output_entry = ttk.Entry(card, textvariable=self.output_var)
        self.output_entry.grid(row=18, column=0, sticky="ew", padx=(0, 8))
        self.output_entry.bind("<KeyRelease>", self._mark_output_manual)
        self.output_entry.bind("<<Paste>>", self._mark_output_manual)
        self._register_busy_control(self.output_entry)
        self.output_button = ttk.Button(card, text="Escolher…", command=self._choose_output)
        self.output_button.grid(row=18, column=1, sticky="ew")
        self._register_busy_control(self.output_button)

        self.export_button = ttk.Button(
            card,
            text="Exportar quadro",
            style="Primary.TButton",
            command=self._export_clicked,
        )
        self.export_button.grid(row=19, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        self._register_busy_control(self.select_button)
        self._register_busy_control(self.export_button)

    def _build_preview_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(17, 15))
        card.grid(row=0, column=1, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        heading = ttk.Frame(card, style="Card.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="PRÉ-VISUALIZAÇÃO", style="PreviewTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.resolution_badge = ttk.Label(heading, text="SEM VÍDEO", style="Badge.TLabel")
        self.resolution_badge.grid(row=0, column=1, sticky="e")

        self.preview_stage = tk.Frame(
            card,
            background=PREVIEW_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        )
        self.preview_stage.grid(row=1, column=0, sticky="nsew")
        self.preview_label = tk.Label(
            self.preview_stage,
            text="Escolha um vídeo\npara ver o quadro aqui",
            background=PREVIEW_BG,
            foreground=MUTED,
            font=("TkDefaultFont", 12),
            justify="center",
            padx=20,
            pady=20,
        )
        self.preview_label.pack(fill="both", expand=True)

        meta = ttk.Frame(card, style="Card.TFrame")
        meta.grid(row=2, column=0, sticky="ew", pady=(11, 10))
        meta.columnconfigure(0, weight=1)
        ttk.Label(meta, textvariable=self.preview_time_var, style="PreviewTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(meta, textvariable=self.preview_detail_var, style="PreviewMeta.TLabel").grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Label(
            card,
            text="A exportação usa o quadro original do vídeo — a prévia é apenas uma miniatura.",
            style="Info.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=3, column=0, sticky="ew")

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent, style="App.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="indeterminate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.grid(row=1, column=0, sticky="w")

    @staticmethod
    def _section_heading(parent: ttk.Frame, row: int, number: str, title: str) -> None:
        heading = ttk.Frame(parent, style="Card.TFrame")
        heading.grid(row=row, column=0, columnspan=2, sticky="ew")
        ttk.Label(heading, text=number, style="SectionNumber.TLabel").pack(side="left", padx=(0, 9))
        ttk.Label(heading, text=title, style="CardTitle.TLabel").pack(side="left")

    def _register_busy_control(self, widget: ttk.Widget, restore_state: str = "normal") -> None:
        self._busy_controls.append((widget, restore_state))

    def _set_busy(self, busy: bool) -> None:
        self._job_active = busy
        for widget, restore_state in self._busy_controls:
            widget.configure(state="disabled" if busy else restore_state)
        if busy:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _set_status(self, message: str, tone: str = "normal") -> None:
        self.status_var.set(message)
        style = {
            "good": "StatusGood.TLabel",
            "warning": "StatusWarning.TLabel",
        }.get(tone, "Status.TLabel")
        self.status_label.configure(style=style)

    def _select_video(self) -> None:
        selection = filedialog.askopenfilename(
            parent=self.root,
            title="Selecionar vídeo",
            filetypes=(
                ("Arquivos de vídeo", "*.mp4 *.m4v *.mov *.mkv *.avi *.webm *.mpeg *.mpg *.wmv *.flv *.ts *.mts *.m2ts *.3gp"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        if not selection:
            return

        selected_path = Path(selection).expanduser()
        if not selected_path.is_file():
            messagebox.showerror("Arquivo inválido", "O vídeo selecionado não foi encontrado.", parent=self.root)
            return

        self.video_path = selected_path
        self.video_info = None
        self._manual_output = False
        self.time_var.set("00:00:00.000")
        self.width_var.set("")
        self.video_name_label.configure(text=selected_path.name)
        self.video_detail_label.configure(text="Lendo resolução e duração…")
        self.preview_label.configure(image="", text="Analisando o vídeo…")
        self.preview_photo = None
        self.preview_time_var.set("Aguardando vídeo")
        self.preview_detail_var.set("A resolução original será mantida na exportação.")
        self.resolution_badge.configure(text="ANALISANDO")
        self._refresh_automatic_output()

        if not self.ffmpeg_path:
            self._set_status("FFmpeg não encontrado. Instale as dependências indicadas no README.", "warning")
            messagebox.showerror(
                "FFmpeg necessário",
                "Não encontrei o FFmpeg. Instale as dependências com:\n\n"
                "python -m pip install -r requirements.txt\n\n"
                "Depois, abra o aplicativo novamente.",
                parent=self.root,
            )
            return

        self._set_status("Analisando o vídeo…")
        self._start_job(
            "probe",
            lambda: (selected_path, probe_video(selected_path, self.ffmpeg_path)),
        )

    def _preview_clicked(self) -> None:
        if self.video_path is None:
            messagebox.showwarning("Selecione um vídeo", "Escolha um vídeo antes de pré-visualizar.", parent=self.root)
            return
        if self.video_info is None:
            self._set_status("Aguarde a leitura das informações do vídeo.", "warning")
            return

        try:
            timestamp = parse_timestamp(self.time_var.get())
        except ValueError as exc:
            messagebox.showwarning("Instante inválido", str(exc), parent=self.root)
            return
        if self.video_info.duration is not None and timestamp >= self.video_info.duration:
            messagebox.showwarning(
                "Instante fora do vídeo",
                f"O vídeo tem {format_timestamp(self.video_info.duration)}. Escolha um instante anterior ao final.",
                parent=self.root,
            )
            return

        preview_width = max(320, min(PREVIEW_MAX_WIDTH, self.preview_stage.winfo_width() - 20))
        preview_height = max(220, min(PREVIEW_MAX_HEIGHT, self.preview_stage.winfo_height() - 20))
        if self.preview_stage.winfo_width() <= 1 or self.preview_stage.winfo_height() <= 1:
            preview_width, preview_height = 560, 360

        source = self.video_path
        self.preview_label.configure(image="", text="Extraindo pré-visualização…")
        self.preview_photo = None
        self.preview_time_var.set(f"Quadro em {format_timestamp(timestamp)}")
        self._set_status("Gerando pré-visualização…")
        self._start_job(
            "preview",
            lambda: (
                extract_preview(
                    source,
                    timestamp,
                    self.ffmpeg_path,
                    max_width=preview_width,
                    max_height=preview_height,
                ),
                timestamp,
            ),
        )

    def _export_clicked(self) -> None:
        if self.video_path is None:
            messagebox.showwarning("Selecione um vídeo", "Escolha um vídeo antes de exportar.", parent=self.root)
            return
        if self.video_info is None:
            self._set_status("Aguarde a leitura das informações do vídeo.", "warning")
            return

        try:
            timestamp = parse_timestamp(self.time_var.get())
        except ValueError as exc:
            messagebox.showwarning("Instante inválido", str(exc), parent=self.root)
            return
        if self.video_info.duration is not None and timestamp >= self.video_info.duration:
            messagebox.showwarning(
                "Instante fora do vídeo",
                f"O vídeo tem {format_timestamp(self.video_info.duration)}. Escolha um instante anterior ao final.",
                parent=self.root,
            )
            return

        width_text = self.width_var.get().strip()
        if width_text:
            try:
                output_width = int(width_text)
            except ValueError:
                messagebox.showwarning("Largura inválida", "Informe a largura em pixels usando apenas números.", parent=self.root)
                return
            if not 16 <= output_width <= 32_768:
                messagebox.showwarning(
                    "Largura inválida",
                    "A largura deve estar entre 16 e 32.768 pixels.",
                    parent=self.root,
                )
                return
        else:
            output_width = None

        destination_text = self.output_var.get().strip()
        if not destination_text:
            self._refresh_automatic_output()
            destination_text = self.output_var.get().strip()
        if not destination_text:
            messagebox.showwarning("Escolha onde salvar", "Informe o caminho da imagem de saída.", parent=self.root)
            return

        image_format = self._selected_format_key()
        expected_extension = ".webp" if image_format == "webp" else ".jpg"
        destination = Path(destination_text).expanduser()
        accepted_extensions = {".webp"} if image_format == "webp" else {".jpg", ".jpeg"}
        if destination.suffix.lower() not in accepted_extensions:
            destination = destination.with_suffix(expected_extension)
            self.output_var.set(str(destination))

        overwrite = False
        if destination.exists():
            overwrite = messagebox.askyesno(
                "Substituir arquivo?",
                f"O arquivo já existe:\n{destination}\n\nDeseja substituí-lo?",
                parent=self.root,
            )
            if not overwrite:
                return

        source = self.video_path
        quality = max(1, min(100, int(round(self.quality_var.get()))))
        self._set_status("Exportando o quadro na resolução original…")
        self._start_job(
            "export",
            lambda: export_frame(
                source,
                destination,
                timestamp,
                image_format,
                quality=quality,
                output_width=output_width,
                overwrite=overwrite,
                ffmpeg_path=self.ffmpeg_path,
            ),
        )

    def _choose_output(self) -> None:
        if self.video_path is None:
            messagebox.showwarning("Selecione um vídeo", "Escolha um vídeo antes de definir a imagem de saída.", parent=self.root)
            return

        image_format = self._selected_format_key()
        extension = ".webp" if image_format == "webp" else ".jpg"
        filetype = ("Imagem WebP", "*.webp") if image_format == "webp" else ("Imagem JPEG", "*.jpg *.jpeg")
        current = Path(self.output_var.get()).expanduser() if self.output_var.get().strip() else None
        initial_dir = str(current.parent) if current and current.parent.is_dir() else str(self.video_path.parent)
        initial_file = current.name if current else self.video_path.stem + "_frame" + extension

        selection = filedialog.asksaveasfilename(
            parent=self.root,
            title="Salvar quadro como",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=extension,
            filetypes=(filetype, ("Todos os arquivos", "*.*")),
        )
        if not selection:
            return

        destination = Path(selection).expanduser()
        valid_extensions = {".webp"} if image_format == "webp" else {".jpg", ".jpeg"}
        if destination.suffix.lower() not in valid_extensions:
            destination = destination.with_suffix(extension)
        self._manual_output = True
        self.output_var.set(str(destination))

    def _start_job(self, kind: str, operation: Callable[[], Any]) -> None:
        if self._job_active:
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:  # Report worker failures on Tk's main thread.
                self._events.put(("error", kind, exc))
            else:
                self._events.put(("success", kind, result))

        threading.Thread(target=worker, name=f"frame-export-{kind}", daemon=True).start()

    def _drain_events(self) -> None:
        try:
            while True:
                event, kind, result = self._events.get_nowait()
                self._set_busy(False)
                if event == "error":
                    self._handle_job_error(kind, result)
                else:
                    self._handle_job_success(kind, result)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _handle_job_error(self, kind: str, error: Exception) -> None:
        message = str(error)
        self._set_status("Não foi possível concluir a operação.", "warning")
        if kind == "probe":
            self.video_info = None
            self.video_detail_label.configure(text="Não foi possível ler este vídeo.")
            self.resolution_badge.configure(text="ERRO")
        elif kind == "preview":
            self.preview_label.configure(image="", text="Não foi possível mostrar este quadro")
            self.preview_photo = None
        messagebox.showerror("Erro", message, parent=self.root)

    def _handle_job_success(self, kind: str, result: Any) -> None:
        if kind == "probe":
            path, info = result
            self.video_info = info
            duration_text = format_timestamp(info.duration) if info.duration is not None else "duração desconhecida"
            fps_text = f"  ·  {info.fps:g} fps" if info.fps is not None else ""
            self.video_detail_label.configure(
                text=f"{info.width:,} × {info.height:,} px  ·  {duration_text}{fps_text}"
            )
            self.resolution_badge.configure(text=f"{info.width} × {info.height}")
            self.preview_detail_var.set(f"Resolução original: {info.width} × {info.height} px")
            self._set_status(f"Vídeo carregado: {path.name}", "good")
            self._preview_clicked()
        elif kind == "preview":
            ppm_data, timestamp = result
            try:
                photo = tk.PhotoImage(data=base64.b64encode(ppm_data).decode("ascii"))
            except tk.TclError as exc:
                self._handle_job_error("preview", FFmpegError(f"Não foi possível abrir a miniatura:\n{exc}"))
                return
            self.preview_photo = photo
            self.preview_label.configure(image=photo, text="")
            self.preview_time_var.set(f"Quadro em {format_timestamp(timestamp)}")
            if self.video_info:
                self.preview_detail_var.set(
                    f"Vídeo: {self.video_info.width} × {self.video_info.height} px  ·  Prévia reduzida"
                )
            self._set_status("Pré-visualização pronta. Ajuste as opções e exporte.", "good")
        elif kind == "export":
            destination = Path(result)
            self._set_status(f"Imagem salva: {destination}", "good")
            messagebox.showinfo(
                "Exportação concluída",
                f"O quadro foi salvo com sucesso em:\n\n{destination}",
                parent=self.root,
            )

    def _on_time_changed(self, *_: object) -> None:
        if self.video_path is not None and not self._manual_output:
            self._refresh_automatic_output()

    def _on_format_changed(self, *_: object) -> None:
        if not hasattr(self, "output_var"):
            return
        if self._manual_output and self.output_var.get().strip():
            destination = Path(self.output_var.get()).expanduser()
            extension = ".webp" if self._selected_format_key() == "webp" else ".jpg"
            if destination.suffix.lower() != extension and not (
                extension == ".jpg" and destination.suffix.lower() == ".jpeg"
            ):
                destination = destination.with_suffix(extension)
                self.output_var.set(str(destination))
        elif self.video_path is not None:
            self._refresh_automatic_output()

    def _refresh_automatic_output(self) -> None:
        if self.video_path is None:
            return
        if self._manual_output:
            return
        try:
            stamp = format_timestamp(parse_timestamp(self.time_var.get()))
            stamp = stamp.replace(":", "-").replace(".", "-")
        except ValueError:
            stamp = "quadro"
        extension = ".webp" if self._selected_format_key() == "webp" else ".jpg"
        filename = f"{self.video_path.stem}_frame_{stamp}{extension}"
        self.output_var.set(str(self.video_path.with_name(filename)))

    def _mark_output_manual(self, _event: object = None) -> None:
        self._manual_output = True

    def _selected_format_key(self) -> str:
        return "webp" if self.format_var.get().lower().startswith("webp") else "jpeg"

    def _update_quality_text(self, value: str) -> None:
        self.quality_text_var.set(f"{int(round(float(value)))}%")


if __name__ == "__main__":
    root = tk.Tk()
    app = FrameExporterApp(root)
    root.mainloop()
