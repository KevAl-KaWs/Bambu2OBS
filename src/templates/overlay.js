// Settings come from the settings page (http://localhost:5000/).
// URL options override them, e.g. /view/overlay?name=Printcess&color=ff4fa3&cover=0&card=0&sound=0&volume=50&test=fertig
const params = new URLSearchParams(window.location.search);
const isTest = params.get('test') === 'fertig';
const isDemo = params.get('demo') === '1';
const CELEBRATION_MS = 12000;

const NAMED_STATE_LABELS = {
    RUNNING: 'druckt gerade',
    PREPARE: 'bereitet den Druck vor',
    PAUSE: 'macht Pause',
    FINISH: 'ist fertig!',
    FAILED: 'hat abgebrochen',
    IDLE: 'ruht sich aus',
};

const STATE_LABELS = {
    RUNNING: 'Druckt gerade',
    PREPARE: 'Druck wird vorbereitet',
    PAUSE: 'Pausiert',
    FINISH: 'Fertig!',
    FAILED: 'Abgebrochen',
    IDLE: 'Kein Druck aktiv',
};

let options = { name: '', color: '#ff4fa3', card: true, cover: true, sound: true, volume: 70 };
let lastCoverVersion = null;
let lastState = null;
let lastTestFinishAt = null;
let celebrateUntil = 0;

// Lighter shade of the bar colour for the gradient end
function lighten(hex, amount) {
    const match = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!match) return hex;
    const n = parseInt(match[1], 16);
    const mix = (c) => Math.round(c + (255 - c) * amount);
    return `rgb(${mix(n >> 16)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`;
}

function flag(value) {
    return value !== '0' && value !== 'false';
}

// Server settings first, URL parameters win
function applyOptions(serverOptions) {
    const merged = Object.assign({}, options, serverOptions || {});
    if (params.has('name')) merged.name = params.get('name');
    if (params.has('color')) merged.color = '#' + params.get('color').replace('#', '');
    if (params.has('card')) merged.card = flag(params.get('card'));
    if (params.has('cover')) merged.cover = flag(params.get('cover'));
    if (params.has('sound')) merged.sound = flag(params.get('sound'));
    if (params.has('volume')) merged.volume = Number(params.get('volume'));
    merged.name = (merged.name || '').trim();
    merged.volume = Math.max(0, Math.min(100, Number(merged.volume) || 0));
    options = merged;

    document.documentElement.style.setProperty('--bar', options.color);
    document.documentElement.style.setProperty('--bar-light', lighten(options.color, 0.4));
    document.body.classList.toggle('no-card', !options.card);
}

function finishedText() {
    return options.name ? `${options.name} ist fertig! 🎉` : 'Fertig! 🎉';
}

function formatDuration(minutes) {
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return h > 0 ? `${h} Std. ${m} Min.` : `${m} Min.`;
}

function formatEta(minutes) {
    const eta = new Date(Date.now() + minutes * 60000);
    return eta.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

// Short chime, generated in the browser so no sound file is needed
function playChime() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const volume = options.volume / 100;
    const notes = [523.25, 659.25, 783.99, 1046.5];
    notes.forEach((freq, i) => {
        const start = ctx.currentTime + i * 0.14;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(0.35 * volume, start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, start + (i === notes.length - 1 ? 1.4 : 0.5));
        osc.connect(gain).connect(ctx.destination);
        osc.start(start);
        osc.stop(start + 1.5);
    });
    setTimeout(() => ctx.close(), 2500);
}

function playFinishSound(hasCustomSound) {
    if (!options.sound || options.volume === 0) return;
    if (hasCustomSound) {
        const audio = new Audio(`/sound?t=${Date.now()}`);
        audio.volume = options.volume / 100;
        audio.play().catch(playChime);
    } else {
        playChime();
    }
}

function runConfetti(durationMs) {
    const canvas = document.getElementById('confetti');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const colors = [options.color, '#ffffff', '#ffd1e8', options.color];
    const pieces = [];
    const end = performance.now() + durationMs;

    function spawn(count) {
        for (let i = 0; i < count; i++) {
            pieces.push({
                x: Math.random() * canvas.width,
                y: -10 - Math.random() * 40,
                vx: (Math.random() - 0.5) * 2.5,
                vy: 1 + Math.random() * 2.5,
                size: 4 + Math.random() * 5,
                rot: Math.random() * Math.PI,
                spin: (Math.random() - 0.5) * 0.3,
                color: colors[Math.floor(Math.random() * colors.length)],
            });
        }
    }

    spawn(80);
    function frame(now) {
        if (now < end - 2000) spawn(3);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let i = pieces.length - 1; i >= 0; i--) {
            const p = pieces[i];
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.03;
            p.rot += p.spin;
            if (p.y > canvas.height + 20) {
                pieces.splice(i, 1);
                continue;
            }
            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate(p.rot);
            ctx.fillStyle = p.color;
            ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
            ctx.restore();
        }
        if (now < end || pieces.length) {
            requestAnimationFrame(frame);
        } else {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }
    requestAnimationFrame(frame);
}

function celebrate(hasCustomSound) {
    celebrateUntil = Date.now() + CELEBRATION_MS;
    document.body.classList.add('celebrate');
    runConfetti(CELEBRATION_MS);
    playFinishSound(hasCustomSound);
    setTimeout(() => {
        if (Date.now() >= celebrateUntil) document.body.classList.remove('celebrate');
    }, CELEBRATION_MS);
}

async function update() {
    try {
        const response = await fetch('/status', { cache: 'no-store' });
        const data = await response.json();
        applyOptions(data.overlay);

        // Sample data for the preview on the settings page
        if (isDemo && !data.name && !data.designTitle) {
            Object.assign(data, { name: 'Beispiel-Druck', progress: 64, remainingMinutes: 83, state: 'RUNNING' });
        }
        if (isTest) {
            data.state = 'FINISH';
            data.progress = 100;
        }

        // Only a real switch to FINISH triggers the celebration, not reloading the page afterwards
        const testPressed = lastTestFinishAt !== null && data.testFinishAt !== lastTestFinishAt;
        if ((data.state === 'FINISH' && lastState !== null && lastState !== 'FINISH') || testPressed) {
            celebrate(data.hasSound);
        }
        if (isTest && lastState === null) {
            celebrate(data.hasSound);
        }
        lastState = data.state || 'UNKNOWN';
        lastTestFinishAt = data.testFinishAt;

        const celebrating = Date.now() < celebrateUntil;
        const progress = celebrating ? 100 : Math.max(0, Math.min(100, Number(data.progress) || 0));
        document.getElementById('bar').style.width = `${progress}%`;
        document.getElementById('percent').textContent = `${Math.round(progress)} %`;
        const printTitle = data.designTitle || data.name || '–';
        // While celebrating the big line shows "… ist fertig!" and the small line the print name
        document.getElementById('name').textContent = celebrating ? finishedText() : printTitle;
        document.getElementById('label').textContent = celebrating
            ? printTitle
            : options.name
                ? `${options.name} ${NAMED_STATE_LABELS[data.state] || NAMED_STATE_LABELS.RUNNING}`
                : (STATE_LABELS[data.state] || STATE_LABELS.RUNNING);

        const time = document.getElementById('time');
        if (celebrating || data.state === 'FINISH') {
            time.textContent = 'Druck abgeschlossen';
        } else if (data.remainingMinutes !== null && data.remainingMinutes > 0) {
            time.textContent = `noch ${formatDuration(data.remainingMinutes)} · fertig ca. ${formatEta(data.remainingMinutes)} Uhr`;
        } else {
            time.textContent = '';
        }

        const cover = document.getElementById('cover');
        cover.hidden = !(options.cover && data.hasCover);
        if (options.cover && data.hasCover && data.coverVersion !== lastCoverVersion) {
            lastCoverVersion = data.coverVersion;
            cover.src = `/cover?v=${data.coverVersion}`;
        }
    } catch (error) {
        console.error('Status konnte nicht geladen werden:', error);
    }
}

update();
setInterval(update, isDemo ? 1000 : 2000);
