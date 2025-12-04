🎵 Tastify — Ultimate MP3 Tagger & Player

Tastify adalah aplikasi MP3 tagger dan player all-in-one. Dirancang untuk memudahkan manajemen koleksi musik dengan UI modern, preview cover art, dan playback stabil.

✨ Fitur Utama

Tagging Genre:

* Assign genre ke MP3 secara cepat.
* Support pending changes, undo, dan custom genre.

Playback & Seek:

* Player built-in menggunakan pygame.
* Autoplay, prev/next, pause/resume, seek relatif dan absolute.
* Volume control & track progress.

Cover Art Preview:

* Menampilkan cover art asli dari file (tidak di-embed).
* Crop & scale otomatis agar tampil 1:1 di tengah.

Organisasi File & Export:

* Copy/move MP3 ke folder output berdasarkan genre.
* Buat playlist .m3u otomatis untuk setiap genre.

UI Modern:

* Cover art di tengah, MP3 list mini di bawah cover.
* Tagging di kanan atas, export di kanan bawah.
* Input/output folder jelas terlihat.

Undo History:

* Simpan perubahan tag yang terakhir dilakukan.
* Pulihkan dengan mudah jika terjadi kesalahan.

🛠️ Teknologi:

* Python 3
* Tkinter — GUI sederhana dan ringan.
* Mutagen — Manipulasi tag ID3.
* Pillow — Memproses cover art.
* Pygame — Playback audio (autoplay, seek, volume).

💾 Instalasi:

1. Install dependencies:
   pip install mutagen pillow
   pip install pygame-ce
2. Simpan script sebagai tastetify.py
3. Jalankan aplikasi: python tastetify.py

⌨️ Shortcut Keys:

* Enter: Assign genre ke file terpilih
* Up / Down: Previous / Next track
* Left / Right: Seek ±5 detik
* Space: Pause / Resume
* Ctrl+S: Save pending tags
* Ctrl+Z: Undo last change

💡 Tips Penggunaan:

* Pending genre: beri tag terlebih dahulu, baru save semua sekaligus.
* Undo: batalkan perubahan terakhir.
* Export: Copy untuk tetap mempertahankan file asli, Move untuk memindahkan ke folder genre.
* Playlists: otomatis membuat playlist .m3u untuk setiap genre.

📜 Lisensi:
MIT License. Bebas digunakan, dimodifikasi, dan dibagikan.
