# Lite3 Interactive Follower Robot 

Sistem kontrol robot cerdas yang menggabungkan pelacakan objek berbasis Computer Vision (YOLOv8 & MediaPipe) dan pengenalan suara mandiri sepenuhnya (Offline Speech Recognition menggunakan Whisper). Sistem ini dirancang untuk berjalan pada sistem operasi Linux (seperti Ubuntu) dan berkomunikasi dengan robot melalui jaringan lokal (UDP).

## Fitur Utama

### 1. Computer Vision (Vision & Tracking)
- [cite_start]**Person Re-identification (Color Histogram):** Robot tidak lagi asal mengikuti orang secara acak[cite: 10, 11]. [cite_start]Saat Anda mengangkat tangan (atau memberikan perintah suara), robot akan mengambil profil warna baju Anda (HSV Histogram) dan hanya akan mengikuti Anda[cite: 13, 14, 15].
- [cite_start]**Average Histogram Buffering:** Memastikan profil warna sangat akurat dengan merata-ratakan belasan frame data warna selama 0.5 detik tangan diangkat[cite: 20, 35, 112].
- [cite_start]**Hysteresis Thresholding & Lost Buffer:** Robot tidak mudah "kehilangan" Anda saat menjauh atau keluar dari frame berkat sistem dua batas ambang (atas: 0.70, bawah: 0.25) dan toleransi memori 1.5 detik[cite: 21, 22, 36, 113, 114].
- [cite_start]**ROI Optimization (60% Area):** Pemotongan kotak deteksi hanya 60% pada bagian dada untuk mencegah warna latar belakang mengganggu pelacakan[cite: 23, 37, 115].
- [cite_start]**Virtual Hand Raise:** Dapat menyimulasikan gestur angkat tangan melalui perintah suara tanpa harus mengangkat tangan secara fisik[cite: 605, 606].

### 2. Speech Recognition (Suara Offline)
- [cite_start]**100% Offline (Whisper AI):** Pemrosesan bahasa manusia tidak memerlukan jaringan internet sama sekali menggunakan model *Whisper Base/Tiny* dari OpenAI[cite: 353, 360, 378]. 
- [cite_start]**Noise Cancellation Adaptif:** Terbebas dari *Silence Hallucination* karena menggunakan filter `adjust_for_ambient_noise`, memblokir suara dengungan kipas laptop/komputer[cite: 406, 409].
- [cite_start]**Sistem Wake Word:** Robot beroperasi dengan mode tidur (*sleep*) dan hanya akan mendengarkan perintah jika dipanggil menggunakan nama (misal: "Halo robot" atau "Robot") untuk menghindari eksekusi yang tidak disengaja[cite: 531, 532, 535].
- [cite_start]**Bilingual Terkalibrasi:** Mampu merespons perintah dasar seperti "Berdiri", "Duduk", "Halo", dan "Ikuti saya"[cite: 544].

### 3. Kendali Cerdas
- [cite_start]**Dynamic Stopping:** Menggunakan filter Kalman untuk memperhalus pergerakan dan akan berhenti otomatis (*Auto Brake*) jika jaraknya sudah dekat/sejajar dengan pinggul/dada Anda[cite: 31, 57].
- [cite_start]**Gesture Action:** Saat robot dalam keadaan berhenti/terkunci (STOP), ia mengaktifkan kamera MediaPipe Hand Tracking[cite: 42]. [cite_start]Menunjukkan jempol atau jumlah jari tertentu akan mengeksekusi gerakan koreografi khusus seperti *Hello*, *Twist*, dll[cite: 44].

---

## Prasyarat Instalasi

Pastikan komputer/Mini PC Anda berjalan pada sistem operasi Linux. Sistem diuji menggunakan Virtual Environment (`venv`) Python 3.

### Langkah 1: Instalasi Paket OS Audio
Karena kita mengakses perangkat keras audio (mikrofon), jalankan perintah berikut pada terminal Linux Anda terlebih dahulu:
```bash
sudo apt-get update
sudo apt-get install portaudio19-dev python3-pyaudio ffmpeg
