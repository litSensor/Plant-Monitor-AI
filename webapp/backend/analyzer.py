import logging
from pathlib import Path

log = logging.getLogger("analyzer")


class PlantAnalyzer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.classifier = None
        self.leaf_model = None

        if not cfg.enabled:
            log.warning("Анализ отключён в конфиге.")
            return

        weights = Path(cfg.plant_classifier_weights)
        classes_json = weights.with_suffix(".classes.json")
        if not weights.exists():
            log.warning("Веса не найдены: %s", weights)
        elif not classes_json.exists():
            log.warning("Список классов не найден: %s", classes_json)
        else:
            try:
                from .classifier import SimpleClassifier
                device = "cuda" if _has_cuda() else "cpu"
                self.classifier = SimpleClassifier(
                    weights=str(weights),
                    classes_json=str(classes_json),
                    device=device,
                )
                log.info("SimpleClassifier загружен на %s", device)
            except Exception as e:
                log.exception("Ошибка загрузки классификатора: %s", e)

        leaf = Path(cfg.leaf_seg_weights)
        if leaf.exists():
            try:
                from ultralytics import YOLO
                self.leaf_model = YOLO(str(leaf))
                log.info("YOLO leaf_seg загружен")
            except Exception as e:
                log.error("leaf_seg: %s", e)

    def analyze(self, image_path: str) -> dict:
        result = {}
        if self.classifier is not None:
            try:
                pred = self.classifier.predict(image_path)
                # Применяем порог уверенности
                if (self.cfg.use_confidence_threshold
                        and pred.get("confidence", 0) < self.cfg.min_confidence):
                    pred["raw_prediction"] = pred.get("prediction")
                    pred["prediction"] = "не распознано"
                result.update(pred)
            except Exception as e:
                log.exception("Ошибка классификации: %s", e)
        return result


def _has_cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False
