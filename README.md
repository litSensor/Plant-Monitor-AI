# 🌱 Plant Monitor

> **⚠️ BETA VERSION — under active development**
> This project is in early beta. APIs, configuration format, and file structure
> may change without notice. Not recommended for production use yet.

An autonomous plant monitoring system that captures daily photos of plants via USB cameras, classifies their condition with a neural network, and generates a human-readable observation diary with LLM-written narratives.

Built on top of the [Microsoft Pytorch-Wildlife](https://github.com/microsoft/Pytorch-Wildlife) framework as its inference backend, extended with a standalone web application for greenhouse, botanical garden, or research use.

---

## ✨ Features

- 📷 **Multi-camera support** — 1 to 10 USB cameras, auto-detected via `/dev/v4l/by-id/`
- ⏰ **Scheduled capture** — configurable morning and evening snapshots (default: 08:00 / 20:00)
- 🧠 **Neural classification** — ResNet-18 fine-tuned on PlantVillage (38 classes), with confidence threshold
- 🤖 **LLM narratives** — local Ollama (`gemma2:2b`) writes 2–4 sentence descriptions
- 📝 **Markdown diaries** — one `.md` file per plant per day, with embedded photos
- 📊 **Period reports** — aggregate observations over a custom date range into one file
- 🎥 **Live MJPEG streaming** — real-time preview from any camera
- 🖼 **Photo gallery** — grid view of all photos per plant with lightbox
- 💾 **One-click archive** — download all photos and diaries as `.tar.gz`
- 🔄 **Health indicator** — free disk space, photo count, diary size
- 📜 **Event log** — last 200 lines of systemd logs in the browser
- 🚀 **Systemd auto-start** — survives reboots, restarts on failure

---

## 🏗 Architecture

```
Browser (web UI)
      │ HTTP / MJPEG
      ▼
FastAPI (backend)
      │
      ├── USB cameras
      ├── ResNet-18 (PyTorch)
      ├── Ollama (gemma2:2b)
      └── photos/ + diaries/
```

---

## 📋 Requirements

**Hardware**
- Server with USB ports (Raspberry Pi 4+ or x86_64)
- RAM: 4 GB minimum
- Disk: 10 GB+
- USB webcams

**Software**
- Linux (Debian/Ubuntu)
- Python 3.11 – 3.13
- PyTorch 2.x
- Ollama
- systemd

---

## 🚀 Installation

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/plant-monitor.git
cd plant-monitor
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install PyTorch

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

For CUDA: replace `cpu` with `cu124`.

### 3. Dependencies

```bash
pip install -e .
pip install fastapi "uvicorn[standard]" apscheduler python-multipart
pip install opencv-python Pillow numpy requests
```

### 4. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma2:2b
```

### 5. Configure cameras

```bash
python3 webapp/tools/list_cameras.py
```

Edit `webapp/data/config.json`:

```json
{
  "plants_count": 2,
  "plant_names": ["Ficus", "Lilac"],
  "schedule": {
    "morning": "08:00",
    "evening": "20:00",
    "timezone": "Europe/Moscow"
  },
  "camera": {
    "type": "usb",
    "devices": [
      "/dev/v4l/by-id/usb-Chicony_...-video-index0",
      "/dev/v4l/by-id/usb-Jieli_...-video-index0"
    ],
    "resolution": [640, 480],
    "warmup_frames": 8,
    "settle_sec": 1.0
  },
  "analysis": {
    "enabled": false,
    "plant_classifier_weights": "models/plant_classifier.pth",
    "use_confidence_threshold": true,
    "min_confidence": 0.4,
    "use_llm": false
  }
}
```

### 6. Grant camera access

```bash
sudo usermod -aG video $USER
newgrp video
```

### 7. systemd service

```bash
sudo tee /etc/systemd/system/plant-monitor.service > /dev/null << 'SERVICE'
[Unit]
Description=Plant Monitor
After=network.target

[Service]
Type=simple
User=bro
WorkingDirectory=/home/bro/Pytorch-Wildlife/webapp
ExecStart=/usr/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
SupplementaryGroups=video

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now plant-monitor
```

### 8. Open

```bash
hostname -I
```

Then visit `http://<server-ip>:8000` in a browser.

---

## 🧠 Training your own classifier

### 1. Dataset (ImageFolder format)

```
webapp/training_data/
├── healthy/
├── dry/
├── pest/
└── ...
```

10–15 images per class to start, 50+ for robust results.

### 2. Train

```bash
python3 webapp/train_classifier.py --epochs 20 --batch-size 16
```

### 3. Enable analysis

Set `"enabled": true` in `config.json`, then:

```bash
sudo systemctl restart plant-monitor
```

---

## 🎛 Web interface

| Section | Description |
|---|---|
| Health bar | Disk, photo count, diary size (30 s refresh) |
| Quick actions | Snap all plants, download archive |
| Settings | Plants, names, schedule, thresholds, LLM toggle |
| Live stream | MJPEG preview |
| Gallery | All photos per plant with lightbox |
| Manual snapshot | Full record or test photo |
| Period diary | Merge observations over a date range |
| Event log | Last 200 lines of systemd logs |

---

## 📂 Project structure

```
plant-monitor/
├── src/PytorchWildlife/           # Inference backend
│   └── models/classification/
│       └── plant_classifier.py
├── webapp/
│   ├── backend/
│   │   ├── config.py
│   │   ├── camera.py
│   │   ├── classifier.py
│   │   ├── analyzer.py
│   │   ├── narrator.py
│   │   ├── diary.py
│   │   ├── worker.py
│   │   ├── summary.py
│   │   ├── main.py
│   │   ├── templates/index.html
│   │   └── static/{style.css, app.js}
│   ├── data/{config.json, photos/, diaries/}
│   ├── models/
│   ├── training_data/
│   └── train_classifier.py
└── README.md
```

---

## ⚠️ Known limitations (beta)

- Model always returns a class from its training set — no "unknown" class. Enable confidence threshold to suppress noise.
- LLM latency on CPU: `gemma2:2b` takes 60–180 s per generation.
- Prompts are tuned for Russian. English localization not implemented.
- No authentication. Do not expose to the public internet.
- Single-user. Concurrent config edits may race.
- No automatic backups.

---

## 🗺 Roadmap

- [ ] Telegram notifications
- [ ] Daily backup of diaries
- [ ] Basic auth
- [ ] Log rotation
- [ ] Before/after comparison
- [ ] Time-series graphs
- [ ] PDF export
- [ ] Multi-language prompts
- [ ] Docker image

---

## 🤝 Contributing

Beta phase — issues and PRs welcome, expect API churn.

---

## 📜 License

Apache-2.0. See `LICENSE`. Uses [Microsoft Pytorch-Wildlife](https://github.com/microsoft/Pytorch-Wildlife) (MIT).

---

## 🙏 Acknowledgements

- [Microsoft AI for Good Lab](https://www.microsoft.com/en-us/ai/ai-for-good) — Pytorch-Wildlife
- [PlantVillage dataset](https://github.com/spMohanty/PlantVillage-Dataset) — training data
- [Ollama](https://ollama.com/) — LLM runtime
- [FastAPI](https://fastapi.tiangolo.com/), [OpenCV](https://opencv.org/)

---

*Built with 🌿 for botanists, gardeners, and anyone who talks to their plants.*
