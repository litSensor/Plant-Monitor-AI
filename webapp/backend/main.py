import io
import json
import logging
import shutil
import tarfile
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import AppConfig
from .worker import Worker
from .summary import build_summary
from .camera import detect_cameras
from .diary import build_period_diary

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

CONFIG_PATH = Path("data/config.json")
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Plant Monitor")
scheduler = BackgroundScheduler()
state = {"cfg": None, "worker": None, "active_streams": {}}


def load_config() -> AppConfig:
    if CONFIG_PATH.exists():
        return AppConfig(**json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    cfg = AppConfig()
    CONFIG_PATH.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    return cfg


def save_config(cfg: AppConfig):
    CONFIG_PATH.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")


def setup_jobs():
    cfg, worker = state["cfg"], state["worker"]
    scheduler.remove_all_jobs()
    tz = cfg.schedule.timezone
    mh, mm = map(int, cfg.schedule.morning.split(":"))
    eh, em = map(int, cfg.schedule.evening.split(":"))
    scheduler.add_job(lambda: worker.run_cycle("morning"),
                      CronTrigger(hour=mh, minute=mm, timezone=tz),
                      id="morning", replace_existing=True,
                      misfire_grace_time=3600)
    scheduler.add_job(lambda: worker.run_cycle("evening"),
                      CronTrigger(hour=eh, minute=em, timezone=tz),
                      id="evening", replace_existing=True,
                      misfire_grace_time=3600)


@app.on_event("startup")
def startup():
    state["cfg"] = load_config()
    state["worker"] = Worker(state["cfg"])
    setup_jobs()
    scheduler.start()
    log.info("Сервер запущен.")


# ---------------- Config / cameras ----------------

@app.get("/api/config")
def get_config():
    return state["cfg"]


@app.post("/api/config")
def set_config(new_cfg: AppConfig):
    if new_cfg.camera.type == "usb":
        n_cameras = len(new_cfg.camera.devices)
        if new_cfg.plants_count > n_cameras:
            raise HTTPException(
                400,
                f"Растений ({new_cfg.plants_count}) больше, чем камер ({n_cameras})")
    names = list(new_cfg.plant_names)
    while len(names) < new_cfg.plants_count:
        names.append("")
    new_cfg.plant_names = names[:new_cfg.plants_count]

    state["cfg"] = new_cfg
    save_config(new_cfg)
    state["worker"] = Worker(new_cfg)
    setup_jobs()
    return {"ok": True}


@app.get("/api/cameras")
def get_cameras():
    cams = detect_cameras()
    return {"count": sum(1 for c in cams if c["ok"]), "cameras": cams}


# ---------------- Health ----------------

@app.get("/api/health")
def health():
    """Свободное место, размер данных, количество фото и дневников."""
    base = Path(".")
    photos_dir = base / "data" / "photos"
    diaries_dir = base / "data" / "diaries"

    def dir_size(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

    du = shutil.disk_usage(str(base))
    n_photos = sum(1 for _ in photos_dir.rglob("*.jpg")) if photos_dir.exists() else 0
    n_diaries = sum(1 for _ in diaries_dir.glob("*.md")) if diaries_dir.exists() else 0

    def fmt_size(size_bytes: int) -> dict:
        """Возвращает {value, unit} — КБ для мелких, МБ для крупных."""
        if size_bytes < 1024 * 1024:  # меньше 1 МБ
            return {"value": round(size_bytes / 1024, 1), "unit": "КБ"}
        return {"value": round(size_bytes / 1024**2, 2), "unit": "МБ"}

    return {
        "disk_total_gb": round(du.total / 1024**3, 2),
        "disk_used_gb": round(du.used / 1024**3, 2),
        "disk_free_gb": round(du.free / 1024**3, 2),
        "photos_count": n_photos,
        "photos_size": fmt_size(dir_size(photos_dir)),
        "diaries_count": n_diaries,
        "diaries_size": fmt_size(dir_size(diaries_dir)),
    }


# ---------------- Snapshot ----------------

@app.post("/api/snapshot/{plant_id}")
def snapshot(plant_id: int, time_of_day: str = "morning"):
    if not (1 <= plant_id <= state["cfg"].plants_count):
        raise HTTPException(400, "Неверный номер растения")
    state["worker"].run_cycle(time_of_day, plant_id=plant_id)
    return {"ok": True}


@app.post("/api/snapshot_all")
def snapshot_all(time_of_day: str = "morning"):
    """Сделать снимок всех растений."""
    state["worker"].run_cycle(time_of_day)
    return {"ok": True, "plants": state["cfg"].plants_count}


# ---------------- Photos gallery ----------------

@app.get("/api/photos/{plant_id}")
def list_photos(plant_id: int):
    """Список фото растения (от новых к старым)."""
    d = Path("data/photos") / f"plant_{plant_id}"
    if not d.exists():
        return {"plant_id": plant_id, "photos": []}
    files = sorted(d.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for p in files:
        items.append({
            "name": p.name,
            "url": f"/photos/plant_{plant_id}/{p.name}",
            "size_kb": round(p.stat().st_size / 1024, 1),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return {"plant_id": plant_id, "count": len(items), "photos": items}


# ---------------- Archive download ----------------

@app.get("/api/download/archive")
def download_archive():
    """Скачать .tar.gz с фото и дневниками."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for sub in ("data/photos", "data/diaries"):
            p = Path(sub)
            if p.exists():
                tar.add(p, arcname=p.name)
    buf.seek(0)
    fname = f"plant_monitor_{datetime.now():%Y%m%d_%H%M}.tar.gz"
    return Response(
        content=buf.getvalue(),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------- Camera preview / stream ----------------

@app.get("/api/camera/preview/{plant_id}")
def camera_preview(plant_id: int):
    import cv2
    if not (1 <= plant_id <= state["cfg"].plants_count):
        raise HTTPException(400, "Неверный номер растения")
    try:
        frame = state["worker"].camera.capture(plant_id)
        ok, buf = cv2.imencode(".jpg", frame,
                               [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            raise RuntimeError("Ошибка кодирования JPEG")
        return Response(content=buf.tobytes(), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(500, f"Ошибка камеры: {e}")


@app.get("/api/camera/stream/{plant_id}")
def camera_stream(plant_id: int, fps: int = 10):
    import cv2
    cfg = state["cfg"]
    if not (1 <= plant_id <= cfg.plants_count):
        raise HTTPException(400, "Неверный номер растения")
    cam = state["worker"].camera
    src = cam._source(plant_id)

    BOUNDARY = b"--frame\r\n"
    HEADER = b"Content-Type: image/jpeg\r\n\r\n"
    CRLF = b"\r\n"

    def gen():
        cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        state["active_streams"][plant_id] = cap
        try:
            if not cap.isOpened():
                return
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.height)
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                ok, buf = cv2.imencode(
                    ".jpg", frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if not ok:
                    continue
                yield BOUNDARY + HEADER + buf.tobytes() + CRLF
        except (GeneratorExit, Exception):
            pass
        finally:
            state["active_streams"].pop(plant_id, None)
            try:
                cap.release()
            except Exception:
                pass

    return StreamingResponse(
        gen(),
        media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/camera/stream/stop/{plant_id}")
def camera_stream_stop(plant_id: int):
    cap = state["active_streams"].pop(plant_id, None)
    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass
        return {"ok": True, "stopped": True}
    return {"ok": True, "stopped": False}


# ---------------- Diaries ----------------

@app.get("/api/diaries")
def list_diaries():
    d = Path("data/diaries")
    return sorted(p.name for p in d.glob("*.md")) if d.exists() else []


@app.get("/api/diaries/{name}")
def get_diary(name: str):
    p = Path("data/diaries") / name
    if not p.exists() or p.suffix != ".md":
        raise HTTPException(404)
    return FileResponse(p, media_type="text/markdown")


@app.post("/api/summary/{plant_id}")
def make_summary(plant_id: int, start: str, end: str):
    path = build_summary(plant_id, state["cfg"].plant_names, start, end)
    return {"ok": True, "file": path.name}


@app.post("/api/period_diary")
def make_period_diary(start: str, end: str):
    try:
        path = build_period_diary(
            start, end,
            state["cfg"].plant_names,
            state["cfg"].plants_count,
        )
    except Exception as e:
        raise HTTPException(400, f"Не удалось собрать дневник: {e}")
    return {"ok": True, "file": path.name}


# ---------------- Snapshot (только фото) ----------------

@app.post("/api/photo_only/{plant_id}")
def photo_only(plant_id: int):
    """Сделать снимок и сохранить в photos/, БЕЗ записи в дневник."""
    import cv2
    from datetime import datetime
    cfg = state["cfg"]
    if not (1 <= plant_id <= cfg.plants_count):
        raise HTTPException(400, "Неверный номер растения")
    try:
        frame = state["worker"].camera.capture(plant_id)
        folder = Path("data/photos") / f"plant_{plant_id}"
        folder.mkdir(parents=True, exist_ok=True)
        fname = f"{datetime.now():%Y-%m-%d_%H-%M-%S}_test.jpg"
        fpath = folder / fname
        cv2.imwrite(str(fpath), frame)
        log.info("Только фото: plant=%s -> %s", plant_id, fname)
        return {"ok": True, "file": str(fpath.relative_to("data/photos"))}
    except Exception as e:
        raise HTTPException(500, f"Ошибка камеры: {e}")


# ---------------- Logs ----------------

@app.get("/api/logs")
def get_logs(lines: int = 200):
    """Последние N строк логов: systemd-журнал + app.log, если есть."""
    import subprocess
    lines = max(10, min(lines, 2000))
    result = []

    # systemd журнал
    try:
        out = subprocess.run(
            ["journalctl", "-u", "plant-monitor", "-n", str(lines),
             "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            result.extend(out.stdout.splitlines())
    except Exception:
        pass

    # если есть локальный app.log — тоже добавим
    app_log = Path("app.log")
    if app_log.exists():
        try:
            with app_log.open("r", encoding="utf-8", errors="replace") as f:
                tail = deque(f, maxlen=lines)
            result.extend(list(tail))
        except Exception:
            pass

    return {"lines": result[-lines:], "count": len(result[-lines:])}


# ---------------- Describe last photo ----------------

@app.post("/api/describe_last/{plant_id}")
def describe_last(plant_id: int):
    """Взять последнее фото растения, сгенерировать текст через LLM и дописать в дневник."""
    from .diary import append_ai_comment
    cfg = state["cfg"]
    if not (1 <= plant_id <= cfg.plants_count):
        raise HTTPException(400, "Неверный номер растения")
    if not getattr(cfg.analysis, "enabled", False):
        raise HTTPException(400, "Анализ отключён в конфиге")

    folder = Path("data/photos") / f"plant_{plant_id}"
    if not folder.exists():
        raise HTTPException(404, "Нет фото для этого растения")
    photos = sorted(folder.glob("*.jpg"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    if not photos:
        raise HTTPException(404, "Нет фото для этого растения")
    latest = photos[0]

    # Анализ фото
    analysis = state["worker"].analyzer.analyze(str(latest))

    # Имя растения
    name = (cfg.plant_names[plant_id - 1]
            if len(cfg.plant_names) >= plant_id
            else f"Растение #{plant_id}")

    # Определим время суток по имени файла
    time_of_day = "auto"
    if "_morning" in latest.name:
        time_of_day = "morning"
    elif "_evening" in latest.name:
        time_of_day = "evening"

    # Генерация (может занять 1-3 минуты)
    text = state["worker"].narrator.describe(plant_id, name, time_of_day, analysis)
    if not text:
        raise HTTPException(500, "LLM не вернула текст (проверьте логи)")

    # Дописать в дневник
    path = append_ai_comment(plant_id, cfg.plant_names, text, time_of_day)
    log.info("LLM-описание дописано: plant=%s -> %s", plant_id, path.name)

    return {"ok": True, "file": path.name, "text": text}


# ---------------- Static ----------------

app.mount("/photos", StaticFiles(directory="data/photos"), name="photos")
app.mount("/static", StaticFiles(directory="backend/static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("backend/templates/index.html")
