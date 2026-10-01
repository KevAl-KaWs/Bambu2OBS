from flask import Flask, jsonify, Response, send_from_directory, render_template_string, request
from werkzeug.utils import secure_filename, safe_join
from flask_cors import CORS
import os
import time
import logging
from dotenv import load_dotenv
from threading import Thread
import sys
import json

# Load environment variables
load_dotenv()

BASE_DIR = os.path.abspath(os.getenv('BASE_DIR', 'data'))
# Folder of the .exe / project, where a custom finish sound (fertig.mp3 etc.) can be placed
APP_DIR = os.path.abspath(os.getenv('APP_DIR', os.path.dirname(BASE_DIR)))
SOUND_FILES = ['fertig.mp3', 'fertig.wav', 'fertig.ogg']
CONFIG_DIR = os.getenv('CONFIG_DIR')
TEMPLATE_DIR = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'templates')
SVG_FILES = ['Filaments.svg', 'ActiveFilament.svg']

app = Flask(__name__)
# Only the read-only overlay data may be read by other origins, never the settings (access code)
CORS(app, resources={r"/progress": {}, r"/status": {}, r"/svg/*": {}, r"/updates/*": {}})
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # sound uploads

# Shared with bambu2obs.py when started from there (settings hooks, connection state)
runtime = {}

SETTINGS_DIR = CONFIG_DIR or BASE_DIR
OVERLAY_SETTINGS_PATH = os.path.join(SETTINGS_DIR, 'overlay.json')
OVERLAY_DEFAULTS = {
    'name': '',
    'color': '#ff4fa3',
    'card': True,
    'cover': True,
    'sound': True,
    'volume': 70,
}

def read_overlay_settings():
    settings = dict(OVERLAY_DEFAULTS)
    try:
        with open(OVERLAY_SETTINGS_PATH, 'r', encoding='utf-8') as file:
            stored = json.load(file)
        settings.update({k: v for k, v in stored.items() if k in OVERLAY_DEFAULTS})
    except (FileNotFoundError, ValueError, OSError):
        pass
    return settings

def write_overlay_settings(values):
    settings = read_overlay_settings()
    for key, default in OVERLAY_DEFAULTS.items():
        if key not in values:
            continue
        value = values[key]
        if isinstance(default, bool):
            settings[key] = bool(value)
        elif isinstance(default, int):
            settings[key] = max(0, min(100, int(value)))
        else:
            settings[key] = str(value).strip()[:60]
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(OVERLAY_SETTINGS_PATH, 'w', encoding='utf-8') as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)
    return settings

@app.before_request
def protect_settings_api():
    """Changing settings needs a custom header: other websites cannot send it without CORS."""
    if request.path.startswith('/api/') and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('X-Bambu2OBS') != '1':
            return jsonify({'error': 'forbidden'}), 403

# Configure logging
app.logger.setLevel(logging.DEBUG)

PROGRESS_FILE_PATH = os.path.join(BASE_DIR, 'progress.txt')
SVG_DIR = BASE_DIR  # Assuming SVG files are stored in the BASE_DIR

def file_watcher(filename, last_known_stamp=0):
    """
    Generator function to watch for file changes.
    """
    while True:
        try:
            stat = os.stat(os.path.join(SVG_DIR, filename))
            if stat.st_mtime != last_known_stamp:
                last_known_stamp = stat.st_mtime
                yield f"data: update\n\n"
        except FileNotFoundError:
            pass
        time.sleep(1)

@app.route('/progress')
def get_progress():
    try:
        if os.path.exists(PROGRESS_FILE_PATH):
            with open(PROGRESS_FILE_PATH, 'r') as file:
                progress = file.read().strip()
                try:
                    progress = float(progress) if '.' in progress else int(progress)
                except ValueError:
                    pass
                return jsonify({'progress': progress})
        else:
            return jsonify({'progress': "progress.txt not found"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def read_data(name, default=None):
    try:
        with open(os.path.join(BASE_DIR, f'{name}.txt'), 'r', encoding='utf-8') as file:
            return file.read().strip()
    except (FileNotFoundError, OSError):
        return default

def to_number(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

@app.route('/status')
def get_status():
    """All values the overlay needs in one request."""
    cover_path = os.path.join(BASE_DIR, 'printCover.png')
    design_title = read_data('designTitle')
    return jsonify({
        'name': read_data('printName') or read_data('printProfile'),
        'designTitle': design_title if design_title not in (None, 'N/A') else None,
        'progress': to_number(read_data('progress'), 0),
        'remainingMinutes': to_number(read_data('remaining_minutes')),
        'state': read_data('printState'),
        'layer': read_data('layer_num'),
        'totalLayers': read_data('total_layer_num'),
        'hasCover': os.path.exists(cover_path),
        'coverVersion': int(os.path.getmtime(cover_path)) if os.path.exists(cover_path) else 0,
        'hasSound': find_sound_file() is not None,
        'overlay': read_overlay_settings(),
        'testFinishAt': runtime.get('test_finish_at', 0),
    })

@app.route('/')
def settings_view():
    return send_from_directory(TEMPLATE_DIR, 'settings.html')

@app.route('/view/settings.js')
def settings_script():
    return send_from_directory(TEMPLATE_DIR, 'settings.js')

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    printer = runtime['read_settings']() if 'read_settings' in runtime else {}
    connection = runtime.get('connection', {'state': 'standalone' if 'read_settings' not in runtime else 'unconfigured'})
    last_message = runtime.get('last_message')
    sound = find_sound_file()
    return jsonify({
        'printer': {
            'ip': printer.get('PRINTER_IP', ''),
            'accessCode': printer.get('ACCESS_CODE', ''),
            'serial': printer.get('PRINTER_SN', ''),
            'email': printer.get('EMAIL', ''),
            'hasPassword': bool(printer.get('PASSWORD')),
        },
        'overlay': read_overlay_settings(),
        'connection': dict(
            connection,
            sinceAgo=(time.time() - connection['since']) if connection.get('since') else None,
            lastMessageAgo=(time.time() - last_message) if last_message else None,
        ),
        'sound': sound[1] if sound else None,
        'canSavePrinter': 'save_printer_settings' in runtime,
    })

@app.route('/api/settings/printer', methods=['POST'])
def api_save_printer():
    if 'save_printer_settings' not in runtime:
        return jsonify({'error': 'Nur verfügbar, wenn Bambu2OBS gestartet ist.'}), 503
    data = request.get_json(silent=True) or {}
    values = {
        'PRINTER_IP': data.get('ip', ''),
        'ACCESS_CODE': data.get('accessCode', ''),
        'PRINTER_SN': data.get('serial', ''),
        'EMAIL': data.get('email', ''),
    }
    # Empty password field keeps the stored password; without e-mail it is removed
    if not values['EMAIL']:
        values['PASSWORD'] = ''
    elif data.get('password'):
        values['PASSWORD'] = data['password']
    runtime['last_message'] = None
    runtime['save_printer_settings'](values)
    return jsonify({'ok': True})

@app.route('/api/settings/overlay', methods=['POST'])
def api_save_overlay():
    return jsonify(write_overlay_settings(request.get_json(silent=True) or {}))

@app.route('/api/test-finish', methods=['POST'])
def api_test_finish():
    runtime['test_finish_at'] = int(time.time() * 1000)
    return jsonify({'ok': True})

@app.route('/api/sound', methods=['POST', 'DELETE'])
def api_sound():
    sound_dir = SETTINGS_DIR
    os.makedirs(sound_dir, exist_ok=True)
    if request.method == 'POST':
        upload = request.files.get('file')
        extension = os.path.splitext(upload.filename)[1].lower() if upload and upload.filename else ''
        if f'fertig{extension}' not in SOUND_FILES:
            return jsonify({'error': 'Bitte eine MP3-, WAV- oder OGG-Datei wählen.'}), 400
    # Only one custom sound at a time
    for name in SOUND_FILES:
        try:
            os.remove(os.path.join(sound_dir, name))
        except FileNotFoundError:
            pass
    if request.method == 'DELETE':
        return jsonify({'ok': True})
    upload.save(os.path.join(sound_dir, f'fertig{extension}'))
    return jsonify({'ok': True, 'sound': f'fertig{extension}'})

def find_sound_file():
    """Custom sound next to the .exe or in the settings folder."""
    for directory in (SETTINGS_DIR, APP_DIR):
        if not directory:
            continue
        for name in SOUND_FILES:
            if os.path.exists(os.path.join(directory, name)):
                return directory, name
    return None

@app.route('/sound')
def get_sound():
    sound_file = find_sound_file()
    if sound_file:
        return send_from_directory(*sound_file)
    return "No sound", 404

@app.route('/cover')
def get_cover():
    if os.path.exists(os.path.join(BASE_DIR, 'printCover.png')):
        return send_from_directory(BASE_DIR, 'printCover.png')
    return "No cover", 404

@app.route('/view/overlay')
def overlay_view():
    return send_from_directory(TEMPLATE_DIR, 'overlay.html')

@app.route('/view/overlay.js')
def overlay_script():
    return send_from_directory(TEMPLATE_DIR, 'overlay.js')

@app.route('/view/progressbar')
def progressbar_view():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Customized Bootstrap Progress Bar for OBS</title>
        <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
        <style>
            html, body {
                margin: 0;
                padding: 0;
                overflow: hidden;
            }
            .custom-container {
                padding-right: 0;
                padding-left: 0;
                margin-right: auto;
                margin-left: auto;
                max-width: 560px; /* Set the container's max width */
            }
            .progress {
                background-color: #EEEEEE; /* Color for the unused part of the bar */
                height: 30px; /* Height of the progress bar */
                margin: 0; /* Remove default margin */
                width: 100%; /* Use full width of the custom container */
            }
            .progress-bar {
                background-color: #00AE42; /* Color for the used part of the bar */
            }
        </style>
    </head>
    <body>

    <div class="custom-container"> <!-- Changed class here -->
        <div class="progress">
            <div id="progress-bar" class="progress-bar" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
        </div>
    </div>

    <script>
        function updateProgress() {
            fetch('http://localhost:5000/progress')
                .then(response => response.json())
                .then(data => {
                    const progressBar = document.getElementById('progress-bar');
                    progressBar.style.width = `${data.progress}%`;
                    progressBar.setAttribute('aria-valuenow', data.progress);
                })
                .catch(error => console.error('Error fetching progress:', error));
        }

        setInterval(updateProgress, 1000);
    </script>

    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/updates/<filename>')
def updates(filename):
    if filename in SVG_FILES:
        return Response(file_watcher(filename), content_type='text/event-stream')
    return "File not found", 404

@app.route('/svg/<filename>')
def serve_svg(filename):
    filename = secure_filename(filename)
    filepath = safe_join(SVG_DIR, filename)
    print(f"Attempting to serve: {filepath}: {secure_filename} in directory: {SVG_DIR}")  # Debug print
    if os.path.exists(filepath):
        print("File found, serving...")  # Debug print
        return send_from_directory(SVG_DIR, filename)
    else:
        app.logger.error(f"File not found: {secure_filename} in directory: {SVG_DIR}")
        return "File not found", 404
    
@app.route('/view/<filename>')
def view_svg(filename):
    if filename in SVG_FILES:
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>SVG Viewer - {filename}</title>
        </head>
        <body>
            <img src="/svg/{filename}" id="svgImage">
            <script>
                const evtSource = new EventSource("/updates/{filename}");
                evtSource.onmessage = function(event) {{
                    const img = document.getElementById('svgImage');
                    const src = img.src.split('?')[0];
                    img.src = `${{src}}?t=${{new Date().getTime()}}`;
                }};
            </script>
        </body>
        </html>
        """
        return render_template_string(html)
    return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
