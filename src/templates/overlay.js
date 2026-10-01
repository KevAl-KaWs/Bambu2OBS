// URL options, e.g. /view/overlay?name=Printcess&color=ff4fa3&cover=0&card=0&sound=0&volume=50&test=fertig
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

const printerName = (params.get('name') || '').trim();

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

let lastCoverVersion = null;
let lastState = null;
let celebrateUntil = 0;
const playSound = params.get('sound') !== '0';
const volume = Math.max(0, Math.min(100, Number(params.get('volume') ?? 70))) / 100;
const isTest = params.get('test') === 'fertig';
const CELEBRATION_MS = 12000;

function finishedText() {
    return printerName ? `${printerName} ist fertig! 🎉` : 'Fertig! 🎉';
}

// Short chime, generated in the browser so no sound file is needed
function playChime() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
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
    if (!playSound) return;
    if (hasCustomSound) {
        const audio = new Audio(`/sound?t=${Date.now()}`);
        audio.volume = volume;
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
    const style = getComputedStyle(document.documentElement);
    const colors = [style.getPropertyValue('--bar').trim(), style.getPropertyValue('--bar-light').trim(), '#ffffff', '#ffd1e8'];
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

        if (isTest) {
            data.state = 'FINISH';
            data.progress = 100;
        }

        // Only a real switch to FINISH triggers the celebration, not reloading the page afterwards
        if (data.state === 'FINISH' && lastState !== null && lastState !== 'FINISH') {
            celebrate(data.hasSound);
        }
        if (isTest && lastState === null) {
            celebrate(data.hasSound);
        }
        lastState = data.state || 'UNKNOWN';

        const progress = Math.max(0, Math.min(100, Number(data.progress) || 0));
        document.getElementById('bar').style.width = `${progress}%`;
        document.getElementById('percent').textContent = `${Math.round(progress)} %`;
        const printTitle = data.designTitle || data.name || '–';
        const celebrating = Date.now() < celebrateUntil;
        // While celebrating the big line shows "… ist fertig!" and the small line the print name
        document.getElementById('name').textContent = celebrating ? finishedText() : printTitle;
        document.getElementById('label').textContent = celebrating
            ? printTitle
            : printerName
                ? `${printerName} ${NAMED_STATE_LABELS[data.state] || NAMED_STATE_LABELS.RUNNING}`
                : (STATE_LABELS[data.state] || STATE_LABELS.RUNNING);

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
