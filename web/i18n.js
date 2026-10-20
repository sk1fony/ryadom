'use strict';
(() => {
  const en = {
    'рядом.':'ryadom.', 'Рядом ':'Ryadom ', 'Передача':'Transfer', 'Отправить':'Send', 'Получить':'Receive',
    'Файлы':'Files', 'Текст':'Text', 'Подключение':'Connection', 'Подключение…':'Connecting…',
    'Подключено':'Connected', 'Ждём подключения':'Waiting for a device', 'Нет подключения':'Disconnected',
    'Отсканируйте QR-код повторно':'Scan the QR code again', 'Введите код':'Enter code', 'Подключиться':'Connect',
    'Закрыть':'Close', 'QR-код для подключения':'Connection QR code', 'Код подключения':'Connection code',
    'Отсканируйте QR и введите код на телефоне':'Scan the QR and enter the code on your phone',
    'Скопировать ссылку':'Copy link', 'Адрес компьютера':'Computer address', 'Не получается подключиться?':'Can’t connect?',
    'Адрес ':'Address ', 'Показать IP-адрес':'Show IP address', 'Скрыть IP-адрес':'Hide IP address',
    'Служебный файл не передаётся':'System metadata files are not shared',
    'Сетевая справка':'Use the same network. If your VPN blocks local connections, allow LAN access in its settings. On Windows, allow Python through the firewall for private networks. Guest Wi-Fi may isolate devices.',
    'Отключить устройства и обновить QR':'Disconnect devices and refresh QR', 'Направление передачи':'Transfer direction',
    'Тип данных':'Content type', 'Добавление файлов':'Add files', 'Открыть папку ↗':'Open folder ↗',
    'Перетащите файлы сюда':'Drop files here', 'Выбрать файлы':'Choose files', 'Текст для отправки':'Text to send',
    'Вставьте ссылку, заметку или другой текст':'Paste a link, note or other text', 'Отправить текст ↑':'Send text ↑',
    'Передача файлов':'File transfer', 'Убрать завершённые':'Clear finished', 'Нет добавленных файлов':'No files added',
    'Пока ничего не получено':'Nothing received yet', 'Пока нет текста':'No text yet',
    'Выберите файлы для передачи':'Choose files to share', 'Отправьте ':'Send ', 'файлы':'files', 'текст':'text',
    ' с телефона':' from your phone', ' из панели на ПК':' from the computer panel',
    'Скачать ↓':'Download ↓', 'Скачать ':'Download ', 'Удалить':'Delete', 'Убрать':'Remove',
    'Удалить файл ':'Delete file ', 'Убрать файл ':'Remove file ', 'Удалить из папки полученных на ПК':'Delete from the received folder on the computer',
    'Убрать из передачи':'Remove from sharing', 'Убрать из списка на этом устройстве':'Hide from this device’s list',
    'Удалить «':'Delete “', '» из папки полученных файлов на компьютере?':'” from the received folder on the computer?',
    'Убрано из списка. Отправленный файл остался на ПК':'Removed from the list. The sent file is still on the computer',
    'Скопировано':'Copied', 'Скопировать':'Copy', 'Текст выделен. Скопируйте его через меню браузера':'Text selected. Copy it using your browser’s menu',
    'Не удалось скопировать. Используйте QR-код':'Could not copy. Use the QR code', 'Отправленный текст':'Sent text', 'Полученный текст':'Received text',
    'Убрать текст':'Remove text', 'Отмена':'Cancel', 'Повторить':'Retry', 'Убрать запись ':'Remove entry ',
    'В очереди':'Queued', 'Передаётся':'Sending', 'Сохраняется…':'Saving…', 'Отменено':'Cancelled', 'Передача ':'Transfer ',
    ': размер больше ':': larger than ', 'Нет связи. Проверьте сеть и повторите':'No connection. Check your network and retry',
    'Не удалось передать файл':'Could not send the file', 'Не удалось выполнить действие':'Could not complete the action',
    'Новый код через ':'New code in ', ' с':' s', 'Не удалось обновить код':'Could not refresh the code',
    'До ':'Up to ', ' на файл':' per file', ' / 64 КБ':' / 64 KB', '0 Б':'0 B', 'Б':'B', 'КБ':'KB', 'МБ':'MB', 'ГБ':'GB',
    'Фото, видео, документы':'Photos, videos, documents', 'Текст отправлен':'Text sent',
    'Отключить все устройства и создать новый QR-код?':'Disconnect all devices and create a new QR code?',
    'Устройства отключены. Новый QR-код готов':'Devices disconnected. New QR code ready',
    'Подключитесь заново':'Reconnect', 'Подключитесь заново через QR-код':'Scan the QR code again',
    'Подключение завершено. Отсканируйте QR-код на ПК и введите новый код':'Connection closed. Scan the QR on the computer and enter the new code',
    'Откройте программу на ПК и подключитесь через QR-код заново':'Open Ryadom on the computer and scan the QR code again',
    'Отсканируйте QR-код на компьютере ещё раз':'Scan the QR code on the computer again',
    'Не удалось подключиться':'Could not connect', 'Проверьте соединение':'Check your connection',
    'Неверный адрес сервера':'Invalid server address', 'Откройте панель на компьютере':'Open the panel on the computer',
    'Ссылка устарела. Отсканируйте QR-код ещё раз':'Link expired. Scan the QR code again',
    'Слишком много подключений. Повторите позже':'Too many connections. Try again later',
    'Файл недоступен':'File unavailable', 'Файл перемещён или удалён':'File moved or deleted',
    'Обновите страницу и попробуйте снова':'Refresh the page and try again', 'Введите текст':'Enter some text',
    'Текст больше 64 КБ':'Text exceeds 64 KB', 'Не удалось прочитать текст':'Could not read the text',
    'Список текстов заполнен. Уберите ненужные сообщения':'Text history is full. Remove messages you no longer need',
    'Текст недоступен':'Text unavailable', 'Подтвердите удаление полученного файла':'Confirm deletion of the received file',
    'Файл ещё скачивается. Попробуйте позже':'File is still downloading. Try again later',
    'Действие доступно только на ПК':'This action is only available on the computer', 'Выберите адрес из списка':'Choose an address from the list',
    'Откройте папку вручную: ':'Open the folder manually: ', 'Не найдено':'Not found', 'Обновите страницу':'Refresh the page',
    'Введите шесть цифр с экрана ПК':'Enter the six digits shown on the computer', 'Не удалось прочитать код':'Could not read the code',
    'Много неверных попыток. Подождите 30 секунд':'Too many incorrect attempts. Wait 30 seconds',
    'Неверный код или он уже изменился. Посмотрите новый на ПК':'Incorrect or expired code. Check the current code on the computer',
    'Обновите QR-код на компьютере':'Refresh the QR code on the computer', 'Неизвестный размер файла':'Unknown file size',
    'Файл превышает лимит размера':'File exceeds the size limit', 'Не удалось прочитать имя файла':'Could not read the filename',
    'Уже передаётся несколько файлов. Повторите чуть позже':'Several files are already being transferred. Try again shortly',
    'Передача прервана. Отправьте файл ещё раз':'Transfer interrupted. Send the file again', 'Подключение завершено на ПК':'Connection closed on the computer',
    'Файл с таким именем уже появился. Повторите отправку':'A file with this name just appeared. Try sending it again',
    'Не удалось сохранить файл. Проверьте свободное место и соединение':'Could not save the file. Check disk space and connection'
  };
  const ru = {'Сетевая справка':'Устройства должны быть в одной сети. Если VPN блокирует локальные подключения, разрешите доступ к локальной сети в его настройках. В Windows разрешите Python доступ к частной сети. Гостевой Wi-Fi может изолировать устройства.'};
  const reverse = Object.fromEntries(Object.entries(en).map(([key,value]) => [value,key]));
  let language = 'en';
  try { if (localStorage.getItem('ryadom-language') === 'ru') language = 'ru'; } catch { /* Storage can be unavailable in private mode. */ }
  function translate(value) {
    if (typeof value !== 'string') return '';
    const source = Object.hasOwn(en, value) ? value : reverse[value] || value;
    if (language === 'ru') return ru[source] || source;
    if (Object.hasOwn(en, source)) return en[source];
    const prefix = 'Откройте папку вручную: ';
    return source.startsWith(prefix) ? en[prefix] + source.slice(prefix.length) : source;
  }
  function apply() {
    document.documentElement.lang = language;
    document.title = language === 'ru' ? 'Рядом' : 'Ryadom';
    for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = translate(el.dataset.i18n);
    for (const [data,attr] of [['i18nPlaceholder','placeholder'],['i18nLabel','aria-label'],['i18nAlt','alt']]) {
      for (const el of document.querySelectorAll('[data-' + data.replace(/[A-Z]/g,c => '-' + c.toLowerCase()) + ']')) el.setAttribute(attr, translate(el.dataset[data]));
    }
    for (const el of document.querySelectorAll('[data-language]')) el.setAttribute('aria-pressed', String(el.dataset.language === language));
  }
  function setLanguage(value) {
    language = value === 'ru' ? 'ru' : 'en';
    try { localStorage.setItem('ryadom-language', language); } catch { /* Keep the in-memory choice. */ }
    apply(); window.dispatchEvent(new Event('languagechange'));
  }
  window.t = translate;
  window.i18n = {get language() {return language;}, apply, setLanguage};
  for (const el of document.querySelectorAll('[data-language]')) el.onclick = () => setLanguage(el.dataset.language);
  apply();
})();
