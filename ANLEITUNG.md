# Bambu2OBS – Druck-Overlay für OBS (Anleitung auf Deutsch)

Dieses Overlay zeigt in OBS live an, **was gerade gedruckt wird**, einen **pinken Fortschrittsbalken** und **wie lange der Druck noch braucht** (inklusive voraussichtlicher Uhrzeit, wann er fertig ist).

![Overlay-Beispiel](images/overlay_example.png)

Das Programm läuft auf dem PC, auf dem auch OBS läuft, und liest die Daten direkt vom Bambu-Drucker im eigenen WLAN aus.

---

## 1. Was du brauchst

- Einen **Bambu Lab Drucker** (X1, P1, A1 …) im selben Netzwerk wie der PC
- **OBS Studio**
- **Python 3** – Download unter https://www.python.org/downloads/
  ⚠️ Beim Installieren unbedingt das Häkchen **„Add python.exe to PATH“** setzen!

## 2. Programm herunterladen

Auf dieser GitHub-Seite oben auf den grünen Button **„Code“** → **„Download ZIP“** klicken und die ZIP-Datei z. B. nach `C:\Bambu2OBS` entpacken.

## 3. Einmalig einrichten

1. Den Ordner `C:\Bambu2OBS` im Explorer öffnen, oben in die Adresszeile klicken, `cmd` eintippen und Enter drücken. Es öffnet sich ein schwarzes Fenster (Eingabeaufforderung) direkt in diesem Ordner.
2. Diese Befehle nacheinander eingeben (jeweils mit Enter bestätigen):

   ```
   python -m venv b2obsvenv
   b2obsvenv\Scripts\activate
   pip install -r requirements.txt
   ```

## 4. Drucker-Daten eintragen

1. Die Datei `example.env` kopieren und die Kopie in **`.env`** umbenennen (ohne „example“, mit Punkt am Anfang).
2. Die `.env` mit dem Editor öffnen und ausfüllen:

   | Eintrag | Wo finde ich das? |
   |---|---|
   | `PRINTER_IP` | Am Drucker-Display unter **Einstellungen → WLAN/Netzwerk** (z. B. `192.168.178.45`) |
   | `ACCESS_CODE` | Am Drucker-Display unter **Einstellungen → WLAN/Netzwerk** („Access Code“ / „Zugangscode“) |
   | `PRINTER_SN` | Seriennummer: am Drucker unter **Einstellungen → Gerät**, oder in Bambu Studio / Bambu Handy |
   | `EMAIL`, `PASSWORD` | **Optional.** Bambu-Konto-Daten – damit kommen Modellname und Vorschaubild aus der Bambu Cloud. |
   | `REGION` | `global` lassen |
   | `BASE_DIR` | `data` lassen |

   **Tipp:** Wenn die Cloud-Anmeldung Probleme macht (z. B. wegen Bestätigungscode per Mail), `EMAIL` und `PASSWORD` einfach leer lassen. Dann wird statt des Modellnamens der Dateiname des Drucks angezeigt – Balken und Restzeit funktionieren trotzdem.

## 5. Starten

Jedes Mal vor dem Streamen im Ordner `C:\Bambu2OBS` eine Eingabeaufforderung öffnen (siehe Schritt 3.1) und eingeben:

```
b2obsvenv\Scripts\activate
python src\bambu2obs.py
```

Das Fenster offen lassen, solange das Overlay laufen soll. Beenden mit **Strg + C**.

## 6. In OBS einbinden

1. In OBS bei **Quellen** auf **+** → **Browser** klicken.
2. Als URL eintragen:

   ```
   http://localhost:5000/view/overlay
   ```

3. **Breite: 600**, **Höhe: 130** – fertig. Die Quelle lässt sich danach beliebig im Bild verschieben und skalieren.

### Aussehen anpassen (optional)

Einfach an die URL anhängen:

| Zusatz | Wirkung |
|---|---|
| `?color=ff4fa3` | Farbe des Balkens (Hex-Farbcode ohne `#`), Standard ist Pink |
| `?card=0` | Ohne dunklen Hintergrund-Kasten |
| `?cover=0` | Ohne Vorschaubild |

Mehrere kombinieren mit `&`, z. B. `http://localhost:5000/view/overlay?color=c026d3&card=0`

## 7. Wenn etwas nicht klappt

- **Overlay bleibt leer / zeigt „–“:** Läuft das schwarze Fenster noch? Startet gerade ein Druck? Die Daten kommen erst, sobald der Drucker welche sendet.
- **Keine Verbindung zum Drucker:** IP-Adresse und Access Code nochmal prüfen. Bei neueren Firmware-Versionen muss am Drucker eventuell der **LAN-Modus** bzw. **Entwicklermodus** aktiviert werden, damit externe Programme mitlesen dürfen.
- **„python“ wird nicht gefunden:** Python wurde ohne das Häkchen „Add to PATH“ installiert → Python nochmal installieren und das Häkchen setzen.
