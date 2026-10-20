'use strict';
const input = document.getElementById('code');
const button = document.getElementById('connect');
const error = document.getElementById('connect-error');
let csrf, busy = false;
input.addEventListener('input', () => { input.value = input.value.replace(/[^0-9]/g, '').slice(0, 6); });
async function prepare() {
  try {
    const response = await fetch('/api/pairing', {cache: 'no-store'});
    if (!response.ok) throw new Error(t('Отсканируйте QR-код на компьютере ещё раз'));
    csrf = (await response.json()).csrf;
  } catch (e) { error.textContent = e.message; button.disabled = true; }
}
document.getElementById('connect-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !csrf) return;
  busy = true; button.disabled = true; error.textContent = '';
  try {
    const response = await fetch('/api/connect', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Ryadom-CSRF': csrf}, body: JSON.stringify({code: input.value})});
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) csrf = null;
      throw new Error(t(data.error) || t('Не удалось подключиться'));
    }
    window.location.replace('/');
  } catch (e) { error.textContent = e.message || t('Проверьте соединение'); input.focus(); input.select(); }
  finally { busy = false; button.disabled = !csrf; }
});
window.addEventListener('languagechange', () => { error.textContent = t(error.textContent); });
prepare();
