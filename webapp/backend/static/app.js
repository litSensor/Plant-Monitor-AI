const $ = id => document.getElementById(id);

let currentConfig = null;
let detectedCameras = [];
let currentStreamPlant = null;

async function loadConfig() {
  currentConfig = await (await fetch('/api/config')).json();
  $('plants').value = currentConfig.plants_count;
  $('morning').value = currentConfig.schedule.morning;
  $('evening').value = currentConfig.schedule.evening;
  $('tz').value = currentConfig.schedule.timezone;

  const a = currentConfig.analysis || {};
  $('useThreshold').checked = !!a.use_confidence_threshold;
  $('useLlm').checked = !!a.use_llm;
  $('minConf').value = a.min_confidence ?? 0.4;

  renderNameInputs();
  await refreshCameras();
  updatePlantLimit();
  await refreshHealth();
}

async function refreshHealth() {
  try {
    const h = await (await fetch('/api/health')).json();
    const bar = $('health');
    const usedPct = (h.disk_used_gb / h.disk_total_gb * 100).toFixed(0);
    const ps = h.photos_size || {value: 0, unit: 'КБ'};
    const ds = h.diaries_size || {value: 0, unit: 'КБ'};
    bar.innerHTML =
      `💾 Диск: <b>${h.disk_free_gb} ГБ свободно</b> ` +
      `(${usedPct}% занято) &nbsp;·&nbsp; ` +
      `📷 Фото: <b>${h.photos_count}</b> (${ps.value} ${ps.unit}) &nbsp;·&nbsp; ` +
      `📝 Дневники: <b>${h.diaries_count}</b> (${ds.value} ${ds.unit})`;
  } catch (e) {}
}

function renderNameInputs() {
  const block = $('plantNames');
  const n = +$('plants').value;
  const saved = currentConfig?.plant_names || [];
  block.innerHTML = '';
  for (let i = 1; i <= n; i++) {
    const wrap = document.createElement('label');
    wrap.style.display = 'block';
    wrap.textContent = `Растение #${i}: `;
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.placeholder = 'напр. Дуб, Сирень (необязательно)';
    inp.value = saved[i - 1] || '';
    inp.dataset.idx = i - 1;
    inp.className = 'name-input';
    wrap.appendChild(inp);
    block.appendChild(wrap);
  }
}

function collectNames() {
  return [...document.querySelectorAll('.name-input')]
    .map(i => (i.value || '').trim());
}

async function refreshCameras() {
  $('camCount').textContent = '…';
  try {
    const data = await (await fetch('/api/cameras')).json();
    detectedCameras = data.cameras || [];
    $('camCount').textContent = data.count;
    const ul = $('camList');
    ul.innerHTML = '';
    detectedCameras.forEach(c => {
      const li = document.createElement('li');
      li.className = c.ok ? 'ok' : 'fail';
      const res = c.resolution ? `${c.resolution[0]}×${c.resolution[1]}` : '—';
      li.textContent = `${c.ok ? '✓' : '✗'} ${c.path}  ${res}`;
      ul.appendChild(li);
    });
  } catch { $('camCount').textContent = '?'; }
}

function updatePlantLimit() {
  const max = detectedCameras.filter(c => c.ok).length || 10;
  $('plants').max = max;
  if (+$('plants').value > max) $('plants').value = max;
}

// ---------- Быстрые действия ----------
$('snapAll').onclick = async () => {
  if (!confirm('Сделать снимок всех растений и записать в дневник?')) return;
  $('quickResult').textContent = 'Съёмка всех растений...';
  try {
    const r = await fetch('/api/snapshot_all?time_of_day=morning', {method: 'POST'});
    const d = await r.json();
    $('quickResult').textContent = r.ok
      ? `Готово. Снято растений: ${d.plants}`
      : 'Ошибка.';
  } catch (e) { $('quickResult').textContent = 'Ошибка: ' + e; }
  await refreshHealth();
  refreshDiaries();
};

$('downloadAll').onclick = () => {
  window.location.href = '/api/download/archive';
};

// ---------- Трансляция ----------
async function stopStream() {
  const box = $('streamBox');
  const img = box.querySelector('img');
  if (img) { img.src = ''; img.remove(); }
  if (currentStreamPlant !== null) {
    try {
      await fetch(`/api/camera/stream/stop/${currentStreamPlant}`, {method: 'POST'});
    } catch (e) {}
    currentStreamPlant = null;
  }
}

$('streamStart').onclick = async () => {
  await stopStream();
  const pid = +$('streamPlant').value;
  currentStreamPlant = pid;
  const box = $('streamBox');
  box.innerHTML = '';
  const img = document.createElement('img');
  img.className = 'preview-img';
  img.alt = 'Трансляция с камеры ' + pid;
  img.src = `/api/camera/stream/${pid}?t=${Date.now()}`;
  img.onerror = () => {
    box.innerHTML = '<span class="hint">Не удалось открыть поток. Камера занята?</span>';
    currentStreamPlant = null;
  };
  box.appendChild(img);
};

$('streamStop').onclick = async () => {
  await stopStream();
  $('streamBox').innerHTML = '<span class="hint">Трансляция остановлена.</span>';
};

// ---------- Галерея ----------
$('galleryLoad').onclick = async () => {
  const pid = +$('galleryPlant').value;
  const grid = $('galleryGrid');
  grid.innerHTML = '<span class="hint">Загрузка...</span>';
  try {
    const data = await (await fetch(`/api/photos/${pid}`)).json();
    $('galleryCount').textContent = `(${data.count} фото)`;
    grid.innerHTML = '';
    if (!data.count) {
      grid.innerHTML = '<span class="hint">Фото пока нет.</span>';
      return;
    }
    data.photos.forEach(p => {
      const wrap = document.createElement('div');
      wrap.className = 'gallery-item';
      const img = document.createElement('img');
      img.src = p.url;
      img.loading = 'lazy';
      img.alt = p.name;
      img.onclick = () => openLightbox(p.url);
      const meta = document.createElement('div');
      meta.className = 'gallery-meta';
      meta.textContent = p.mtime.replace('T', ' ').slice(5, 16);
      wrap.appendChild(img);
      wrap.appendChild(meta);
      grid.appendChild(wrap);
    });
  } catch (e) {
    grid.innerHTML = '<span class="hint">Ошибка загрузки.</span>';
  }
};

function openLightbox(url) {
  $('lightboxImg').src = url;
  $('lightbox').style.display = 'flex';
}
$('lightbox').onclick = () => {
  $('lightbox').style.display = 'none';
  $('lightboxImg').src = '';
};

// ---------- Обработчики ----------
$('checkCameras').onclick = async () => {
  await refreshCameras();
  updatePlantLimit();
};

$('plants').addEventListener('input', () => {
  updatePlantLimit();
  renderNameInputs();
});

$('save').onclick = async () => {
  const cfg = await (await fetch('/api/config')).json();
  cfg.plants_count = +$('plants').value;
  cfg.plant_names = collectNames();
  cfg.schedule.morning = $('morning').value;
  cfg.schedule.evening = $('evening').value;
  cfg.schedule.timezone = $('tz').value;
  cfg.analysis = cfg.analysis || {};
  cfg.analysis.use_confidence_threshold = $('useThreshold').checked;
  cfg.analysis.use_llm = $('useLlm').checked;
  cfg.analysis.min_confidence = parseFloat($('minConf').value) || 0.4;

  const r = await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(cfg),
  });
  if (r.ok) {
    currentConfig = cfg;
    alert('Настройки сохранены.');
  } else {
    const err = await r.json().catch(() => ({}));
    alert('Ошибка: ' + (err.detail || r.statusText));
  }
};

$('snap').onclick = async () => {
  $('log').textContent = 'Съёмка...';
  try {
    const r = await fetch(
      `/api/snapshot/${+$('manualPlant').value}?time_of_day=${$('manualTime').value}`,
      {method: 'POST'}
    );
    $('log').textContent = r.ok ? 'Готово.' : 'Ошибка: ' + r.status;
  } catch (e) { $('log').textContent = 'Ошибка: ' + e; }
  await refreshHealth();
  refreshDiaries();
};

$('snapOnly').onclick = async () => {
  $('log').textContent = 'Съёмка без записи в дневник...';
  try {
    const r = await fetch(`/api/photo_only/${+$('manualPlant').value}`,
                          {method: 'POST'});
    const d = await r.json();
    $('log').textContent = r.ok
      ? 'Готово. Фото: ' + d.file
      : 'Ошибка: ' + (d.detail || r.status);
  } catch (e) {
    $('log').textContent = 'Ошибка: ' + e;
  }
  await refreshHealth();
};

$('describeBtn').onclick = async () => {
  const pid = +$('manualPlant').value;
  $('log').textContent =
    '🤖 LLM генерирует описание (1-3 минуты)... Подождите.';
  try {
    const r = await fetch(`/api/describe_last/${pid}`, {method: 'POST'});
    const d = await r.json();
    if (r.ok) {
      $('log').textContent = '✅ Готово. Текст дописан в дневник.';
      refreshDiaries();
    } else {
      $('log').textContent = '❌ Ошибка: ' + (d.detail || r.status);
    }
  } catch (e) {
    $('log').textContent = '❌ Ошибка: ' + e;
  }
  await refreshHealth();
};

// ---------- Логи ----------
let logsTimer = null;

async function loadLogs() {
  const box = $('logsBox');
  try {
    const r = await fetch('/api/logs?lines=200');
    const d = await r.json();
    box.textContent = (d.lines || []).join('\n') || 'Пусто.';
    box.scrollTop = box.scrollHeight;
  } catch (e) {
    box.textContent = 'Ошибка загрузки: ' + e;
  }
}

$('logsLoad').onclick = loadLogs;

$('logsAuto').addEventListener('change', () => {
  if (logsTimer) { clearInterval(logsTimer); logsTimer = null; }
  if ($('logsAuto').checked) {
    loadLogs();
    logsTimer = setInterval(loadLogs, 10_000);
  }
});

$('makePeriod').onclick = async () => {
  const s = $('perStart').value, e = $('perEnd').value;
  if (!s || !e) { alert('Укажите период.'); return; }
  const r = await fetch(`/api/period_diary?start=${s}&end=${e}`, {method: 'POST'});
  if (r.ok) {
    const d = await r.json();
    $('periodResult').textContent = 'Создан: ' + d.file;
    refreshDiaries();
  } else {
    const err = await r.json().catch(() => ({}));
    $('periodResult').textContent = 'Ошибка: ' + (err.detail || r.status);
  }
};

$('makeSummary').onclick = async () => {
  const s = $('sumStart').value, e = $('sumEnd').value;
  if (!s || !e) { alert('Укажите период.'); return; }
  const r = await fetch(
    `/api/summary/${+$('sumPlant').value}?start=${s}&end=${e}`,
    {method: 'POST'}
  );
  if (r.ok) {
    const d = await r.json();
    $('summaryResult').textContent = 'Создан: ' + d.file;
    refreshDiaries();
  } else {
    $('summaryResult').textContent = 'Ошибка.';
  }
};

async function refreshDiaries() {
  const list = await (await fetch('/api/diaries')).json();
  const ul = $('diaryList');
  ul.innerHTML = '';
  list.forEach(name => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = name;
    a.onclick = async ev => {
      ev.preventDefault();
      const text = await (await fetch(`/api/diaries/${name}`)).text();
      $('diaryView').innerHTML = renderMarkdown(text);
    };
    li.appendChild(a);
    ul.appendChild(li);
  });
}

function renderMarkdown(md) {
  return md
    .replace(/!\[(.*?)\]\((.*?)\)/g, '<img alt="$1" src="$2">')
    .replace(/^### (.*)$/gm, '<h3>$1</h3>')
    .replace(/^## (.*)$/gm, '<h2>$1</h2>')
    .replace(/^# (.*)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
    .replace(/\n/g, '<br>');
}

window.addEventListener('beforeunload', () => {
  if (currentStreamPlant !== null) {
    navigator.sendBeacon(`/api/camera/stream/stop/${currentStreamPlant}`);
  }
});

loadConfig();
refreshDiaries();
