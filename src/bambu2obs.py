from dotenv import load_dotenv, dotenv_values
import os
import ssl
from pybambu import BambuClient
from pybambu.const import SPEED_PROFILE, FILAMENT_NAMES, CURRENT_STAGE_IDS
import paho.mqtt.client as mqtt
import json
from datetime import datetime, timedelta
import time
import socket
import requests
import subprocess
import signal
import sys
import xml.etree.ElementTree as ET
import threading
import shutil
import ftplib
import io
import re
import zipfile

# As .exe (PyInstaller) the data lives next to the .exe, otherwise in the project folder
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    TEMPLATE_DIR = os.path.join(sys._MEIPASS, 'templates')
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# Settings are kept in a fixed user folder, so a new version in any folder finds them again
if os.name == 'nt' and os.getenv('APPDATA'):
    CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'Bambu2OBS')
else:
    CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.config', 'Bambu2OBS')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.env')
LOCAL_ENV_PATH = os.path.join(APP_DIR, '.env')

if not getattr(sys, 'frozen', False) and os.path.exists(LOCAL_ENV_PATH):
    # Running from source with a project .env (original setup)
    ENV_PATH = LOCAL_ENV_PATH
else:
    ENV_PATH = CONFIG_PATH
    # Take over a .env from an older version next to the .exe
    if not os.path.exists(CONFIG_PATH) and os.path.exists(LOCAL_ENV_PATH):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copyfile(LOCAL_ENV_PATH, CONFIG_PATH)

def ask(question, current=None, secret=False):
    """Asks for a value; Enter keeps the current one."""
    if current:
        hint = 'gespeichert' if secret else current
        answer = input(f"{question} [{hint}]: ").strip()
        return answer or current
    return input(f"{question}: ").strip()

def run_setup():
    """Asks for the printer details and writes the settings file."""
    current = dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    print("=" * 60)
    print(" Bambu2OBS - Einstellungen")
    print(" Die Angaben findest du am Drucker unter Einstellungen -> WLAN/Netzwerk.")
    if current:
        print(" Enter drücken übernimmt den Wert in [Klammern].")
    print("=" * 60)
    printer_ip = ask("IP-Adresse des Druckers (z. B. 192.168.178.45)", current.get('PRINTER_IP'))
    access_code = ask("Access Code des Druckers", current.get('ACCESS_CODE'))
    printer_sn = ask("Seriennummer des Druckers", current.get('PRINTER_SN'))
    print("Optional: Bambu-Konto für den Modellnamen von MakerWorld (leer lassen = ohne).")
    email = ask("Bambu-Konto E-Mail", current.get('EMAIL'))
    password = ask("Bambu-Konto Passwort", current.get('PASSWORD'), secret=True) if email else ''
    os.makedirs(os.path.dirname(ENV_PATH), exist_ok=True)
    with open(ENV_PATH, 'w', encoding='utf-8') as env_file:
        env_file.write(
            f"EMAIL={email}\nPASSWORD={password}\nREGION=global\n"
            f"PRINTER_SN={printer_sn}\nPRINTER_IP={printer_ip}\nACCESS_CODE={access_code}\nBASE_DIR=data\n"
        )
    print(f"Einstellungen gespeichert in {ENV_PATH}\n")

def offer_settings_change(seconds=5):
    """On Windows: pressing E right after the start opens the settings again."""
    try:
        import msvcrt
    except ImportError:
        return False
    print(f"Einstellungen ändern? Innerhalb von {seconds} Sekunden die Taste E drücken ...")
    end = time.time() + seconds
    while time.time() < end:
        if msvcrt.kbhit() and msvcrt.getwch().lower() == 'e':
            return True
        time.sleep(0.05)
    print("Starte mit den gespeicherten Einstellungen.\n")
    return False

if __name__ == '__main__':
    if not os.path.exists(ENV_PATH) or offer_settings_change():
        run_setup()

# Load environment variables
load_dotenv(ENV_PATH)

# Additional global variable to track the first run
is_first_run = True

subprocesses = []  # List to keep track of subprocesses

def launch_progress_server():
    """Starts the overlay web server in a background thread (also works inside the .exe)."""
    import progressbarServer
    server_thread = threading.Thread(
        target=lambda: progressbarServer.app.run(port=5000, use_reloader=False),
        daemon=True,
    )
    server_thread.start()

def cleanup_subprocesses():
    """Terminates all running subprocesses initiated by this script."""
    for proc in subprocesses:
        proc.terminate()  # Terminate the subprocess
        proc.wait()       # Wait for the subprocess to exit

# Define the path for the ConnectionDumps.json file in the data subdirectory

# Retrieve environment variables
REGION = os.getenv('REGION')
EMAIL = os.getenv('EMAIL')
PASSWORD = os.getenv('PASSWORD')
USERNAME = os.getenv('USERNAME')
PRINTER_SN = os.getenv('PRINTER_SN')
PRINTER_IP = os.getenv('PRINTER_IP')
ACCESS_CODE = os.getenv('ACCESS_CODE')
BASE_DIR = os.path.join(APP_DIR, os.getenv('BASE_DIR') or 'data')
# progressbarServer reads BASE_DIR from the environment, so hand over the absolute path
os.environ['BASE_DIR'] = BASE_DIR
os.environ['APP_DIR'] = APP_DIR
os.environ['CONFIG_DIR'] = CONFIG_DIR
DUMPS_FILE_PATH = os.path.join(BASE_DIR, 'ConnectionDumps.json')
DUMP_MESSAGES = os.getenv('DUMP_MESSAGES', '0') == '1'

total_layer_num_global = None

class BambuCloud:
    def __init__(self, region: str, email: str, password: str):
        self.region = region
        self.email = email
        self.password = password
        self.auth_token = None
        self.session = requests.Session()  # Use a session for persistent connections

    def _get_authentication_token(self):
        """Authenticate and retrieve access token from Bambu Cloud with session handling and headers."""
        print("Getting accessToken from Bambu Cloud")
        
        base_url = (
            'https://api.bambulab.com/v1/user-service/user/login'
            if self.region != "China" 
            else 'https://api.bambulab.cn/v1/user-service/user/login'
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36"
        }
        payload = {
            "account": self.email,
            "password": self.password
        }
        
        response = self.session.post(base_url, headers=headers, json=payload, timeout=10)
        if response.ok:
            self.auth_token = response.json().get('accessToken')
            print("Authentication successful")
        else:
            raise ValueError(f"Authentication failed with status code {response.status_code}: {response.text}")

    def login(self):
        """Public method to initiate login and set auth_token."""
        self._get_authentication_token()

    def get_device_list(self):
        """Retrieve list of devices associated with account."""
        if not self.auth_token:
            raise ValueError("Not authenticated")
        
        print("Getting device list from Bambu Cloud")
        base_url = (
            'https://api.bambulab.com/v1/iot-service/api/user/bind'
            if self.region != "China" 
            else 'https://api.bambulab.cn/v1/iot-service/api/user/bind'
        )
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        response = self.session.get(base_url, headers=headers, timeout=10)
        if response.ok:
            devices = response.json().get('devices', [])
            return devices
        else:
            raise ValueError(f"Failed to fetch device list with status code {response.status_code}")

    def get_latest_task_for_printer(self, deviceId: str):
        """Fetches the latest task for a specific printer by device ID."""
        print(f"Fetching latest task for printer with device ID: {deviceId}")
        tasklist = self.get_tasklist()
        
        if 'hits' in tasklist:
            for task in tasklist['hits']:
                if task['deviceId'] == deviceId:
                    return task
        return None

    def get_tasklist(self):
        """Fetches the task list from Bambu Cloud."""
        print("Fetching task list from Bambu Cloud")
        base_url = (
            'https://api.bambulab.com/v1/user-service/my/tasks'
            if self.region != "China"
            else 'https://api.bambulab.cn/v1/user-service/my/tasks'
        )
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        response = self.session.get(base_url, headers=headers, timeout=10)
        if response.ok:
            return response.json()
        else:
            raise ValueError(f"Failed to fetch task list with status code {response.status_code}")

        
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR, exist_ok=True)

def get_auth_token(email, password, region):
    print("Getting accessToken from Bambu Cloud")
    # Corrected: Directly use 'region' parameter instead of 'self.region'
    base_url = 'https://api.bambulab.com/v1/user-service/user/login' if region != "China" else 'https://api.bambulab.cn/v1/user-service/user/login'
    data = {'account': email, 'password': password}  # Corrected: Directly use 'email' and 'password' parameters
    response = requests.post(base_url, json=data, timeout=10)
    if response.ok:
        auth_token = response.json()['accessToken']
        print("Authentication successful")
        return auth_token  # Return the obtained token
    else:
        raise ValueError(f"Authentication failed with status code {response.status_code}")
        
def format_remaining_time(minutes):
    """Formats remaining time from minutes to '-HhMm'."""
    hours, minutes = divmod(minutes, 60)
    return f"-{hours}h{minutes}m"

def write_to_file(filename, content):
    """Writes content to a file within the data directory, ensuring numeric content is formatted correctly."""
    try:
        path = os.path.join(BASE_DIR, f"{filename}.txt")
        with open(path, 'w') as file:
            if isinstance(content, (int, float)):
                file.write(f"{content:.2f}")  # Format as float with 2 decimal places
            else:
                file.write(str(content))  # Ensuring content is always treated as a string
        print(f"Updated {filename}.txt with content: {content}")
    except Exception as e:
        print(f"Failed to write to {filename}.txt: {e}")

def load_from_file(file_name, default=None):
    """Utility function to load data from a file, returning a default value if the file does not exist."""
    file_path = os.path.join(BASE_DIR, file_name + '.txt')
    try:
        with open(file_path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return default

def hex_to_rgb_percent(hex_color):
    """Convert hex color to an RGB percentage string."""
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgb({r/255*100}%,{g/255*100}%,{b/255*100}%)"

# Helper function to read filament color from file
def read_filament_color_from_file(tray_idx):
    color_file_path = os.path.join(BASE_DIR, f'ams{tray_idx}FilamentColor.txt')
    try:
        with open(color_file_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"File {color_file_path} not found.")
        return None

# Helper function to read active ams tray from file
def read_active_ams_tray_from_file():
    amstray_file_path = os.path.join(BASE_DIR, f'activeAmsTray.txt')
    try:
        with open(amstray_file_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"File {amstray_file_path} not found.")
        return None
    
# Function to update the SVG with colors for all trays
def update_svg_with_all_tray_colors():
    input_svg_path = os.path.join(TEMPLATE_DIR, "Filaments.svg")
    active_input_svg_path = os.path.join(TEMPLATE_DIR, "ActiveFilament.svg")
    output_svg_path = os.path.join(BASE_DIR, "Filaments.svg")
    active_output_svg_path = os.path.join(BASE_DIR, "ActiveFilament.svg")
    
    tree = ET.parse(input_svg_path)
    active_tree = ET.parse(active_input_svg_path)
    root = tree.getroot()
    active_root = active_tree.getroot()
    namespaces = {'svg': 'http://www.w3.org/2000/svg'}
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    
    # Correctly read the active tray value from file
    active_ams_tray = int(read_active_ams_tray_from_file())
    
    for tray_idx in range(1, 5):
        filament_color = read_filament_color_from_file(tray_idx)
        rgb_color = hex_to_rgb_percent(filament_color) if filament_color and filament_color != 'N/A' else None
        
        if rgb_color:
            # Update Filaments.svg
            element_id = f'Color{tray_idx}'
            element = root.find(f".//*[@id='{element_id}']", namespaces)
            if element is not None:
                element.set('fill', rgb_color)
            
            # Update ActiveFilament.svg for lines
            for line_part in ['a', 'b', 'c']:
                line_id = f'Line{tray_idx}{line_part}'
                line_element = active_root.find(f".//*[@id='{line_id}']", namespaces)
                if line_element is not None:
                    line_element.set('fill', rgb_color)
                    # Set opacity based on active tray
                    line_element.set('opacity', '0' if tray_idx != active_ams_tray else '1')

        # Set active filament tray by highlighting the corrected numbered circle
        circle_element_id = f'Circle{tray_idx}'
        circle_element = root.find(f".//*[@id='{circle_element_id}']", namespaces)
        if circle_element is not None:
            if tray_idx == active_ams_tray:
                circle_element.set('fill', 'green')  # Active tray
            else:
                circle_element.set('fill', 'gray')  # Inactive trays

    # Check if the active tray is within the expected range (1-4)
    if 1 <= active_ams_tray <= 4:
        active_tray_color = read_filament_color_from_file(active_ams_tray)
        active_rgb_color = hex_to_rgb_percent(active_tray_color) if active_tray_color and active_tray_color != 'N/A' else None
        if active_rgb_color:
            color_element = active_root.find(".//*[@id='Extruder']/*[@id='Color']", namespaces)
            if color_element is not None:
                color_element.set('fill', active_rgb_color)
                color_element.set('opacity', '1')  # Ensure the active tray color is fully opaque
    else:
        # If active_ams_tray is outside the expected range, make the extruder color transparent
        color_element = active_root.find(".//*[@id='Extruder']/*[@id='Color']", namespaces)
        if color_element is not None:
            color_element.set('opacity', '0')  # Make the extruder color transparent if no valid tray is active


    # Save the modified SVGs
    tree.write(output_svg_path, xml_declaration=True, encoding='utf-8')
    active_tree.write(active_output_svg_path, xml_declaration=True, encoding='utf-8')
    print(f"Modified SVG saved as {output_svg_path}")
    print(f"Modified ActiveFilament SVG saved as {active_output_svg_path}")
    
# Load the persisted total_layer_num at script startup
total_layer_num_global = load_from_file("total_layer_num", None)

def try_process_latest_task(force_update=False, expected_task_id=None):
    """Fetches title/cover from Bambu Cloud. Optional: the overlay also works without cloud access."""
    if not EMAIL or not PASSWORD or EMAIL == 'your_email@domain.com':
        return
    try:
        bambu_cloud = BambuCloud(REGION, EMAIL, PASSWORD)
        bambu_cloud.login()
        process_latest_task(bambu_cloud, PRINTER_SN, BASE_DIR, force_update=force_update, expected_task_id=expected_task_id)
    except Exception as e:
        print(f"Bambu Cloud not available, continuing without cover/title: {e}")

class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTP over implicit TLS (port 990), as used by the printer for its SD card."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            # The printer requires the data connection to reuse the TLS session
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size

def find_print_file(ftp, print_name, gcode_file):
    """Finds the .3mf of the current print on the SD card."""
    if gcode_file and gcode_file.lower().endswith('.3mf'):
        yield gcode_file
    for directory in ('/', '/cache'):
        try:
            entries = ftp.nlst(directory)
        except ftplib.all_errors:
            continue
        for entry in entries:
            file_name = entry.rsplit('/', 1)[-1]
            if file_name.lower().endswith('.3mf') and file_name.startswith(print_name):
                yield f"{directory.rstrip('/')}/{file_name}"

def extract_plate_image(threemf_bytes, gcode_file):
    """Returns the slicer preview of the printed plate from a .3mf file."""
    plate_match = re.search(r'plate_(\d+)', gcode_file or '')
    plate = plate_match.group(1) if plate_match else '1'
    with zipfile.ZipFile(io.BytesIO(threemf_bytes)) as archive:
        names = archive.namelist()
        for candidate in (f'Metadata/plate_{plate}.png', 'Metadata/plate_1.png'):
            if candidate in names:
                return archive.read(candidate)
        previews = sorted(n for n in names if re.fullmatch(r'Metadata/plate_\d+\.png', n))
        return archive.read(previews[0]) if previews else None

def fetch_cover_from_printer(print_name, gcode_file):
    """Loads the preview image from the printer's SD card (works without Bambu Cloud)."""
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        ftp = ImplicitFTP_TLS(context=context)
        ftp.connect(PRINTER_IP, 990, timeout=20)
        ftp.login('bblp', ACCESS_CODE)
        ftp.prot_p()
        try:
            for path in find_print_file(ftp, print_name, gcode_file):
                buffer = io.BytesIO()
                try:
                    ftp.retrbinary(f'RETR {path}', buffer.write)
                except ftplib.all_errors:
                    continue
                image = extract_plate_image(buffer.getvalue(), gcode_file)
                if image:
                    with open(os.path.join(BASE_DIR, 'printCover.png'), 'wb') as cover_file:
                        cover_file.write(image)
                    print(f"Preview image loaded from printer: {path}")
                    return
            print("No preview image found on the printer's SD card.")
        finally:
            ftp.quit()
    except Exception as e:
        print(f"Could not load preview image from printer: {e}")

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(f"device/{PRINTER_SN}/report")
    # P1/A1 only send changes, so ask once for the full status (print name etc.)
    client.publish(f"device/{PRINTER_SN}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))

# Last known print job, assembled from the (partial) MQTT messages
current_job = {'task_id': None, 'name': None, 'gcode_file': None}
previous_job_key = None

def on_message(client, userdata, msg):
    global total_layer_num_global, previous_job_key
    print(" ")
    print(f"Message received -> Topic: {msg.topic} Message: {msg.payload.decode('utf-8')}")
    try:
        message_data = json.loads(msg.payload.decode('utf-8'))

        # Convert numeric values to strings where necessary
        message_data_str = convert_all_to_str(message_data)

        # Raw message log grows quickly, so it is only written when DUMP_MESSAGES=1
        if DUMP_MESSAGES:
            with open(DUMPS_FILE_PATH, 'a') as dumps_file:
                json.dump({"timestamp": datetime.now().isoformat(), "message": message_data_str}, dumps_file, indent=4)
                dumps_file.write('\n')

        if 'print' in message_data_str:
            handle_print_data(message_data_str['print'])

            print_data = message_data_str['print']
            for key, field in (('task_id', 'task_id'), ('name', 'subtask_name'), ('gcode_file', 'gcode_file')):
                if print_data.get(field):
                    current_job[key] = print_data[field]

            # A new print job is detected by task ID + name (LAN prints always have task ID 0)
            job_key = (current_job['task_id'], current_job['name'])
            if current_job['name'] and job_key != previous_job_key:
                print("New print job detected. Fetching title and preview image.")
                previous_job_key = job_key
                # Drop title/cover of the previous print so the overlay never shows stale data
                for stale_file in ('designTitle.txt', 'printCover.png'):
                    try:
                        os.remove(os.path.join(BASE_DIR, stale_file))
                    except FileNotFoundError:
                        pass
                try_process_latest_task(force_update=True, expected_task_id=current_job['task_id'])
                # Without cloud data the preview comes straight from the printer's SD card
                if not os.path.exists(os.path.join(BASE_DIR, 'printCover.png')):
                    threading.Thread(
                        target=fetch_cover_from_printer,
                        args=(current_job['name'], current_job['gcode_file']),
                        daemon=True,
                    ).start()
    except Exception as e:
        print(f"Error processing message: {e}")


def convert_all_to_str(data):
    """Recursively convert all values in the dictionary to strings."""
    if isinstance(data, dict):
        return {k: convert_all_to_str(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_all_to_str(v) for v in data]
    else:
        return str(data)

def handle_print_data(print_data):
    global total_layer_num_global
    # Process print profile name
    if 'subtask_name' in print_data:
        write_to_file('printProfile', print_data['subtask_name'])
        write_to_file('printName', print_data['subtask_name'])

    if 'gcode_state' in print_data:
        write_to_file('printState', print_data['gcode_state'])

    # Process print progress
    if 'mc_percent' in print_data:
        write_to_file('progressPercent', f"{print_data['mc_percent']}%")
        write_to_file('progress', print_data['mc_percent'])

    if 'mc_remaining_time' in print_data:
        formatted_time = format_remaining_time(int(print_data['mc_remaining_time']))
        write_to_file('remaining_time', formatted_time)
        write_to_file('remaining_minutes', str(int(print_data['mc_remaining_time'])))

    # Process cooling fan speed
    if 'cooling_fan_speed' in print_data:
        cooling_fan_speed = float(print_data['cooling_fan_speed'])
        calculated_speed = (cooling_fan_speed / 15) * 100  # Assuming 15 is the max speed for normalization
        write_to_file('coolingFanSpeed', f"{calculated_speed:.2f}")

    # Process print speed level
    if "spd_lvl" in print_data:
        print(f"Received spd_lvl: {print_data['spd_lvl']}")
        print(f"SPEED_PROFILE keys: {list(SPEED_PROFILE.keys())}")

        spd_lvl_value = int(print_data["spd_lvl"])  # Convert spd_lvl to integer
        speed_level_name = SPEED_PROFILE.get(spd_lvl_value, "Unknown Speed Level")

        # Ensure the first letter is uppercase without altering the case of the rest of the string
        speed_level_name = speed_level_name[0].upper() + speed_level_name[1:]

        print(f"Matched speed level name: {speed_level_name}")  # Debug print
        write_to_file('printSpeed', speed_level_name)

    if "mc_print_stage" in print_data:
        print(f"Received mc_print_stage: {print_data['mc_print_stage']}")
        print(f"CURRENT_STAGE_IDS keys: {list(CURRENT_STAGE_IDS.keys())}")

        mc_print_stage_key = str(print_data['mc_print_stage'])
        mc_print_stage_name = CURRENT_STAGE_IDS.get(mc_print_stage_key, "Unknown Print Stage")
        print(f"Matched print stage name: {mc_print_stage_name}")  # Debug print
        write_to_file('printStage', mc_print_stage_name)
        
    # Process layer number
    if "layer_num" in print_data:
        write_to_file("layer_num", print_data['layer_num'])
        layer_overview_content = f"Layer: {print_data['layer_num']} / {total_layer_num_global}"
        write_to_file("layerOverview", layer_overview_content)

    # Process total layer number
    if "total_layer_num" in print_data:
        total_layer_num_global = print_data['total_layer_num']
        write_to_file("total_layer_num", print_data['total_layer_num'])

    # Process temperatures
    if 'bed_temper' in print_data:
        write_to_file('bedTemperature', f"{float(print_data['bed_temper']):.2f}")
    if 'nozzle_temper' in print_data:
        write_to_file('nozzleTemperature', f"{float(print_data['nozzle_temper']):.2f}")

    # Process AMS trays
    if 'ams' in print_data and 'ams' in print_data['ams']:
        for tray in print_data['ams']['ams'][0]['tray']:
            tray_idx = int(tray['id']) + 1  # Adjusting from 0-based to 1-based indexing
            filament_id = tray.get('tray_info_idx', 'Unknown')
            filament_color = tray.get('tray_color', 'N/A')
            filament_name = FILAMENT_NAMES.get(filament_id, "Unknown Filament")
            write_to_file(f'ams{tray_idx}FilamentId', filament_id)
            write_to_file(f'ams{tray_idx}FilamentColor', filament_color)
            write_to_file(f'ams{tray_idx}FilamentName', filament_name)

    # Process active AMS tray
    if 'ams' in print_data and 'tray_now' in print_data['ams']:
        active_tray = int(print_data['ams']['tray_now']) + 1  # Adjusting from 0-based to 1-based indexing
        write_to_file('activeAmsTray', str(active_tray))
        update_svg_with_all_tray_colors()

def format_time_hms(seconds):
    """Formats time from seconds to 'HhMmSs'."""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def process_latest_task(bambu_cloud, printer_sn, base_dir, force_update=False, expected_task_id=None):
    global is_first_run
    latest_task = bambu_cloud.get_latest_task_for_printer(printer_sn)
    if not latest_task:
        print("No cloud task found for this printer.")
        return
    # Only use cloud data that belongs to the running print (not for LAN prints or older jobs)
    if expected_task_id is not None and str(latest_task.get('id')) != str(expected_task_id):
        print("Latest cloud task does not match the running print. Skipping cloud data.")
        return
    task_id_file_path = os.path.join(base_dir, 'latest_task_id.txt')

    # Read the last processed task ID if exists
    try:
        with open(task_id_file_path, 'r') as file:
            last_processed_task_id = file.read().strip()
    except FileNotFoundError:
        last_processed_task_id = None

    current_task_id = str(latest_task.get('id'))

    # Check if this is a forced update or if the task info has changed
    if force_update or current_task_id != last_processed_task_id:
        # Extract and write required information from the task
        designTitle = latest_task.get('designTitle', 'N/A')
        printProfile = latest_task.get('title', 'N/A')
        printCover = latest_task.get('cover', 'N/A')
        totalWeight = str(latest_task.get('weight', 'N/A')) + "g"
        totalTime = int(latest_task.get('costTime', 0))
        totalTimeFormatted = format_time_hms(totalTime)  # Use the new format function

        # Write extracted information to files
        write_to_file('designTitle', designTitle)
        write_to_file('printProfile', printProfile)
        write_to_file('printCover', printCover)
        write_to_file('totalWeight', totalWeight)
        write_to_file('totalTime', totalTimeFormatted)

        # Download and save print cover image if available
        if printCover != 'N/A':
            cover_response = requests.get(printCover)
            cover_path = os.path.join(base_dir, 'printCover.png')
            with open(cover_path, 'wb') as cover_file:
                cover_file.write(cover_response.content)
            print(f"Downloaded print cover to {cover_path}")

        # Update the last processed task ID
        with open(task_id_file_path, 'w') as file:
            file.write(current_task_id)

        print("Latest task processed successfully.")
    elif not force_update and current_task_id == last_processed_task_id:
        print("No new task or already processed. Skipping update.")

    # After processing, disable force_update for subsequent runs
    if is_first_run:
        is_first_run = False


def setup_mqtt_listener():
    client = mqtt.Client()
    client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(username="bblp", password=ACCESS_CODE)
    client.connect(PRINTER_IP, 8883, 60)
    return client

def main():
    """
    Main function to initialize Bambu Cloud connection, start progress bar server,
    and handle MQTT messages for Bambu 3D printer status updates.
    """
    # Process the latest task from Bambu Cloud (optional), forcing update on the first run
    try_process_latest_task(force_update=is_first_run)

    launch_progress_server()
    print("Progress bar server started.")
    print("OBS overlay: http://localhost:5000/view/overlay")

    try:
        # Setup and start MQTT listener for real-time printer status updates
        print("Connecting to the printer's local MQTT service...")
        mqtt_client = setup_mqtt_listener()
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        print("Interrupt received, stopping...")
    except Exception as e:
        print(f"Unhandled exception: {e}")
        print("Verbindung zum Drucker fehlgeschlagen - IP-Adresse und Access Code in der .env pruefen.")
    finally:
        cleanup_subprocesses()
        print("Progress bar server stopped.")
        # Keep the .exe window open so the message can be read
        if getattr(sys, 'frozen', False):
            input("Enter druecken zum Beenden ...")

if __name__ == "__main__":
    main()
    