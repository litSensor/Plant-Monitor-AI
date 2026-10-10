"""Простой классификатор на ResNet-18 без обёрток PyTorch-Wildlife."""
import json
import logging
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

log = logging.getLogger("classifier")


class SimpleClassifier:
    def __init__(self, weights: str, classes_json: str | None = None,
                 device: str = "cpu"):
        self.device = torch.device(device)
        self.classes = self._load_classes(weights, classes_json)

        m = models.resnet18(weights=None)
        m.fc = nn.Linear(m.fc.in_features, len(self.classes))
        state = torch.load(weights, map_location="cpu")
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        m.load_state_dict(state)
        self.model = m.to(self.device).eval()

        self.preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225]),
        ])
        log.info("SimpleClassifier загружен: %d классов", len(self.classes))

    def _load_classes(self, weights: str, classes_json: str | None):
        path = Path(classes_json) if classes_json else \
               Path(weights).with_suffix(".classes.json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"Не найден список классов: {path}")

    @torch.no_grad()
    def predict(self, image_path: str) -> dict:
        img = Image.open(image_path).convert("RGB")
        x = self.preprocess(img).unsqueeze(0).to(self.device)
        logits = self.model(x)
        probs = torch.nn.functional.softmax(logits, dim=1)[0]
        conf, idx = torch.max(probs, 0)
        return {
            "prediction": self.classes[int(idx)],
            "confidence": float(conf),
        }
