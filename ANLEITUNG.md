# Bambu2OBS – Druck-Overlay für OBS (Anleitung auf Deutsch)

Dieses Overlay zeigt in OBS live an, **was gerade gedruckt wird**, einen **pinken Fortschrittsbalken** und **wie lange der Druck noch braucht** (inklusive voraussichtlicher Uhrzeit, wann er fertig ist).

![Overlay-Beispiel](images/overlay_example.png)

Das Programm läuft auf dem PC, auf dem auch OBS läuft, und liest die Daten direkt vom Bambu-Drucker im eigenen WLAN aus.

---

## 1. Was du brauchst

- Einen **Bambu Lab Drucker** (X1, P1, A1 …) im selben Netzwerk wie der PC
- **OBS Studio** auf einem Windows-PC

Python oder sonstige Programme brauchst du **nicht**.

## 2. Herunterladen

1. Rechts auf dieser GitHub-Seite unter **„Releases“** die neueste Version öffnen.
2. **`Bambu2OBS-Windows-….zip`** herunterladen und in einen eigenen Ordner entpacken, z. B. `C:\Bambu2OBS`.

## 3. Erster Start

1. **`Bambu2OBS.exe`** doppelklicken.
   Falls Windows „Der Computer wurde durch Windows geschützt“ anzeigt: auf **„Weitere Informationen“** → **„Trotzdem ausführen“** klicken. (Das kommt bei kleinen Programmen ohne gekaufte Signatur.)
2. Im schwarzen Fenster wirst du einmalig nach diesen Angaben gefragt:

   - **IP-Adresse** und **Access Code**
   - **Seriennummer**
   - **E-Mail / Passwort** des Bambu-Kontos: **optional**, einfach mit Enter überspringen. Mit Bambu-Konto wird der Modellname von MakerWorld angezeigt, ohne Konto der Dateiname des Drucks.

   Wo du IP-Adresse, Access Code und Seriennummer findest, steht im nächsten Abschnitt.

   Die Angaben werden in der Datei `.env` neben der .exe gespeichert. Zum Ändern diese Datei löschen und die .exe neu starten.

### Wo finde ich IP-Adresse, Access Code und Seriennummer?

Die Menünamen können je nach Modell und Firmware leicht abweichen.

**IP-Adresse und Access Code** stehen direkt am Drucker-Display:

- **A1 / A1 mini / P1S / P1P:** Zahnrad (Einstellungen) → **WLAN**. Dort stehen die IP-Adresse (z. B. `192.168.178.45`) und der **Access Code** (8 Zeichen aus Zahlen und Buchstaben).
- **X1 / X1C:** Zahnrad → Reiter **Netzwerk**. Dort stehen dieselben Angaben.

Den Access Code am besten direkt beim ersten Start vom Display ablesen. Er kann sich ändern, z. B. nachdem der Drucker zurückgesetzt wurde.

**Seriennummer**, eine dieser Stellen reicht:

- Am Drucker: Einstellungen → **Gerät** bzw. Geräteinformationen
- In **Bambu Handy** (Handy-App): Drucker antippen → Einstellungen → Geräteinformationen
- In **Bambu Studio**: Reiter **Gerät** → Bereich **Update**, dort steht sie neben der Firmware-Version
- Auf dem Aufkleber am Drucker (meist hinten oder unten), die Nummer hinter „SN“

## 4. Jedes Mal vor dem Streamen

**`Bambu2OBS.exe`** starten und das schwarze Fenster offen lassen, solange das Overlay laufen soll. Zum Beenden das Fenster schließen.

## 5. Alternative: mit Python starten (für Bastler)

Mit installiertem Python 3 im Projektordner:

```
python -m venv b2obsvenv
b2obsvenv\Scripts\activate
pip install -r requirements.txt
python src\bambu2obs.py
```

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
| `?name=Printcess` | Name des Druckers, dann steht da z. B. „Printcess druckt gerade“ oder „Printcess ist fertig!“ |
| `?color=ff4fa3` | Farbe des Balkens (Hex-Farbcode ohne `#`), Standard ist Pink |
| `?card=0` | Ohne dunklen Hintergrund-Kasten |
| `?cover=0` | Ohne Vorschaubild |

Mehrere kombinieren mit `&`, z. B. `http://localhost:5000/view/overlay?name=Printcess&color=c026d3`

Die URL änderst du in OBS mit einem Doppelklick auf die Browserquelle.

## 7. Auf eine neue Version updaten

1. Bambu2OBS schließen (das schwarze Fenster).
2. Unter **„Releases“** auf dieser GitHub-Seite die neueste `Bambu2OBS-Windows-….zip` herunterladen.
3. Aus der ZIP nur die **`Bambu2OBS.exe`** in deinen Ordner (z. B. `C:\Bambu2OBS`) kopieren und die alte ersetzen.
4. Die **`.env`** im Ordner **nicht löschen**, darin stehen deine Drucker-Daten. Dann musst du nichts neu eingeben.
5. Bambu2OBS wieder starten. Falls das Overlay in OBS noch alt aussieht: Browserquelle anklicken → **„Seite aktualisieren“** bzw. in den Eigenschaften „Cache der aktuellen Seite aktualisieren“.

Die Versionsnummer steht im Namen der ZIP-Datei, z. B. `Bambu2OBS-Windows-v1.2.0.zip`. Ist die Nummer auf GitHub höher als bei deiner Datei, gibt es etwas Neues.

## 8. Wenn etwas nicht klappt

- **Overlay bleibt leer / zeigt „–“:** Läuft das schwarze Fenster von Bambu2OBS noch? Startet gerade ein Druck? Die Daten kommen erst, sobald der Drucker welche sendet.
- **Keine Verbindung zum Drucker:** IP-Adresse und Access Code nochmal prüfen (`.env` löschen und neu starten). Bei neueren Firmware-Versionen muss am Drucker eventuell der **LAN-Modus** bzw. **Entwicklermodus** aktiviert werden, damit externe Programme mitlesen dürfen.
- **Kein Vorschaubild:** Das Bild wird bei jedem neuen Druck von der **SD-Karte im Drucker** geholt. Ohne SD-Karte geht das nicht. Bei einem Druck, der schon lief, bevor Bambu2OBS gestartet wurde, kann es ein paar Sekunden dauern.
- **Overlay ging, nach ein paar Tagen aber nicht mehr:** Der Router hat dem Drucker vermutlich eine neue IP-Adresse gegeben. Im Router eine feste Adresse einstellen (FritzBox: **Heimnetz → Netzwerk** → beim Drucker auf den Stift klicken → **„Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen“**). Danach die `.env` neben der .exe löschen und die .exe neu starten.
