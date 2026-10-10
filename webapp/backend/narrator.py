import json
import logging
from pathlib import Path
import requests
from datetime import datetime, timedelta

log = logging.getLogger("narrator")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma2:2b"


class Narrator:
    def __init__(self, diaries_dir: Path):
        self.diaries_dir = diaries_dir

    def _get_recent_context(self, plant_id: int, days: int = 3) -> str:
        """Собирает последние записи дневника для контекста."""
        entries = []
        today = datetime.now().date()
        for i in range(1, days + 1):
            d = today - timedelta(days=i)
            f = self.diaries_dir / f"plant_{plant_id}_{d.isoformat()}.md"
            if f.exists():
                text = f.read_text(encoding="utf-8")
                lines = [ln for ln in text.splitlines()
                         if ln.startswith("- **") or ln.startswith("##")]
                entries.append(f"[{d.isoformat()}]\n" + "\n".join(lines[-8:]))
        if not entries:
            return "Предыдущих записей нет (это первое наблюдение)."
        return "\n\n".join(reversed(entries[-3:]))

    def _build_prompt(self, plant_name: str, time_of_day: str,
                      analysis: dict, history: str) -> str:
        pred = analysis.get("prediction", "не распознано")
        conf = analysis.get("confidence", 0.0)
        parts = []
        if pred != "не распознано":
            parts.append(f"Классификатор: состояние «{pred}», уверенность {conf:.0%}.")
        else:
            raw = analysis.get("raw_prediction", "")
            parts.append(f"Классификатор не уверен (ближайший класс: «{raw}», {conf:.0%}).")
        if "leaf_count" in analysis:
            parts.append(f"Оценка числа листьев: {analysis['leaf_count']}.")
        colors = analysis.get("color_stats") or {}
        if colors:
            cs = ", ".join(f"{k} {v*100:.0f}%" for k, v in colors.items() if v > 0.01)
            if cs:
                parts.append(f"Цвет листвы: {cs}.")

        return f"""Ты — ассистент учёного-ботаника. Составь краткое (3–4 предложения) описание наблюдения за растением.

Растение: {plant_name}
Дата: {datetime.now():%d.%m.%Y}, время: {time_of_day}

Данные с камеры и нейросети:
{chr(10).join('- ' + p for p in parts)}

Предыдущие наблюдения:
{history}

СТРОГИЕ ПРАВИЛА:
1. Используй ТОЛЬКО данные выше. НЕ выдумывай названия сортов, цвета, болезни, которых нет в данных.
2. Если данных мало — напиши прямо: «недостаточно данных для детального описания».
3. Не используй слова: «возможно», «вероятно», «кажется» — пиши только факты.
4. Стиль — сухой, протокольный, без художественных оборотов.
5. Пиши ТОЛЬКО на русском языке.
6. Объём — не больше 4 предложений.
7. Заверши одной строкой: «Вывод: ...» — но только если есть что сказать, иначе пропусти."""

    def describe(self, plant_id: int, plant_name: str, time_of_day: str,
                 analysis: dict) -> str | None:
        """Возвращает текст описания или None при ошибке."""
        try:
            history = self._get_recent_context(plant_id)
            prompt = self._build_prompt(plant_name, time_of_day, analysis, history)

            r = requests.post(
                OLLAMA_URL,
                json={"model": MODEL, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.2, "num_predict": 120, "num_ctx": 1024}},
                timeout=400,
            )
            r.raise_for_status()
            text = r.json().get("response", "").strip()
            if not text:
                log.warning("LLM вернула пустой ответ для plant=%s", plant_id)
                return None
            log.info("LLM-описание готово для plant=%s (%d символов)",
                     plant_id, len(text))
            return text
        except requests.exceptions.ConnectionError:
            log.warning("Ollama недоступна — пропускаю генерацию текста")
            return None
        except Exception as e:
            log.exception("Ошибка LLM: %s", e)
            return None
