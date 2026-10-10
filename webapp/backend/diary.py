from datetime import datetime, date
from pathlib import Path

DIARY_DIR = Path("data/diaries")


def _plant_name(plant_id, plant_names):
    if plant_names and len(plant_names) >= plant_id:
        n = (plant_names[plant_id - 1] or "").strip()
        if n:
            return n
    return f"Растение #{plant_id}"


def append_entry(plant_id, plant_names, time_of_day, image_rel_path, analysis):
    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    name = _plant_name(plant_id, plant_names)
    path = DIARY_DIR / f"plant_{plant_id}_{date_str}.md"

    is_new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# Дневник наблюдений: {name}\n\n")
            f.write(f"**Дата:** {date_str}\n\n---\n\n")
        f.write(f"## {time_of_day.capitalize()} ({datetime.now():%H:%M})\n\n")
        _write_body(f, analysis, image_rel_path, time_of_day)


def _write_body(f, analysis, image_rel_path, time_of_day):
    pred = analysis.get("prediction", "—")
    conf = analysis.get("confidence")
    raw = analysis.get("raw_prediction")

    if conf is not None:
        f.write(f"- **Состояние:** {pred} (уверенность {conf:.0%})\n")
        if raw and raw != pred:
            f.write(f"- **Ближайший класс модели:** {raw}\n")
    else:
        f.write(f"- **Состояние:** {pred}\n")

    if analysis.get("description"):
        f.write(f"\n> {analysis['description']}\n\n")

    if "leaf_count" in analysis:
        f.write(f"- **Листьев (оценка):** {analysis['leaf_count']}\n")
    colors = analysis.get("color_stats") or {}
    if colors:
        parts = [f"{k} {v*100:.0f}%" for k, v in colors.items() if v > 0.01]
        if parts:
            f.write(f"- **Цвет листвы:** {', '.join(parts)}\n")
    f.write(f"\n![{time_of_day}]({image_rel_path})\n\n---\n\n")


def write_summary(plant_id, plant_names, period_start, period_end,
                  stats_md, conclusion):
    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    name = _plant_name(plant_id, plant_names)
    path = DIARY_DIR / f"plant_{plant_id}_summary_{period_start}_{period_end}.md"
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# Итоговый вывод: {name}\n\n")
        f.write(f"**Период:** {period_start} — {period_end}\n\n")
        f.write(f"## Агрегированные данные\n\n{stats_md}\n\n")
        f.write(f"## Вывод\n\n{conclusion}\n")
    return path


def _parse_daily_file(text: str):
    lines = text.splitlines()
    body = []
    skip = True
    for ln in lines:
        if skip:
            if ln.strip() == "---":
                skip = False
            continue
        body.append(ln)
    return "\n".join(body).strip()


def build_period_diary(start_date, end_date, plant_names, plants_count):
    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)
    out_path = DIARY_DIR / f"period_{start_date}_{end_date}.md"

    with out_path.open("w", encoding="utf-8") as out:
        out.write(f"# Общий дневник наблюдений за период\n\n")
        out.write(f"**Период:** {start_date} — {end_date}\n")
        out.write(f"**Растений:** {plants_count}\n\n---\n\n")

        total = 0
        for pid in range(1, plants_count + 1):
            name = _plant_name(pid, plant_names)
            files = []
            for p in sorted(DIARY_DIR.glob(f"plant_{pid}_*.md")):
                if "_summary_" in p.name:
                    continue
                try:
                    d = date.fromisoformat(p.stem.split("_")[-1])
                except ValueError:
                    continue
                if d_start <= d <= d_end:
                    files.append((d, p))
            files.sort(key=lambda x: x[0])
            if not files:
                continue
            out.write(f"## {name}\n\n")
            for d, p in files:
                body = _parse_daily_file(p.read_text(encoding="utf-8"))
                out.write(f"### {d.isoformat()}\n\n{body}\n\n")
                total += 1
            out.write("---\n\n")
        out.write(f"_Всего наблюдений: {total}._\n")
    return out_path


def append_ai_comment(plant_id, plant_names, text, time_of_day="auto"):
    """Дописать текстовое описание от LLM в конец сегодняшнего дневника."""
    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    name = _plant_name(plant_id, plant_names)
    path = DIARY_DIR / f"plant_{plant_id}_{date_str}.md"

    # Если дневника нет — создаём с заголовком
    if not path.exists():
        with path.open("w", encoding="utf-8") as f:
            f.write(f"# Дневник наблюдений: {name}\n\n")
            f.write(f"**Дата:** {date_str}\n\n---\n\n")

    with path.open("a", encoding="utf-8") as f:
        f.write(f"## 🤖 Описание (LLM, {datetime.now():%H:%M})\n\n")
        f.write(f"{text}\n\n---\n\n")
    return path

