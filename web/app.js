'use strict';
const $ = id => document.getElementById(id);
let session, files = [], texts = [], mode = 'send', type = 'files', transfers = [];
let running = false, stopped = false, refreshing = false, revision = 0, toastTimer;
let events, waiting = true, lastConnection = [false, t("Подключение…")];
let ipHidden = false;
try { ipHidden = localStorage.getItem('ryadom-hide-ip') === 'true'; } catch { /* Use the default if storage is unavailable. */ }

function renderAddresses() {
  if (session?.role !== 'host') return;
  const select = $('address');
  select.replaceChildren();
  for (const [index, address] of session.addresses.entries()) {
    const label = ipHidden ? t('Адрес ') + (index + 1) + ' · •••.•••.•••.•••:' + session.port : address + ':' + session.port;
    const option = node('option', '', label); option.value = address; select.append(option);
  }
  select.value = session.address;
  const label = t(ipHidden ? 'Показать IP-адрес' : 'Скрыть IP-адрес');
  $('toggle-ip').setAttribute('aria-label', label);
  $('toggle-ip').setAttribute('aria-pressed', String(ipHidden));
  $('toggle-ip').title = label;
}

function size(bytes) {
  if (!bytes) return t('0 Б');
  const units = [t('Б'), t('КБ'), t('МБ'), t('ГБ')];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), 3);
  return new Intl.NumberFormat(i18n.language, {maximumFractionDigits: i > 1 ? 1 : 0}).format(bytes / 1024 ** i) + ' ' + units[i];
}
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function toast(message) {
  clearTimeout(toastTimer); $('toast').textContent = message; $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5500);
}
function connection(online, label) {
  lastConnection = [online, label];
  $('status-dot').className = 'dot ' + (online ? 'online' : 'offline');
  $('connection-text').textContent = t(label);
}
function setPairing(value) {
  if (session?.role !== 'host') return;
  const changed = waiting !== value;
  waiting = value;
  document.body.classList.toggle('waiting', value);
  $('pairing-view').hidden = !value;
  $('layout').hidden = value;
  if (changed && $('connection-settings').open) $('connection-settings').close();
}
function disconnect() {
  if (stopped) return;
  stopped = true;
  events?.close();
  for (const task of transfers) task.xhr?.abort();
  files = []; texts = []; transfers = []; revision++;
  $('file-list').replaceChildren(); $('text-list').replaceChildren(); $('transfer-list').replaceChildren();
  $('text-input').value = ''; $('file-input').value = '';
  $('layout').hidden = true; $('pairing-view').hidden = true; $('fatal').hidden = true; $('toast').hidden = true;
  $('settings').hidden = true;
  if ($('connection-settings').open) $('connection-settings').close();
  document.body.classList.remove('waiting'); document.body.classList.add('disconnected');
  $('disconnected-view').hidden = false;
}
function connectEvents() {
  events = new EventSource('/api/events');
  events.addEventListener('state', event => {
    if (stopped) return;
    if (session.role === 'host') setPairing(!JSON.parse(event.data).paired);
    refresh();
  });
  events.addEventListener('revoked', disconnect);
  events.onerror = () => { if (!stopped) refresh(); };
}
async function api(path, body) {
  const options = {cache: 'no-store'};
  if (body !== undefined) {
    options.method = 'POST';
    options.headers = {'X-Ryadom-CSRF': session.csrf, 'Content-Type': 'application/json'};
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) disconnect();
    throw new Error(t(data.error) || t('Не удалось выполнить действие'));
  }
  return data;
}
function setTabs(prefix, values, selected) {
  for (const value of values) {
    const el = $(prefix + '-' + value);
    el.classList.toggle('active', value === selected);
    el.setAttribute('aria-selected', String(value === selected));
    el.tabIndex = value === selected ? 0 : -1;
  }
}
function selectMode(value) {
  mode = value; setTabs('mode', ['send', 'receive'], value);
  $('workspace').setAttribute('aria-labelledby', 'mode-' + value);
  render();
}
function selectType(value) {
  type = value; setTabs('type', ['files', 'text'], value);
  $('content-panel').setAttribute('aria-labelledby', 'type-' + value);
  render();
}
function render() {
  if (!session || stopped) return;
  const outgoing = mode === 'send', fileType = type === 'files';
  const visible = files.filter(f => f.direction === mode);
  const visibleTexts = texts.filter(t => t.direction === mode);
  $('receive-count').textContent = files.filter(f => f.direction === 'receive').length + texts.filter(t => t.direction === 'receive').length;
  $('files-count').textContent = visible.length; $('texts-count').textContent = visibleTexts.length;
  $('dropzone').hidden = !outgoing || !fileType;
  $('text-form').hidden = !outgoing || fileType;
  $('file-list').hidden = !fileType; $('text-list').hidden = fileType;
  $('open-folder').hidden = session.role !== 'host' || outgoing || !fileType;
  $('file-footnote').hidden = session.role !== 'host' || outgoing || !fileType;
  if (!$('file-footnote').hidden) $('file-footnote').textContent = session.storage;
  const hasData = fileType ? visible.length : visibleTexts.length;
  $('empty').hidden = hasData > 0 || (outgoing && !fileType);
  $('empty-title').textContent = fileType ? (outgoing ? t('Нет добавленных файлов') : t('Пока ничего не получено')) : t('Пока нет текста');
  $('empty-copy').textContent = outgoing ? t('Выберите файлы для передачи') : (session.role === 'host' ? t('Отправьте ') + (fileType ? t('файлы') : t('текст')) + t(' с телефона') : t('Отправьте ') + (fileType ? t('файлы') : t('текст')) + t(' из панели на ПК'));
  renderFiles(visible); renderTexts(visibleTexts); renderTransfers();
}
function renderFiles(visible) {
  const list = $('file-list');
  const signature = JSON.stringify([i18n.language, mode, visible]);
  if (list.dataset.signature === signature) return;
  list.dataset.signature = signature; list.replaceChildren();
  for (const file of visible) {
    const row = node('div', 'file-row');
    row.dataset.id = file.id;
    const extension = file.name.includes('.') ? file.name.split('.').pop().slice(0, 5) : 'FILE';
    row.append(node('span', 'file-icon', extension));
    const info = node('div', 'file-info');
    const name = node('div', 'file-name', file.name); name.title = file.name;
    info.append(name, node('div', 'file-meta', size(file.size) + ' · ' + new Date(file.created * 1000).toLocaleTimeString(i18n.language, {hour: '2-digit', minute: '2-digit'})));
    row.append(info);
    if (mode === 'receive') {
      const download = node('a', 'file-action', t('Скачать ↓'));
      download.href = '/download/' + file.id; download.download = file.name;
      download.setAttribute('aria-label', t('Скачать ') + file.name); row.append(download);
    }
    const deleting = file.removal === 'delete';
    const remove = node('button', 'file-action remove', deleting ? t('Удалить') : t('Убрать'));
    remove.type = 'button';
    remove.setAttribute('aria-label', (deleting ? t('Удалить файл ') : t('Убрать файл ')) + file.name);
    remove.title = deleting ? t('Удалить из папки полученных на ПК') : session.role === 'host' ? t('Убрать из передачи') : t('Убрать из списка на этом устройстве');
    remove.onclick = async () => {
      if (deleting && !window.confirm(t('Удалить «') + file.name + t('» из папки полученных файлов на компьютере?'))) return;
      remove.disabled = true;
      try {
        await api('/api/remove/' + file.id, deleting ? {delete: true} : {});
        revision++; files = files.filter(f => f.id !== file.id); render();
        if (session.role === 'guest' && mode === 'send') toast(t('Убрано из списка. Отправленный файл остался на ПК'));
      } catch (error) { toast(error.message); remove.disabled = false; }
    };
    row.append(remove); list.append(row);
  }
}
async function copyText(text, field) {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); toast(t('Скопировано')); return; }
    catch { /* Keep a manual selection available if clipboard permission is denied. */ }
  }
  const temporary = !field;
  const target = field || node('textarea');
  if (temporary) { target.value = text; target.className = 'copy-fallback'; document.body.append(target); }
  const active = document.activeElement;
  target.focus(); target.select(); target.setSelectionRange(0, target.value.length);
  let copied = false;
  try { copied = document.execCommand('copy'); } catch { /* Browser may block legacy copying. */ }
  if (temporary) target.remove();
  if (copied) { active?.focus({preventScroll: true}); toast(t('Скопировано')); }
  else toast(field ? t('Текст выделен. Скопируйте его через меню браузера') : t('Не удалось скопировать. Используйте QR-код'));
}
function renderTexts(visible) {
  const list = $('text-list');
  const signature = JSON.stringify([i18n.language, mode, visible]);
  if (list.dataset.signature === signature) return;
  list.dataset.signature = signature; list.replaceChildren();
  for (const message of visible) {
    const row = node('div', 'text-row'); row.dataset.id = message.id;
    const field = node('textarea'); field.value = message.text; field.readOnly = true;
    field.rows = Math.min(7, Math.max(3, message.text.split('\n').length + 1));
    field.setAttribute('aria-label', mode === 'send' ? t('Отправленный текст') : t('Полученный текст'));
    const actions = node('div', 'text-actions');
    actions.append(node('span', 'file-meta', new Date(message.created * 1000).toLocaleTimeString(i18n.language, {hour: '2-digit', minute: '2-digit'})));
    const buttons = node('div', 'buttons');
    const copy = node('button', 'text-button', t('Скопировать')); copy.type = 'button';
    copy.onclick = () => copyText(message.text, field);
    const remove = node('button', 'text-button', t('Убрать')); remove.type = 'button';
    remove.setAttribute('aria-label', t('Убрать текст'));
    remove.onclick = async () => {
      remove.disabled = true;
      try { await api('/api/text/remove/' + message.id, {}); revision++; texts = texts.filter(t => t.id !== message.id); render(); }
      catch (error) { toast(error.message); remove.disabled = false; }
    };
    buttons.append(copy, remove); actions.append(buttons); row.append(field, actions); list.append(row);
  }
}
function renderTransfers() {
  const tasks = transfers.filter(t => t.state !== 'done');
  $('transfers').hidden = !tasks.length || mode !== 'send' || type !== 'files';
  $('clear-completed').hidden = !tasks.some(t => ['cancelled', 'error'].includes(t.state));
  const list = $('transfer-list'); list.replaceChildren();
  for (const task of tasks) {
    const row = node('div', 'transfer-row' + (task.state === 'error' ? ' error' : ''));
    const header = node('div', 'transfer-header'); header.append(node('span', 'transfer-name', task.file.name));
    const active = ['sending', 'saving', 'queued'].includes(task.state);
    if (active) {
      const cancel = node('button', 'text-button', t('Отмена')); cancel.type = 'button';
      cancel.onclick = () => { task.state = 'cancelled'; task.xhr?.abort(); renderTransfers(); };
      header.append(cancel);
    } else {
      const retry = node('button', 'text-button', t('Повторить')); retry.type = 'button'; retry.disabled = stopped;
      retry.onclick = () => { task.state = 'queued'; task.loaded = 0; task.error = ''; renderTransfers(); processQueue(); };
      const remove = node('button', 'text-button', t('Убрать')); remove.type = 'button';
      remove.setAttribute('aria-label', t('Убрать запись ') + task.file.name);
      remove.onclick = () => { transfers = transfers.filter(t => t !== task); renderTransfers(); };
      header.append(retry, remove);
    }
    const labels = {queued: t('В очереди'), sending: t('Передаётся'), saving: t('Сохраняется…'), cancelled: t('Отменено'), error: task.error};
    const meta = node('div', 'transfer-meta');
    meta.append(node('span', '', labels[task.state]), node('span', '', task.state === 'sending' ? size(task.loaded) + ' / ' + size(task.file.size) : size(task.file.size)));
    row.append(header, meta);
    if (['sending', 'saving'].includes(task.state)) {
      const progress = node('progress'); progress.max = task.file.size || 1; progress.value = task.loaded;
      progress.setAttribute('aria-label', t('Передача ') + task.file.name); row.append(progress);
    }
    list.append(row);
  }
}
function enqueue(fileList) {
  if (!session || stopped || !fileList.length) return;
  selectMode('send'); selectType('files');
  for (const file of fileList) {
    if (/^(?:\.DS_Store|Thumbs\.db|desktop\.ini)$|^\._|^\.ryadom-/i.test(file.name)) continue;
    if (file.size > session.maxBytes) { toast(file.name + t(': размер больше ') + size(session.maxBytes)); continue; }
    transfers.push({file, state: 'queued', loaded: 0, error: ''});
  }
  renderTransfers(); processQueue();
}
async function processQueue() {
  if (running || stopped) return;
  running = true;
  try {
    let task;
    while (!stopped && (task = transfers.find(t => t.state === 'queued'))) {
      task.state = 'sending'; renderTransfers();
      await new Promise(resolve => {
        const xhr = new XMLHttpRequest(); task.xhr = xhr;
        xhr.open('POST', '/api/upload');
        xhr.setRequestHeader('X-Ryadom-CSRF', session.csrf);
        xhr.setRequestHeader('X-File-Name', encodeURIComponent(task.file.name));
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');
        let lastPaint = 0;
        xhr.upload.onprogress = event => {
          if (task.state === 'cancelled') return;
          task.loaded = event.loaded;
          if (event.loaded === task.file.size) task.state = 'saving';
          if (performance.now() - lastPaint > 100 || task.state === 'saving') { renderTransfers(); lastPaint = performance.now(); }
        };
        xhr.onload = () => {
          if (xhr.status === 201) {
            task.state = 'done'; task.loaded = task.file.size;
            const file = JSON.parse(xhr.responseText).file;
            revision++; files.unshift({...file, direction: 'send', removal: 'remove'}); render();
          } else {
            task.state = 'error';
            try { task.error = t(JSON.parse(xhr.responseText).error); } catch { task.error = t('Не удалось передать файл'); }
            if (xhr.status === 401) disconnect();
          }
          resolve();
        };
        xhr.onerror = () => { task.state = 'error'; task.error = t('Нет связи. Проверьте сеть и повторите'); resolve(); };
        xhr.onabort = () => { task.state = 'cancelled'; resolve(); };
        xhr.send(task.file);
      });
      delete task.xhr; transfers = transfers.filter(t => t.state !== 'done'); renderTransfers();
      await refresh();
    }
  } finally { running = false; }
}
async function refresh() {
  if (stopped || refreshing) return;
  refreshing = true;
  const atRevision = revision;
  try {
    const data = await api('/api/files');
    if (atRevision === revision) { files = data.files; texts = data.texts; render(); }
    if (stopped) return;
    if (session.role === 'host') setPairing(!data.paired);
    connection(true, session.role === 'guest' || data.connected ? t('Подключено') : t('Ждём подключения'));
  } catch { if (!stopped) connection(false, t('Нет подключения')); }
  finally { refreshing = false; }
}
async function refreshCode() {
  if (session?.role !== 'host' || stopped) return;
  try {
    const data = await api('/api/code');
    $('pair-code').textContent = $('waiting-code').textContent = data.code.slice(0, 3) + ' ' + data.code.slice(3);
    const seconds = Math.max(0, Math.min(15, data.seconds));
    $('code-countdown').textContent = $('waiting-countdown').textContent = t('Новый код через ') + seconds + t(' с');
    for (const arc of document.querySelectorAll('.timer-arc')) arc.setAttribute('stroke-dashoffset', String((15 - seconds) / 15 * 100));
  } catch {
    $('code-countdown').textContent = $('waiting-countdown').textContent = t('Не удалось обновить код');
    for (const arc of document.querySelectorAll('.timer-arc')) arc.setAttribute('stroke-dashoffset', '100');
  }
}
function updateTextSize() {
  const bytes = new TextEncoder().encode($('text-input').value).length;
  $('text-size').textContent = size(bytes) + t(' / 64 КБ');
  $('send-text').disabled = stopped || !$('text-input').value.trim() || bytes > (session?.maxTextBytes || 65536);
}
async function init() {
  try {
    session = await api('/api/session');
    $('version').textContent = t('Рядом ') + session.version;
    $('file-limit').textContent = t('До ') + size(session.maxBytes) + t(' на файл');
    if (session.role === 'host') {
      setPairing(true);
      $('settings').hidden = false;
      $('qr').src = $('waiting-qr').src = '/api/qr';
      renderAddresses();
      await refreshCode(); setInterval(refreshCode, 1000);
    } else {
      waiting = false; $('layout').hidden = false;
      $('layout').classList.add('guest');
      $('drop-title').textContent = t('Фото, видео, документы');
    }
    updateTextSize(); await refresh(); connectEvents(); setInterval(refresh, 1000);
  } catch {
    if (!stopped) { $('fatal').textContent = t('Откройте программу на ПК и подключитесь через QR-код заново'); $('fatal').hidden = false; connection(false, t('Нет подключения')); }
  }
}
$('choose').onclick = () => $('file-input').click();
$('file-input').onchange = e => { enqueue(e.target.files); e.target.value = ''; };
for (const value of ['send', 'receive']) $('mode-' + value).onclick = () => selectMode(value);
for (const value of ['files', 'text']) $('type-' + value).onclick = () => selectType(value);
for (const [id, prefix, values, select] of [['modes', 'mode', ['send', 'receive'], selectMode], ['types', 'type', ['files', 'text'], selectType]]) {
  $(id).onkeydown = e => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault(); const current = prefix === 'mode' ? mode : type;
    const value = e.key === 'Home' ? values[0] : e.key === 'End' ? values[1] : values.find(v => v !== current);
    select(value); $(prefix + '-' + value).focus();
  };
}
$('text-input').oninput = updateTextSize;
$('text-form').onsubmit = async e => {
  e.preventDefault(); if ($('send-text').disabled) return;
  const text = $('text-input').value; $('send-text').disabled = true;
  try {
    const result = await api('/api/text', {text});
    revision++; texts.unshift({id: result.id, text, direction: 'send', created: Date.now() / 1000});
    if ($('text-input').value === text) $('text-input').value = '';
    render(); toast(t('Текст отправлен'));
  } catch (error) { toast(error.message); }
  finally { updateTextSize(); }
};
$('clear-completed').onclick = () => { transfers = transfers.filter(t => ['queued', 'sending', 'saving'].includes(t.state)); renderTransfers(); };
$('open-folder').onclick = async () => { try { await api('/api/open-folder', {}); } catch (e) { toast(e.message); } };
$('copy-link').onclick = () => copyText(session.joinUrl);
$('address').onchange = async e => {
  try { const data = await api('/api/address', {address: e.target.value}); session.address = e.target.value; session.joinUrl = data.joinUrl; $('qr').src = $('waiting-qr').src = '/api/qr?t=' + Date.now(); }
  catch (error) { $('address').value = session.address; toast(error.message); }
};
$('rotate').onclick = async () => {
  if (!window.confirm(t('Отключить все устройства и создать новый QR-код?'))) return;
  try { const data = await api('/api/rotate', {}); session.joinUrl = data.joinUrl; $('qr').src = $('waiting-qr').src = '/api/qr?t=' + Date.now(); setPairing(true); if ($('connection-settings').open) $('connection-settings').close(); await refreshCode(); await refresh(); }
  catch (error) { toast(error.message); }
};
let dragDepth = 0;
document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => { e.preventDefault(); dragDepth = 0; $('dropzone').classList.remove('dragging'); enqueue(e.dataTransfer.files); });
$('dropzone').addEventListener('dragenter', e => { e.preventDefault(); dragDepth++; $('dropzone').classList.add('dragging'); });
$('dropzone').addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('dropzone').classList.remove('dragging'); } });
window.addEventListener('beforeunload', e => { if (transfers.some(t => ['sending', 'saving', 'queued'].includes(t.state))) { e.preventDefault(); e.returnValue = ''; } });
document.addEventListener('visibilitychange', () => { if (!document.hidden) { refresh(); refreshCode(); } });
$('settings').onclick = () => $('connection-settings').showModal();
$('toggle-ip').onclick = () => {
  ipHidden = !ipHidden;
  try { localStorage.setItem('ryadom-hide-ip', String(ipHidden)); } catch { /* Keep the in-memory choice. */ }
  renderAddresses();
};
$('close-settings').onclick = () => $('connection-settings').close();
$('connection-settings').addEventListener('click', event => {
  if (event.target !== $('connection-settings')) return;
  const box = event.target.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close();
});
window.addEventListener('languagechange', () => {
  connection(...lastConnection);
  if (!session) return;
  renderAddresses();
  $('version').textContent = t('Рядом ') + session.version;
  $('file-limit').textContent = t('До ') + size(session.maxBytes) + t(' на файл');
  $('drop-title').textContent = session.role === 'guest' ? t('Фото, видео, документы') : t('Перетащите файлы сюда');
  $('toast').hidden = true; render(); updateTextSize(); refreshCode();
});
window.addEventListener('pageshow', event => { if (event.persisted && session) refresh(); });
init();
