from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QProgressBar, QPushButton, QRadioButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from resolveprep import config, logs, transcode
from resolveprep.progress import humanise
from resolveprep.queue import Destination, Mode, Status, free_bytes, inspect, required_bytes, resolve
from resolveprep.ui.worker import TranscodeWorker

STATUS_TEXT = {
    Status.READY: "queued",
    Status.DONE: "done",
    Status.FAILED: "failed",
    Status.SKIPPED: "skipped",
}


def _size(count):
    if count is None:
        return "unknown"
    if count >= 1e9:
        return f"{count / 1e9:.1f} GB"
    return f"{count / 1e6:.0f} MB"


class Window(QMainWindow):
    start_requested = Signal(object, str)

    def __init__(self, paths):
        super().__init__()
        self.setWindowTitle("Resolve Prep")
        self.resize(760, 520)
        self._log = logs.get()
        self._settings = config.load()
        self._destination = config.destination(self._settings)
        self._profile = self._settings["profile"]
        self._jobs = []
        self._rows = {}
        self._running = False
        self._paths = [Path(p) for p in paths]

        self._build()
        self._thread = QThread(self)
        self._worker = TranscodeWorker()
        self._worker.moveToThread(self._thread)
        self.start_requested.connect(self._worker.run)
        self._worker.started.connect(self._on_started)
        self._worker.progressed.connect(self._on_progressed)
        self._worker.completed.connect(self._on_completed)
        self._worker.tick.connect(self._on_tick)
        self._worker.done.connect(self._on_done)
        self._thread.start()

        # let the window paint before ffprobe walks the selection
        QTimer.singleShot(0, self._load)

    def _build(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        destination = QHBoxLayout()
        self._alongside = QRadioButton("Alongside each clip")
        self._into = QRadioButton("Output directory")
        group = QButtonGroup(self)
        group.addButton(self._alongside)
        group.addButton(self._into)
        self._alongside.setChecked(self._destination.mode is Mode.ALONGSIDE)
        self._into.setChecked(self._destination.mode is Mode.DIRECTORY)
        self._alongside.toggled.connect(self._destination_changed)
        self._browse = QPushButton("Browse…")
        self._browse.clicked.connect(self._choose_directory)
        self._directory = QLabel("")
        destination.addWidget(self._alongside)
        destination.addWidget(self._into)
        destination.addWidget(self._browse)
        destination.addWidget(self._directory, 1)
        layout.addLayout(destination)

        self._summary = QLabel("Reading clips…")
        layout.addWidget(self._summary)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Clip", "Status", ""])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self._table.setColumnWidth(2, 150)
        layout.addWidget(self._table, 1)

        self._overall = QProgressBar()
        self._overall.setRange(0, 1000)
        self._overall.setTextVisible(False)
        layout.addWidget(self._overall)

        footer = QHBoxLayout()
        self._status = QLabel("")
        self._start = QPushButton("Start")
        self._start.clicked.connect(self._on_start)
        self._cancel = QPushButton("Cancel")
        self._cancel.clicked.connect(self._on_cancel)
        self._cancel.setEnabled(False)
        footer.addWidget(self._status, 1)
        footer.addWidget(self._start)
        footer.addWidget(self._cancel)
        layout.addLayout(footer)

        self.setCentralWidget(root)

    def _load(self):
        self._jobs = inspect(self._paths, self._profile)
        self._populate()
        self._reresolve()

    def _populate(self):
        self._table.setRowCount(len(self._jobs))
        self._rows.clear()
        for row, job in enumerate(self._jobs):
            self._rows[id(job)] = row
            self._table.setItem(row, 0, QTableWidgetItem(job.name))
            self._table.setItem(row, 1, QTableWidgetItem(""))
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            bar.setFixedHeight(14)
            self._table.setCellWidget(row, 2, bar)

    def _reresolve(self):
        if not self._jobs:
            return
        resolve(self._jobs, self._destination)
        for job in self._jobs:
            self._refresh(job)
        self._refresh_summary()

    def _refresh(self, job):
        row = self._rows.get(id(job))
        if row is None:
            return
        text = STATUS_TEXT.get(job.status, job.status.value)
        if job.note:
            text = f"{text} — {job.note}"
        self._table.item(row, 1).setText(text)
        bar = self._table.cellWidget(row, 2)
        if bar is not None:
            bar.setValue(int(job.fraction * 1000))

    def _refresh_summary(self):
        ready = [job for job in self._jobs if job.status is Status.READY]
        needed = required_bytes(self._jobs)
        free = free_bytes(self._jobs, self._destination)
        duration = sum(job.duration for job in ready)
        parts = [
            f"{len(ready)} of {len(self._jobs)} to transcode",
            humanise(duration) if duration else "0s",
            f"~{_size(needed)} as {transcode.PROFILES[self._profile].label}",
        ]
        if free is not None:
            parts.append(f"{_size(free)} free")
        self._summary.setText("  ·  ".join(parts))
        self._directory.setText(str(self._destination.directory or ""))
        self._browse.setEnabled(self._into.isChecked() and not self._running)
        short = free is not None and needed > free
        if short:
            self._status.setText("Not enough space on the destination")
        elif not ready:
            self._status.setText("Nothing to do")
        else:
            self._status.setText("")
        self._start.setEnabled(bool(ready) and not short and not self._running)

    def _destination_changed(self):
        if self._running:
            return
        if self._into.isChecked() and self._destination.directory is None:
            base = self._paths[0].parent if self._paths else Path.home()
            self._destination = Destination(Mode.DIRECTORY, base)
        else:
            mode = Mode.DIRECTORY if self._into.isChecked() else Mode.ALONGSIDE
            self._destination = Destination(mode, self._destination.directory)
        self._reresolve()

    def _choose_directory(self):
        start = str(self._destination.directory or (self._paths[0].parent if self._paths else Path.home()))
        chosen = QFileDialog.getExistingDirectory(self, "Output directory", start)
        if chosen:
            self._destination = Destination(Mode.DIRECTORY, Path(chosen))
            self._into.setChecked(True)
            self._reresolve()

    def _on_start(self):
        self._running = True
        self._start.setEnabled(False)
        self._cancel.setEnabled(True)
        self._alongside.setEnabled(False)
        self._into.setEnabled(False)
        self._browse.setEnabled(False)
        self._persist()
        self.start_requested.emit(self._jobs, self._profile)

    def _on_cancel(self):
        self._cancel.setEnabled(False)
        self._status.setText("Cancelling…")
        self._worker.stop()

    def _on_started(self, job):
        row = self._rows.get(id(job))
        if row is not None:
            self._table.item(row, 1).setText("transcoding")
            self._table.scrollToItem(self._table.item(row, 0))

    def _on_progressed(self, job, fraction, speed):
        row = self._rows.get(id(job))
        if row is None:
            return
        bar = self._table.cellWidget(row, 2)
        if bar is not None:
            bar.setValue(int(fraction * 1000))
        if speed:
            self._table.item(row, 1).setText(f"transcoding — {speed:.1f}x")

    def _on_completed(self, job):
        self._refresh(job)

    def _on_tick(self, fraction, eta):
        self._overall.setValue(int(fraction * 1000))
        self._status.setText(f"eta {humanise(eta)}" if eta else "")

    def _on_done(self):
        self._running = False
        self._cancel.setEnabled(False)
        self._alongside.setEnabled(True)
        self._into.setEnabled(True)
        written = sum(1 for job in self._jobs if job.status is Status.DONE)
        failed = sum(1 for job in self._jobs if job.status is Status.FAILED)
        skipped = sum(1 for job in self._jobs if job.status is Status.SKIPPED)
        self._status.setText(f"{written} written · {skipped} skipped · {failed} failed")
        self._browse.setEnabled(self._into.isChecked())

    def _persist(self):
        self._settings["mode"] = self._destination.mode.value
        self._settings["directory"] = str(self._destination.directory or "")
        self._settings["profile"] = self._profile
        try:
            config.save(self._settings)
        except OSError as error:
            self._log.warning("could not save config: %s", error)

    def closeEvent(self, event):
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(5000)
        super().closeEvent(event)


def launch(paths=None):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Resolve Prep")
    # lets Wayland match the window to the .desktop entry for its icon
    app.setDesktopFileName("resolve-prep")
    window = Window(paths or [])
    window.show()
    return app.exec()
