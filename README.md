# pemon-information-table
A table that displays various information about Geometry Dash's Platformer Demons

## Täglicher Abgleich auf Windows

Die Windows-Aufgabe **Pemon Daily Sync** startet täglich um **20:00 Uhr Ortszeit**
(auf diesem PC Europe/Berlin). Der PC muss eingeschaltet und der Benutzer
angemeldet sein; eine gesperrte Sitzung reicht. Verpasste Starts darf Windows
bei nächster Gelegenheit nachholen. Der Lauf weckt den PC nicht automatisch.

Der Abgleich prüft täglich alle vorhandenen Levels, zuletzt hinzugefügte zuerst.
Zwischen GD-Anfragen liegen mindestens fünf Sekunden (etwa zwölf pro Minute),
bei Rate Limits/Serverfehlern länger. Ein vollständiger Lauf kann mehrere Stunden
dauern. Gleichzeitig kann nur eine Instanz der Windows-Aufgabe laufen.

Neue Platformer Demons werden über die gefilterte Suche gefunden und angehängt.
Sie erhalten in `rateDate` das Berliner Datum der ersten Erkennung
(`TT.MM.JJJJ`), kein historisch belegtes Ratingdatum. Vorhandene Datumsangaben
bleiben erhalten. Sinkende Estimated Times und Objektzahlen werden ignoriert,
ebenso 65535 bei bekannten höheren Zahlen. Die NONG/UNKNOWN-Regeln sowie
manuelle Checkpoints und Zusatzfelder bleiben erhalten. Nur vom Server
bereitgestellte Werte können aktualisiert werden. Gelöschte oder ungeratete
Einträge werden nicht automatisch entfernt. Fehlerhafte Antworten brechen den
Abgleich vor dem Schreiben ab.

Der Lauf verwendet eine separate Arbeitskopie in `.sync-state/checkout`.
Offene Projektdateien werden nicht verändert. Datenänderungen werden mit der
lokalen Git-Identität committet und über Git Credential Manager auf `main`
gepusht. Ohne Datenänderungen gibt es keinen Commit. Neue Daten im normalen
Projektordner anschließend über **Pull origin** holen. Das Repository darf
nicht verschoben werden, ohne die Windows-Aufgabe neu einzurichten.

Status und Protokolle:

- Windows-Aufgabenplanung → **Pemon Daily Sync** (Ergebnis `0` = erfolgreich).
- `.sync-state/daily-sync.log`: Fortschritt und Fehler des täglichen Laufs.
- `.sync-state/preflight.log`: Prüfung von Arbeitskopie und GitHub-Pushzugang.
- GitHub-Commits: `chore: daily platformer demon data sync` bei Datenänderungen.

Einrichtung bzw. erneute Einrichtung im Projektordner:

```powershell
python -m venv .sync-state/venv
.\.sync-state\venv\Scripts\python.exe -m pip install -r requirements.txt
git credential-manager github login --browser
.\.sync-state\venv\Scripts\python.exe scripts/run_daily_sync.py --check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/install_daily_sync.ps1
```

Manuell denselben vollständigen Lauf starten:

```powershell
Start-ScheduledTask -TaskName 'Pemon Daily Sync'
```

Nur lokal aktualisieren, ohne automatischen Commit/Push:

```sh
python scripts/sync_pemons.py --all
python -m unittest discover -s tests
```

## GitHub Actions

Der bisherige stündliche GitHub-Zeitplan ist entfernt. Der Workflow bleibt
manuell startbar. Der erste GitHub-Runner wurde vom GD-Server mit HTTP 403
abgewiesen; die Node.js-Warnung war nicht die Ursache. Der tägliche Windows-Lauf
verwendet keinen GitHub Actions Runner. Optional kann ein manueller Workflow
über die Repository-Variable `PEMON_RUNNER` andere Runner-Labels erhalten.
