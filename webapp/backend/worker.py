import logging
from datetime import datetime
from pathlib import Path
import cv2
from .camera import build_camera
from .analyzer import PlantAnalyzer
from .diary import append_entry
from .narrator import Narrator

log = logging.getLogger("worker")
PHOTOS_DIR = Path("data/photos")


class Worker:
    def __init__(self, config):
        self.cfg = config
        self.camera = build_camera(config.camera)
        self.analyzer = PlantAnalyzer(config.analysis)
        self.narrator = Narrator(Path("data/diaries"))

    def run_cycle(self, time_of_day: str, plant_id: int | None = None):
        ids = [plant_id] if plant_id else range(1, self.cfg.plants_count + 1)
        for pid in ids:
            try:
                self._one(pid, time_of_day)
            except Exception:
                log.exception("Ошибка plant=%s", pid)

    def _one(self, plant_id: int, time_of_day: str):
        frame = self.camera.capture(plant_id)
        folder = PHOTOS_DIR / f"plant_{plant_id}"
        folder.mkdir(parents=True, exist_ok=True)
        fname = f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{time_of_day}.jpg"
        fpath = folder / fname
        cv2.imwrite(str(fpath), frame)
        analysis = self.analyzer.analyze(str(fpath))

        # Генерация текстового описания через LLM
        if getattr(self.cfg.analysis, "use_llm", False):
            name = (self.cfg.plant_names[plant_id - 1]
                    if len(self.cfg.plant_names) >= plant_id
                    else f"Растение #{plant_id}")
            description = self.narrator.describe(plant_id, name, time_of_day, analysis)
            if description:
                analysis["description"] = description

        rel = f"../photos/plant_{plant_id}/{fname}"
        append_entry(plant_id, self.cfg.plant_names,
                     time_of_day, rel, analysis)
        log.info("Дневник обновлён: plant=%s %s", plant_id, time_of_day)
