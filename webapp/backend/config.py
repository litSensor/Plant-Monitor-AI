from pydantic import BaseModel, Field
from typing import Literal


class CameraCfg(BaseModel):
    type: Literal["usb", "rtsp"] = "usb"
    devices: list[str] = []
    urls: list[str] = []
    resolution: tuple[int, int] = (1920, 1080)
    warmup_frames: int = 8
    settle_sec: float = 1.0


class ScheduleCfg(BaseModel):
    morning: str = "08:00"
    evening: str = "20:00"
    timezone: str = "Europe/Moscow"


class AnalysisCfg(BaseModel):
    enabled: bool = False
    model_dir: str = "models"
    plant_classifier_weights: str = "models/plant_classifier.pth"
    leaf_seg_weights: str = "models/leaf_seg.pt"
    # Порог уверенности: если включён, то при conf < min_confidence
    # в дневник пишется "не распознано"
    use_confidence_threshold: bool = False
    use_llm: bool = False
    min_confidence: float = 0.4


class AppConfig(BaseModel):
    plants_count: int = Field(1, ge=1, le=10)
    plant_names: list[str] = []
    schedule: ScheduleCfg = ScheduleCfg()
    camera: CameraCfg = CameraCfg()
    analysis: AnalysisCfg = AnalysisCfg()
