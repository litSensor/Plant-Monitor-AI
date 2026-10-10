import re
from pathlib import Path
from .diary import write_summary, _plant_name

DIARY_DIR = Path("data/diaries")


def build_summary(plant_id, plant_names, period_start, period_end):
    diaries = sorted(DIARY_DIR.glob(f"plant_{plant_id}_*.md"))
    counts, states = [], []
    for f in diaries:
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"Листьев.*?:\s*(\d+)", text):
            counts.append(int(m.group(1)))
        for m in re.finditer(r"Состояние.*?:\s*([\w\-]+)", text):
            states.append(m.group(1))
    if not counts and not states:
        stats = "_Недостаточно данных._"
        conclusion = "Наблюдения отсутствуют."
    else:
        avg = sum(counts) / len(counts) if counts else 0
        dominant = max(set(states), key=states.count) if states else "—"
        stats = (f"- Среднее число листьев: {avg:.1f}\n"
                 f"- Доминирующее состояние: {dominant}\n"
                 f"- Всего наблюдений: {len(diaries)}")
        conclusion = ("Устойчивое состояние." if states.count("healthy") > len(states) / 2
                      else "Требуется внимание.")
    return write_summary(plant_id, plant_names, period_start, period_end,
                         stats, conclusion)
