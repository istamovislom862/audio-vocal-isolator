# 🎙️ Audio Vocal & Voice Isolator

Zamonaviy va yuqori tezlikda ishlovchi audio vokal va musiqani ajratuvchi (Vocal & Voice Isolator) web-ilovasi. 
Backend **FastAPI** va **Meta Demucs AI** arxitekturasi asosida, frontend esa **Tailwind CSS** va **Vanilla JavaScript** yordamida yaratilgan.

---

## ⚡ Asosiy xususiyatlar

- 🚀 **Apparat tezlatkichi (Hardware Acceleration):** Apple Silicon GPU (MPS) va NVIDIA CUDA avtomatik aniqlanadi va hisoblashlar bir necha barobar tezlashadi.
- ⏱️ **Real-time Progress & ETA:** Neyron tarmoqning ajratish jarayoni, foizi (%) va qolgan vaqti (daqiqa/soniya) jonli hisoblab ko'rsatiladi.
- 🎚️ **HTTP 206 Range Streaming:** Katta hajmdagi audiolarda ham vaqt chizig'ini (seek / scrub) istalgan joyga bosib, qotishlarsiz tinglash imkoniyati.
- 📥 **3 ta mustaqil audio pleyer va yuklab olish:**
  1. Asl audio (Original)
  2. Faqat inson ovozi (Vocals)
  3. Fon musiqa / instrumental (No Vocals)
- 📁 **Kengaytirilgan hajm:** 200 MB gacha bo'lgan `.mp3`, `.wav`, `.ogg`, `.m4a` formatlarini qo'llab-quvvatlaydi.
- 🧹 **Avtomatik tozalash (Cleanup):** Eskirgan vaqtinchalik audio fayllar avtomatik ravishda diskdan o'chirib boriladi.

---

## 🛠️ Texnologiyalar

- **Backend:** Python 3.9+, FastAPI, Uvicorn, Jinja2
- **AI / Audio Engine:** Meta Demucs (`htdemucs`), PyTorch, TorchAudio
- **Tizim talabi:** FFmpeg
- **Frontend:** HTML5, Tailwind CSS, Vanilla JavaScript

---

## 🚀 O'rnatish va ishga tushirish

### 1. Tizim talabi (FFmpeg)
Demucs audio fayllar bilan ishlashi uchun kompyuteringizda `ffmpeg` o'rnatilgan bo'lishi kerak:

```bash
# macOS (Homebrew orqali)
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg -y
```

### 2. Loyihani klonlash va virtual muhit yaratish

```bash
git clone https://github.com/istamovislom862/audio-vocal-isolator.git
cd audio-vocal-isolator

python3 -m venv .venv
source .venv/bin/activate
```

### 3. Paketlarni o'rnatish

```bash
pip install -r requirements.txt
```

### 4. Serverni ishga tushirish

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Brauzerda oching: **[http://localhost:8000](http://localhost:8000)**

---

## 📁 Loyiha tuzilmasi

```
audio-vocal-isolator/
├── main.py              # FastAPI marshrutlari va HTTP Range audio oqimi
├── separator.py         # Demucs AI integratsiyasi va GPU sozlamalari
├── requirements.txt     # Python kutubxonalari
├── templates/
│   └── index.html       # Web-interfeys (Tailwind CSS)
├── static/
│   └── js/
│       └── app.js       # Drag & drop, real-time polling va pleyerlar
├── uploads/             # Vaqtinchalik yuklangan audiolari
└── outputs/             # Ajratilgan natijalar
```

---

## 📄 Litsenziya

MIT License
