#!/usr/bin/env python3
"""
Tastetify v5 — Final (UI & Seek Fix)

Fitur:
- Tagging genre MP3 (pending + save, undo)
- Player dengan autoplay, progress, seek, volume
- Cover art dibaca dari file (tidak pernah di-embed)
- Cover 1:1 di tengah, list MP3 kotak kecil di bawah cover
- Input/Output folder jelas di-label

Dependencies:
    pip install mutagen pillow
    pip install pygame-ce   # atau pygame biasa kalau kompatibel
"""

import os
import io
import glob
import shutil
import traceback
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from datetime import timedelta

from mutagen.id3 import ID3, ID3NoHeaderError, APIC, TCON
from mutagen.mp3 import MP3
from PIL import Image, ImageTk

# try to import pygame for playback
try:
    import pygame
    PYGAME_AVAILABLE = True
except Exception:
    pygame = None
    PYGAME_AVAILABLE = False

# ---------------- ID3 helpers ----------------
def read_genre(path):
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        return None
    except Exception:
        return None
    frame = id3.get("TCON")
    if frame and frame.text:
        return str(frame.text[0])
    return None


def write_genre(path, genre):
    try:
        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            id3 = ID3()
        id3["TCON"] = TCON(encoding=3, text=str(genre))
        id3.save(path)
        return True
    except Exception as e:
        print("write_genre error:", e)
        traceback.print_exc()
        return False


def read_basic_tags(path):
    """
    Return simple dict for display: title, artist, album, duration.
    """
    info = {"title": "", "artist": "", "album": "", "duration": None}
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        id3 = {}
    except Exception:
        id3 = {}
    t = id3.get("TIT2")
    if t and t.text:
        info["title"] = str(t.text[0])
    a = id3.get("TPE1")
    if a and a.text:
        info["artist"] = str(a.text[0])
    al = id3.get("TALB")
    if al and al.text:
        info["album"] = str(al.text[0])
    try:
        audio = MP3(path)
        info["duration"] = float(audio.info.length)
    except Exception:
        info["duration"] = None
    return info


def read_cover_image(path):
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        return None
    except Exception:
        return None
    for key, frame in id3.items():
        if key.startswith("APIC"):
            try:
                img_data = frame.data
                img = Image.open(io.BytesIO(img_data))
                return img
            except Exception:
                continue
    return None


def get_duration_seconds(path):
    try:
        audio = MP3(path)
        return float(audio.info.length)
    except Exception:
        return None


# Helper formatting
def fmt_time(s):
    try:
        s = int(round(s))
        return str(timedelta(seconds=s))
    except Exception:
        return "0:00:00"


# ---------------- Main App ----------------
class TastetifyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tastetify v5 — Final")
        self.geometry("1100x700")
        self.minsize(950, 600)

        # State
        self.input_folder = None
        self.output_folder = None
        self.files = []            # list of absolute paths
        self.genres = [
            "Rock", "Pop", "Jazz", "Hip-Hop", "EDM",
            "Classical", "Metal", "Folk", "Blues", "Other"
        ]
        self.pending_genres = {}   # path -> pending genre
        self.selection_paths = []  # tree selection (iids)
        self.cover_photo = None

        # history for undo: list of (path, old_genre, new_genre)
        self.history = []

        # playback state
        self.current_playing = None
        self.paused = False
        self.current_duration = 0.0  # seconds

        # tracking waktu untuk seek (supaya stabil)
        self.play_start_time = None  # time.time() saat terakhir play/unpause
        self.play_offset = 0.0       # detik, posisi dalam file saat play_start_time

        if PYGAME_AVAILABLE:
            pygame.mixer.init()

        self._build_ui()
        self._bind_shortcuts()

        # schedule periodic progress UI update
        self.after(500, self._update_progress_ui)

    # ---------------- UI BUILD ----------------
    def _build_ui(self):
        # Top controls (bar atas)
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Select Input Folder", command=self.select_input_folder).pack(side="left", padx=4)
        ttk.Button(top, text="Select Output Folder", command=self.select_output_folder).pack(side="left", padx=4)
        ttk.Button(top, text="Refresh", command=self.refresh_files).pack(side="left", padx=4)

        ttk.Label(top, text=" Move/Copy:").pack(side="left", padx=(12, 4))
        self.move_var = tk.StringVar(value="copy")
        ttk.Radiobutton(top, text="Copy", variable=self.move_var, value="copy").pack(side="left")
        ttk.Radiobutton(top, text="Move", variable=self.move_var, value="move").pack(side="left")
        ttk.Label(top, text="    ").pack(side="left", padx=12)
        ttk.Button(top, text="Save Pending (Ctrl+S)", command=self.save_pending).pack(side="left")

        # Path info (penanda input/output)
        path_bar = ttk.Frame(self, padding=(8, 0))
        path_bar.pack(fill="x")
        self.input_label_var = tk.StringVar(value="Input: (none)")
        self.output_label_var = tk.StringVar(value="Output: (none)")
        ttk.Label(path_bar, textvariable=self.input_label_var).pack(side="left", padx=(0, 16))
        ttk.Label(path_bar, textvariable=self.output_label_var).pack(side="left")

        # Main area: kiri (cover + list kecil), kanan (controls)
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=8, pady=8)

        main.columnconfigure(0, weight=3)  # kiri
        main.columnconfigure(1, weight=2)  # kanan
        main.rowconfigure(0, weight=1)

        # --- Left: cover + small MP3 list ---
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=3)  # cover
        left.rowconfigure(1, weight=1)  # list kecil
        left.columnconfigure(0, weight=1)

        # Cover frame (besar, tengah, 1:1)
        cover_frame = ttk.LabelFrame(left, text="Cover", padding=8)
        cover_frame.grid(row=0, column=0, sticky="nsew")
        cover_frame.rowconfigure(0, weight=1)
        cover_frame.columnconfigure(0, weight=1)

        self.cover_label = ttk.Label(cover_frame, text="No cover", anchor="center")
        self.cover_label.grid(row=0, column=0, sticky="nsew")

        # Info text + small list
        info_frame = ttk.Frame(left)
        info_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        info_frame.rowconfigure(1, weight=1)
        info_frame.columnconfigure(0, weight=1)

        self.info_var = tk.StringVar(value="Select a file to preview tags")
        ttk.Label(info_frame, textvariable=self.info_var, wraplength=360, justify="center").grid(
            row=0, column=0, pady=(0, 4)
        )

        # MP3 list kecil di bawah cover
        list_frame = ttk.Frame(info_frame)
        list_frame.grid(row=1, column=0, sticky="nsew")
        ttk.Label(list_frame, text="MP3 Files").pack(anchor="w")

        cols = ("filename", "genre", "pending")
        self.tree = ttk.Treeview(
            list_frame,
            columns=cols,
            show="headings",
            selectmode="extended",
            height=8,
        )
        self.tree.heading("filename", text="Filename")
        self.tree.heading("genre", text="Genre")
        self.tree.heading("pending", text="Pending")
        self.tree.column("filename", width=360, anchor="w")
        self.tree.column("genre", width=120, anchor="w")
        self.tree.column("pending", width=120, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        # --- Right: tag, playback, export ---
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Tag frame
        tag_frame = ttk.LabelFrame(right, text="Tag / Genre", padding=8)
        tag_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(tag_frame, text="Genre:").grid(row=0, column=0, sticky="w")
        self.genre_var = tk.StringVar()
        self.genre_combo = ttk.Combobox(tag_frame, values=self.genres, textvariable=self.genre_var)
        self.genre_combo.grid(row=0, column=1, sticky="ew", padx=6)
        tag_frame.columnconfigure(1, weight=1)
        ttk.Button(tag_frame, text="Assign to Selected (Enter)", command=self.assign_genre).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Button(tag_frame, text="Add Custom Genre", command=self.add_genre).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Button(tag_frame, text="Clear Tag (Remove)", command=self.clear_tag_selected).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

        # Playback frame
        play_frame = ttk.LabelFrame(right, text="Playback", padding=8)
        play_frame.pack(fill="x", pady=8)

        ttk.Button(play_frame, text="▶ Play Selected", command=self.play_selected).pack(fill="x", pady=4)
        self.pause_btn = ttk.Button(play_frame, text="⏸ Pause/Resume (Space)", command=self.toggle_pause)
        self.pause_btn.pack(fill="x", pady=4)
        ttk.Button(play_frame, text="⏹ Stop", command=self.stop_song).pack(fill="x", pady=4)

        nav = ttk.Frame(play_frame)
        nav.pack(fill="x", pady=4)
        ttk.Button(nav, text="⏮ Prev (Up)", width=12, command=self.play_prev).pack(side="left", padx=6)
        ttk.Button(nav, text="⏭ Next (Down)", width=12, command=self.play_next).pack(side="left", padx=6)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Scale(
            play_frame,
            variable=self.progress_var,
            from_=0,
            to=100,
            orient="horizontal",
            command=self.on_progress_drag,
        )
        self.progress.pack(fill="x", pady=(8, 2))
        time_row = ttk.Frame(play_frame)
        time_row.pack(fill="x")
        self.time_label = ttk.Label(time_row, text="00:00:00 / 00:00:00")
        self.time_label.pack(side="left")

        vol_row = ttk.Frame(play_frame)
        vol_row.pack(fill="x", pady=(6, 0))
        ttk.Label(vol_row, text="Volume").pack(side="left")
        self.volume_var = tk.DoubleVar(value=0.9)
        self.volume_scale = ttk.Scale(
            vol_row,
            variable=self.volume_var,
            from_=0.0,
            to=1.0,
            orient="horizontal",
            command=self.on_volume_change,
        )
        self.volume_scale.pack(fill="x", expand=True, padx=6)

        exp_frame = ttk.LabelFrame(right, text="Export & Playlists", padding=8)
        exp_frame.pack(fill="x", pady=(8, 8))
        ttk.Button(exp_frame, text="Export Sorted (by genre)", command=self.export_sorted).pack(fill="x", pady=4)
        ttk.Button(exp_frame, text="Make Playlists (.m3u) in Output", command=self.make_playlists).pack(fill="x", pady=4)

        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(fill="x", side="bottom")

        self.on_volume_change(self.volume_var.get())

    # ---------------- Bindings ----------------
    def _bind_shortcuts(self):
        self.bind_all("<Return>", lambda e: self.assign_genre())
        self.bind_all("<Up>", lambda e: self.play_prev())
        self.bind_all("<Down>", lambda e: self.play_next())
        self.bind_all("<Left>", lambda e: self.seek_relative(-5))
        self.bind_all("<Right>", lambda e: self.seek_relative(5))
        self.bind_all("<space>", lambda e: self.toggle_pause())
        self.bind_all("<Control-s>", lambda e: self.save_pending())
        self.bind_all("<Control-S>", lambda e: self.save_pending())
        self.bind_all("<Control-z>", lambda e: self.undo_last())
        self.bind_all("<Control-Z>", lambda e: self.undo_last())

    # ---------------- Folder & listing ----------------
    def select_input_folder(self):
        folder = filedialog.askdirectory(title="Select input folder with MP3 files")
        if not folder:
            return
        self.input_folder = folder
        self.input_label_var.set(f"Input: {folder}")
        self.status_var.set(f"Input folder set to: {folder}")
        self.refresh_files()

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if not folder:
            return
        self.output_folder = folder
        self.output_label_var.set(f"Output: {folder}")
        self.status_var.set(f"Output folder set to: {folder}")

    def refresh_files(self):
        self.tree.delete(*self.tree.get_children())
        self.files = []
        self.pending_genres.clear()
        self.selection_paths.clear()
        self.cover_photo = None
        self.cover_label.config(image="", text="No cover")
        self.info_var.set("Select a file to preview tags")
        self.current_playing = None
        self.paused = False
        self.current_duration = 0.0
        self.play_offset = 0.0
        self.play_start_time = None
        self.time_label.config(text="00:00:00 / 00:00:00")
        self.progress_var.set(0)

        if not getattr(self, "input_folder", None):
            return
        folder = self.input_folder
        pattern = os.path.join(folder, "**", "*.mp3")
        files = glob.glob(pattern, recursive=True)
        files.sort()
        self.files = [os.path.abspath(f) for f in files]
        for path in self.files:
            base = os.path.basename(path)
            g = read_genre(path) or ""
            self.tree.insert("", "end", iid=path, values=(base, g, ""))
        self.status_var.set(f"Loaded {len(self.files)} MP3 file(s).")

    def on_tree_select(self, event=None):
        sel = self.tree.selection()
        self.selection_paths = list(sel)
        if sel:
            self._preview_file(sel[0])

    def _preview_file(self, path):
        tags = read_basic_tags(path)
        gen = self.pending_genres.get(path) or read_genre(path) or "(none)"
        info_lines = [
            f"File: {os.path.basename(path)}",
            f"Title: {tags.get('title') or '—'}",
            f"Artist: {tags.get('artist') or '—'}",
            f"Album: {tags.get('album') or '—'}",
            f"Genre (tag/pending): {gen}",
        ]
        self.info_var.set("\n".join(info_lines))

        self.cover_label.config(text="Loading...", image="")
        img = read_cover_image(path)

        if img:
            w, h = img.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img_cropped = img.crop((left, top, left + side, top + side))

            max_side = 320
            if side > max_side:
                img_cropped = img_cropped.resize((max_side, max_side), Image.LANCZOS)

            self.cover_photo = ImageTk.PhotoImage(img_cropped)
            self.cover_label.config(image=self.cover_photo, text="")
        else:
            self.cover_label.config(image="", text="No cover")

    # ---------------- Tagging & history ----------------
    def assign_genre(self):
        genre = self.genre_var.get().strip()
        if not genre:
            messagebox.showinfo("Pick genre", "Choose or add a genre first.")
            return
        if not self.selection_paths:
            messagebox.showinfo("Select files", "Select one or more files in the list.")
            return
        for p in self.selection_paths:
            old = read_genre(p) or ""
            self.history.append((p, old, genre))
            self.pending_genres[p] = genre
            if self.tree.exists(p):
                self.tree.set(p, "pending", genre)
        self.status_var.set(f"Assigned pending genre '{genre}' to {len(self.selection_paths)} file(s).")

    def add_genre(self):
        new = simpledialog.askstring("Add Genre", "Enter new genre name:")
        if not new:
            return
        new = new.strip()
        if not new:
            return
        if new not in self.genres:
            self.genres.append(new)
            self.genre_combo.config(values=self.genres)
        self.genre_var.set(new)

    def clear_tag_selected(self):
        if not self.selection_paths:
            messagebox.showinfo("Select files", "Select one or more files in the list.")
            return
        for p in self.selection_paths:
            old = read_genre(p) or ""
            self.history.append((p, old, ""))
            self.pending_genres[p] = ""
            if self.tree.exists(p):
                self.tree.set(p, "pending", "")
        self.status_var.set(f"Marked {len(self.selection_paths)} file(s) to clear genre.")

    # ---------------- Save pending ----------------
    def save_pending(self, event=None):
        if not self.pending_genres:
            messagebox.showinfo("Nothing to save", "There are no pending changes.")
            return
        errors = []
        saved_count = 0

        for path, genre in list(self.pending_genres.items()):
            try:
                ok = write_genre(path, genre)
                if ok:
                    saved_count += 1
                    if self.tree.exists(path):
                        self.tree.set(path, "genre", genre)
                        self.tree.set(path, "pending", "")
                    del self.pending_genres[path]
                else:
                    errors.append((path, "write_genre failed"))
            except Exception as e:
                errors.append((path, str(e)))

        msg = f"Saved {saved_count} items."
        if errors:
            msg += f" Failed for {len(errors)} files. See console."
            traceback.print_exc()
        self.status_var.set(msg)
        messagebox.showinfo("Save completed", msg)
        if self.selection_paths:
            self._preview_file(self.selection_paths[0])

    # ---------------- UNDO ----------------
    def undo_last(self, event=None):
        if not self.history:
            messagebox.showinfo("Undo", "No action to undo.")
            return
        path, old, new = self.history.pop()
        try:
            if path in self.pending_genres:
                del self.pending_genres[path]
            if self.tree.exists(path):
                self.tree.set(path, "pending", "")
            ok = write_genre(path, old)
            if ok:
                if self.tree.exists(path):
                    self.tree.set(path, "genre", old)
                self.status_var.set(f"Undo: {os.path.basename(path)} -> '{old or '(none)'}'")
            else:
                messagebox.showerror("Undo error", "Failed to restore previous genre.")
        except Exception as e:
            messagebox.showerror("Undo error", str(e))

    # ---------------- Playback & Seek ----------------
    def _set_play_position(self, start_pos):
        self.play_offset = float(start_pos)
        self.play_start_time = time.time()

    def _current_position(self):
        if self.current_playing is None:
            return 0.0
        if self.play_start_time is None:
            return max(0.0, self.play_offset)
        return max(0.0, self.play_offset + (time.time() - self.play_start_time))

    def play_song(self, path, start_pos=None):
        if path is None:
            return
        if not PYGAME_AVAILABLE:
            self.status_var.set("Playback unavailable: pygame not installed.")
            return
        try:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

            pygame.mixer.music.load(path)
            if start_pos is None:
                pygame.mixer.music.play()
                self._set_play_position(0.0)
            else:
                sp = float(start_pos)
                try:
                    pygame.mixer.music.play(start=sp)
                except TypeError:
                    pygame.mixer.music.play()
                    sp = 0.0
                except Exception:
                    pygame.mixer.music.play()
                    sp = 0.0
                self._set_play_position(sp)

            pygame.mixer.music.set_volume(self.volume_var.get())
            self.current_playing = path
            self.paused = False
            self.current_duration = get_duration_seconds(path) or 0.0
            self.status_var.set(f"Playing: {os.path.basename(path)}")
            self.time_label.config(text=f"00:00:00 / {fmt_time(self.current_duration)}")
            self.progress_var.set(0)
            self.after(1000, self._check_autoplay)
        except Exception as e:
            print("play_song error:", e)
            traceback.print_exc()
            self.status_var.set("Error playing file.")

    def play_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select file", "Select a file to play.")
            return
        path = sel[0]
        self.selection_paths = list(sel)
        self._preview_file(path)
        self.play_song(path)

    def play_next(self, event=None):
        if not self.files:
            return
        if not self.current_playing:
            current = self.selection_paths[0] if self.selection_paths else self.files[0]
        else:
            current = self.current_playing
        try:
            idx = self.files.index(current)
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(self.files)
        path = self.files[next_idx]
        self.tree.selection_set(path)
        self.tree.see(path)
        self.selection_paths = [path]
        self._preview_file(path)
        self.play_song(path)

    def play_prev(self, event=None):
        if not self.files:
            return
        if not self.current_playing:
            current = self.selection_paths[0] if self.selection_paths else self.files[0]
        else:
            current = self.current_playing
        try:
            idx = self.files.index(current)
        except ValueError:
            idx = 0
        prev_idx = (idx - 1) % len(self.files)
        path = self.files[prev_idx]
        self.tree.selection_set(path)
        self.tree.see(path)
        self.selection_paths = [path]
        self._preview_file(path)
        self.play_song(path)

    def toggle_pause(self):
        if not PYGAME_AVAILABLE or not self.current_playing:
            return
        try:
            if not self.paused:
                pygame.mixer.music.pause()
                self.paused = True
                self.play_offset = self._current_position()
                self.play_start_time = None
                self.status_var.set("Paused")
                self.pause_btn.config(text="▶ Resume (Space)")
            else:
                pygame.mixer.music.unpause()
                self.paused = False
                self.play_start_time = time.time()
                self.status_var.set("Playing")
                self.pause_btn.config(text="⏸ Pause/Resume (Space)")
        except Exception as e:
            print("pause error:", e)

    def stop_song(self):
        if not PYGAME_AVAILABLE:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.paused = False
        self.current_playing = None
        self.current_duration = 0.0
        self.play_offset = 0.0
        self.play_start_time = None
        self.status_var.set("Stopped")
        self.time_label.config(text="00:00:00 / 00:00:00")
        self.progress_var.set(0)

    def _check_autoplay(self):
        if not PYGAME_AVAILABLE or self.current_playing is None:
            return
        cur = self._current_position()
        dur = self.current_duration or 0.0
        if not self.paused and dur > 0 and cur >= dur - 0.5:
            self.play_next()
        else:
            self.after(1000, self._check_autoplay)

    def _update_progress_ui(self):
        try:
            if self.current_playing:
                cur = self._current_position()
                dur = self.current_duration or 0.0
                if dur > 0:
                    pct = max(0.0, min(100.0, (cur / dur) * 100.0))
                    self.progress_var.set(pct)
                self.time_label.config(text=f"{fmt_time(cur)} / {fmt_time(dur)}")
        except Exception:
            pass
        self.after(500, self._update_progress_ui)

    def on_progress_drag(self, value):
        try:
            pct = float(value)
            dur = self.current_duration or 0.0
            sec = (pct / 100.0) * dur if dur else 0.0
            self.time_label.config(text=f"{fmt_time(sec)} / {fmt_time(dur)}")
        except Exception:
            pass

    def seek_to(self, seconds):
        if not PYGAME_AVAILABLE or not self.current_playing:
            return
        seconds = max(0.0, float(seconds))
        if self.current_duration and seconds > self.current_duration:
            seconds = self.current_duration
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self.current_playing)
            try:
                pygame.mixer.music.play(start=seconds)
            except TypeError:
                pygame.mixer.music.play()
                seconds = 0.0
            except Exception:
                pygame.mixer.music.play()
                seconds = 0.0
            self._set_play_position(seconds)
            self.paused = False
            self.status_var.set(f"Seek to {fmt_time(seconds)}")
        except Exception as e:
            print("seek error:", e)

    def seek_relative(self, delta_seconds):
        if not PYGAME_AVAILABLE or not self.current_playing:
            return
        try:
            cur = self._current_position()
            dur = self.current_duration or get_duration_seconds(self.current_playing) or 0.0
            if dur <= 0:
                return
            new_pos = cur + float(delta_seconds)
            new_pos = max(0.0, min(dur, new_pos))
            self.seek_to(new_pos)
        except Exception as e:
            print("seek_relative error:", e)

    def on_volume_change(self, value):
        try:
            v = float(value)
            if PYGAME_AVAILABLE:
                pygame.mixer.music.set_volume(v)
        except Exception:
            pass

    def _seek_bindings(self):
        self.progress.bind("<ButtonRelease-1>", lambda e: self._on_progress_release())

    def _on_progress_release(self):
        try:
            pct = float(self.progress_var.get())
            dur = self.current_duration or 0.0
            sec = (pct / 100.0) * dur if dur else 0.0
            self.seek_to(sec)
        except Exception:
            pass

    # ---------------- Export / Playlists ----------------
    def export_sorted(self):
        if not getattr(self, "output_folder", None):
            messagebox.showinfo("Choose output", "Please choose an output folder first.")
            return
        to_process = []
        for path in list(self.files):
            genre = self.pending_genres.get(path) or read_genre(path)
            if not genre:
                continue
            to_process.append((path, genre))
        if not to_process:
            messagebox.showinfo("Nothing to export", "No files have a genre (including pending).")
            return
        move = (self.move_var.get() == "move")
        errors = []
        for path, genre in to_process:
            safe_genre = "".join(c for c in genre if c.isalnum() or c in " _-").strip() or "Unknown"
            dest_dir = os.path.join(self.output_folder, safe_genre)
            os.makedirs(dest_dir, exist_ok=True)
            base = os.path.basename(path)
            dest = os.path.join(dest_dir, base)
            try:
                if move:
                    shutil.move(path, dest)
                else:
                    shutil.copy2(path, dest)
            except Exception as e:
                errors.append((path, str(e)))
        msg = f"Exported {len(to_process)} files to '{self.output_folder}' ({'moved' if move else 'copied'})."
        if errors:
            msg += f"  Failed for {len(errors)} file(s)."
            print("Export errors:")
            for p, err in errors:
                print(p, "->", err)
        messagebox.showinfo("Export", msg)
        self.status_var.set(msg)
        if move:
            self.refresh_files()

    def make_playlists(self):
        if not getattr(self, "output_folder", None):
            messagebox.showinfo("Choose output", "Please choose an output folder first.")
            return
        base = self.output_folder
        genre_dirs = []
        for root, dirs, files in os.walk(base):
            if root == base:
                for d in dirs:
                    genre_dirs.append(os.path.join(base, d))
                break
        if not genre_dirs:
            messagebox.showinfo("No genre folders", "No genre folders found in output.")
            return
        created = 0
        for gdir in genre_dirs:
            mp3s = [f for f in os.listdir(gdir) if f.lower().endswith(".mp3")]
            if not mp3s:
                continue
            mp3s.sort()
            genre_name = os.path.basename(gdir)
            playlist_path = os.path.join(gdir, f"{genre_name}.m3u")
            try:
                with open(playlist_path, "w", encoding="utf-8") as pl:
                    for f in mp3s:
                        pl.write(f + "\n")
                created += 1
            except Exception as e:
                print("Playlist write error:", e)
        messagebox.showinfo("Playlists", f"Created {created} playlist(s).")
        self.status_var.set(f"Created {created} playlist(s) in output subfolders.")

    def run_post_init(self):
        self._seek_bindings()


def main():
    app = TastetifyApp()
    app.run_post_init()
    app.mainloop()


if __name__ == "__main__":
    main()
