"""Tkinter-based local desktop UI."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from arbomap.app.orchestrator import run_local


def launch_tkinter_app() -> None:
    app = TkApp()
    app.run()


class TkApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("ArboMAP Desktop (Local)")
        self.root.geometry("640x360")

        self.config_path: tk.StringVar = tk.StringVar(
            value="config/default_config.yaml"
        )

        self._build_ui()

    def _build_ui(self) -> None:
        header = tk.Label(
            self.root,
            text="ArboMAP Local Desktop",
            font=("Segoe UI", 14),
        )
        header.pack(pady=(12, 6))

        path_frame = tk.Frame(self.root)
        path_frame.pack(fill="x", padx=16, pady=8)

        path_label = tk.Label(path_frame, text="Config path:")
        path_label.pack(side="left")

        path_entry = tk.Entry(path_frame, textvariable=self.config_path, width=48)
        path_entry.pack(side="left", padx=8)

        browse_btn = tk.Button(path_frame, text="Browse", command=self._browse)
        browse_btn.pack(side="left")

        run_btn = tk.Button(
            self.root,
            text="Run Local Pipeline",
            command=self._run_pipeline,
            width=24,
        )
        run_btn.pack(pady=8)

        self.progress = ttk.Progressbar(
            self.root, mode="indeterminate", length=240
        )
        self.progress.pack(pady=(0, 8))

        self.status_label = tk.Label(
            self.root,
            text="Status: idle",
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=16, pady=(8, 4))

        self.output_text = tk.Text(self.root, height=10, wrap="word")
        self.output_text.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select config YAML",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if path:
            self.config_path.set(path)

    def _run_pipeline(self) -> None:
        config_path = self.config_path.get().strip()
        if not config_path:
            messagebox.showwarning("Missing config", "Please select a config file.")
            return

        self._set_status("running")
        self.progress.start(10)
        self._append_output(f"Running with config: {config_path}")

        thread = threading.Thread(
            target=self._run_pipeline_worker, args=(config_path,), daemon=True
        )
        thread.start()

    def _run_pipeline_worker(self, config_path: str) -> None:
        try:
            result = run_local(config_path)
            summary_lines = [
                f"ID type: {result.id_type}",
                "Inputs:",
            ]
            for key, meta in result.summary.items():
                if "rows" in meta:
                    summary_lines.append(
                        f"- {key}: {meta['rows']} rows, {len(meta['columns'])} columns"
                    )
                else:
                    summary_lines.append(f"- {key}: {meta['value']}")
            self._append_output("\n".join(summary_lines))
            self._set_status("complete")
        except Exception as exc:  # pragma: no cover - UI surfaced
            self._append_output(f"Error: {exc}")
            self._set_status("error")
        finally:
            self._stop_progress()

    def _append_output(self, text: str) -> None:
        def _append() -> None:
            self.output_text.insert("end", text + "\n")
            self.output_text.see("end")

        self.root.after(0, _append)

    def _set_status(self, state: str) -> None:
        def _set() -> None:
            self.status_label.config(text=f"Status: {state}")

        self.root.after(0, _set)

    def _stop_progress(self) -> None:
        def _stop() -> None:
            self.progress.stop()

        self.root.after(0, _stop)

    def run(self) -> None:
        self.root.mainloop()

