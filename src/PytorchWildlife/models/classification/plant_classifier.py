"""
Классификатор состояния растения.
Классы читаются из <weights>.classes.json, если файл есть рядом с весами.
"""
import json
import logging
from pathlib import Path
from .resnet_base.custom_weights import CustomWeights

log = logging.getLogger("PlantClassifier")


class PlantClassifier(CustomWeights):
    DEFAULT_CLASSES = ["healthy", "dry", "pest", "flowering"]

    def __init__(self, weights: str, device: str = "cpu"):
        classes = self._load_classes(weights)
        log.info("PlantClassifier: %d классов", len(classes))
        super().__init__(weights=weights, class_names=classes, device=device)
        log.info("PlantClassifier готов, классы: %s", classes[:5])

    def _load_classes(self, weights: str) -> list[str]:
        w = Path(weights)
        meta = w.with_suffix(".classes.json")
        if meta.exists():
            try:
                names = json.loads(meta.read_text(encoding="utf-8"))
                if isinstance(names, list) and names:
                    return names
            except Exception as e:
                log.warning("Не удалось прочитать %s: %s", meta, e)
        log.warning("Не найден %s, использую классы по умолчанию", meta)
        return self.DEFAULT_CLASSES
