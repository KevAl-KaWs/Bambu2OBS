from flask import Flask, jsonify, Response, send_from_directory, render_template_string
from werkzeug.utils import secure_filename, safe_join
from flask_cors import CORS
import os
import time
import logging
from dotenv import load_dotenv
from threading import Thread
import sys

# Load environment variables
load_dotenv()

BASE_DIR = os.path.abspath(os.getenv('BASE_DIR', 'data'))
TEMPLATE_DIR = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'templates')
SVG_FILES = ['Filaments.svg', 'ActiveFilament.svg']

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

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
    })

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
