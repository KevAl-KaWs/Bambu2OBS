// URL options, e.g. /view/overlay?color=ff4fa3&cover=0&card=0
const params = new URLSearchParams(window.location.search);

if (params.get('color')) {
    const color = '#' + params.get('color').replace('#', '');
    document.documentElement.style.setProperty('--bar', color);
    document.documentElement.style.setProperty('--bar-light', color);
}
if (params.get('card') === '0') {
    document.body.classList.add('no-card');
}
const showCover = params.get('cover') !== '0';

const STATE_LABELS = {
    RUNNING: 'Druckt gerade',
    PREPARE: 'Druck wird vorbereitet',
    PAUSE: 'Pausiert',
    FINISH: 'Fertig!',
    FAILED: 'Abgebrochen',
    IDLE: 'Kein Druck aktiv',
};

let lastCoverVersion = null;

function formatDuration(minutes) {
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return h > 0 ? `${h} Std. ${m} Min.` : `${m} Min.`;
}

function formatEta(minutes) {
    const eta = new Date(Date.now() + minutes * 60000);
    return eta.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

async function update() {
    try {
        const response = await fetch('/status', { cache: 'no-store' });
        const data = await response.json();

        const progress = Math.max(0, Math.min(100, Number(data.progress) || 0));
        document.getElementById('bar').style.width = `${progress}%`;
        document.getElementById('percent').textContent = `${Math.round(progress)} %`;
        document.getElementById('name').textContent = data.designTitle || data.name || '–';
        document.getElementById('label').textContent = STATE_LABELS[data.state] || 'Druckt gerade';

        const time = document.getElementById('time');
        if (data.state === 'FINISH') {
            time.textContent = 'Druck abgeschlossen';
        } else if (data.remainingMinutes !== null && data.remainingMinutes > 0) {
            time.textContent = `noch ${formatDuration(data.remainingMinutes)} · fertig ca. ${formatEta(data.remainingMinutes)} Uhr`;
        } else {
            time.textContent = '';
        }

        const cover = document.getElementById('cover');
        cover.hidden = !(showCover && data.hasCover);
        if (showCover && data.hasCover && data.coverVersion !== lastCoverVersion) {
            lastCoverVersion = data.coverVersion;
            cover.src = `/cover?v=${data.coverVersion}`;
        }
    } catch (error) {
        console.error('Status konnte nicht geladen werden:', error);
    }
}

update();
setInterval(update, 2000);
