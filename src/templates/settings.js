const $ = (id) => document.getElementById(id);
const HEADERS = { 'Content-Type': 'application/json', 'X-Bambu2OBS': '1' };

function showMessage(id, text, kind) {
    const el = $(id);
    el.textContent = text;
    el.className = `msg ${kind || ''}`;
}

async function api(path, options = {}) {
    const response = await fetch(path, Object.assign({ cache: 'no-store' }, options));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Fehler ${response.status}`);
    return data;
}

// --- Connection status -------------------------------------------------------

function describeConnection(c) {
    switch (c.state) {
        case 'unconfigured':
            return ['warn', 'Noch nicht eingerichtet – Drucker-Daten unten eintragen'];
        case 'connecting':
            if (c.sinceAgo > 20) return ['err', 'Keine Verbindung – ist der Drucker an und die IP-Adresse richtig?'];
            return ['warn', c.detail || 'Verbinde …'];
        case 'connected':
            if (c.lastMessageAgo === null && c.sinceAgo > 20) return ['warn', 'Verbunden, aber keine Daten – Seriennummer prüfen'];
            return ['ok', 'Mit dem Drucker verbunden'];
        case 'error':
            return ['err', c.detail || 'Verbindung fehlgeschlagen'];
        case 'standalone':
            return ['warn', 'Nur Vorschau – Bambu2OBS ist nicht gestartet'];
        default:
            return ['', c.state || 'Unbekannt'];
    }
}

function renderStatus(connection) {
    const [kind, text] = describeConnection(connection);
    const pill = $('status');
    pill.className = `pill ${kind}`;
    pill.textContent = text;
}

async function pollStatus() {
    try {
        const data = await api('/api/settings');
        renderStatus(data.connection);
    } catch (error) {
        renderStatus({ state: 'error', detail: 'Bambu2OBS läuft nicht mehr – bitte neu starten' });
    }
}

// --- Printer -----------------------------------------------------------------

function fillPrinter(printer, canSave) {
    $('ip').value = printer.ip || '';
    $('accessCode').value = printer.accessCode || '';
    $('serial').value = printer.serial || '';
    $('email').value = printer.email || '';
    $('password-hint').textContent = printer.hasPassword ? 'Gespeichert – leer lassen, um es zu behalten.' : '';
    if (!canSave) {
        $('printer-form').querySelectorAll('input, button').forEach((el) => { el.disabled = true; });
        showMessage('printer-msg', 'Nur änderbar, wenn Bambu2OBS gestartet ist.', 'err');
    }
}

$('printer-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    showMessage('printer-msg', 'Speichere …');
    try {
        await api('/api/settings/printer', {
            method: 'POST',
            headers: HEADERS,
            body: JSON.stringify({
                ip: $('ip').value.trim(),
                accessCode: $('accessCode').value.trim(),
                serial: $('serial').value.trim().toUpperCase(),
                email: $('email').value.trim(),
                password: $('password').value,
            }),
        });
        $('password').value = '';
        $('serial').value = $('serial').value.trim().toUpperCase();
        showMessage('printer-msg', 'Gespeichert – verbinde mit dem Drucker …', 'ok');
        setTimeout(pollStatus, 800);
    } catch (error) {
        showMessage('printer-msg', error.message, 'err');
    }
});

// --- Overlay & sound (saved automatically) -----------------------------------

let saveTimer = null;

function currentOverlay() {
    return {
        name: $('name').value,
        color: $('color').value,
        card: $('card').checked,
        cover: $('cover').checked,
        sound: $('sound').checked,
        volume: Number($('volume').value),
    };
}

function markSwatch(color) {
    document.querySelectorAll('.swatch').forEach((swatch) => {
        swatch.setAttribute('aria-pressed', String(swatch.dataset.color.toLowerCase() === color.toLowerCase()));
    });
}

function saveOverlaySoon(messageId) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
        try {
            await api('/api/settings/overlay', { method: 'POST', headers: HEADERS, body: JSON.stringify(currentOverlay()) });
            showMessage(messageId, 'Gespeichert ✓', 'ok');
            setTimeout(() => showMessage(messageId, ''), 2000);
        } catch (error) {
            showMessage(messageId, error.message, 'err');
        }
    }, 350);
}

function fillOverlay(overlay) {
    $('name').value = overlay.name || '';
    $('color').value = overlay.color || '#ff4fa3';
    $('card').checked = !!overlay.card;
    $('cover').checked = !!overlay.cover;
    $('sound').checked = !!overlay.sound;
    $('volume').value = overlay.volume;
    $('volume-value').textContent = overlay.volume;
    markSwatch($('color').value);
}

$('name').addEventListener('input', () => saveOverlaySoon('overlay-msg'));
$('color').addEventListener('input', () => { markSwatch($('color').value); saveOverlaySoon('overlay-msg'); });
['card', 'cover'].forEach((id) => $(id).addEventListener('change', () => saveOverlaySoon('overlay-msg')));
$('sound').addEventListener('change', () => saveOverlaySoon('sound-msg'));
$('volume').addEventListener('input', () => {
    $('volume-value').textContent = $('volume').value;
    saveOverlaySoon('sound-msg');
});
document.querySelectorAll('.swatch').forEach((swatch) => {
    swatch.addEventListener('click', () => {
        $('color').value = swatch.dataset.color;
        markSwatch(swatch.dataset.color);
        saveOverlaySoon('overlay-msg');
    });
});

// --- Custom sound ------------------------------------------------------------

function renderSound(soundFile) {
    $('sound-name').textContent = soundFile ? `Eigener Sound: ${soundFile}` : 'Glockenklang (eingebaut)';
    $('remove-sound').hidden = !soundFile;
}

$('choose-sound').addEventListener('click', () => $('sound-file').click());

$('sound-file').addEventListener('change', async () => {
    const file = $('sound-file').files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    showMessage('sound-msg', 'Lade hoch …');
    try {
        const result = await api('/api/sound', { method: 'POST', headers: { 'X-Bambu2OBS': '1' }, body: form });
        renderSound(result.sound);
        showMessage('sound-msg', 'Sound gespeichert ✓', 'ok');
    } catch (error) {
        showMessage('sound-msg', error.message, 'err');
    }
    $('sound-file').value = '';
});

$('remove-sound').addEventListener('click', async () => {
    try {
        await api('/api/sound', { method: 'DELETE', headers: HEADERS });
        renderSound(null);
        showMessage('sound-msg', 'Wieder der eingebaute Glockenklang', 'ok');
    } catch (error) {
        showMessage('sound-msg', error.message, 'err');
    }
});

$('test-finish').addEventListener('click', async () => {
    try {
        await api('/api/test-finish', { method: 'POST', headers: HEADERS });
        showMessage('sound-msg', 'Einblendung ausgelöst – schau in die Vorschau und in OBS', 'ok');
    } catch (error) {
        showMessage('sound-msg', error.message, 'err');
    }
});

// --- OBS URL -----------------------------------------------------------------

$('copy-url').addEventListener('click', async () => {
    const url = $('obs-url').textContent;
    try {
        await navigator.clipboard.writeText(url);
    } catch (error) {
        const range = document.createRange();
        range.selectNodeContents($('obs-url'));
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        document.execCommand('copy');
    }
    $('copy-url').textContent = 'Kopiert ✓';
    setTimeout(() => { $('copy-url').textContent = 'Kopieren'; }, 1800);
});

// --- Start -------------------------------------------------------------------

(async function init() {
    try {
        const data = await api('/api/settings');
        fillPrinter(data.printer, data.canSavePrinter);
        fillOverlay(data.overlay);
        renderSound(data.sound);
        renderStatus(data.connection);
        if (!data.printer.ip) $('ip').focus();
    } catch (error) {
        renderStatus({ state: 'error', detail: 'Bambu2OBS läuft nicht – bitte starten' });
    }
    setInterval(pollStatus, 3000);
})();
