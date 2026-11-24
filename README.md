# pemon-information-table
A table that displays various information about Geometry Dash's Platformer Demons

## Einmal pro Tag automatisch bei Windows-Anmeldung

Nach Installation gibt es nur **Pemon Daily Sync**, mit einem Ausloeser:

- Beim Anmelden an Windows (auch nach PC-Neustart).

Der erste **erfolgreiche** Lauf eines Berliner Kalendertags zaehlt.
In `.sync-state/last-success.json` wird das Datum gespeichert. Weitere
Starts am selben Tag ueberspringen den Scan, auch wenn du den PC
mehrmals neu startest. Schlaegt der Abgleich fehl, darf der naechste
Start am selben Tag erneut versuchen. Ein Logon ist eine Windows-Anmeldung,
kein Start vor dem Login. Bleibt der PC tagelang angemeldet, gibt es
bewusst keinen neuen Lauf bis zur naechsten Windows-Anmeldung. Der PC muss eingeschaltet, der Benutzer
angemeldet und das Netzwerk verfuegbar sein.

Der taegliche **leichte Watch-Modus** geht durch die Seiten der
GD-Suche nach offiziell gerateten Platformer Demons. Dabei gleicht
er Level-IDs, Ratings, Difficulty, Metadaten-Fingerprints und Creator-
Usernames ab. **Er laedt nicht alle Levels einzeln erneut herunter.**
Nur neu entdeckte bzw. veraenderte Levels werden vollstaendig abgefragt.
Reine Creator-Umbenennungen aus den GD-Suchergebnissen brauchen keinen
Level-Download. Dies reduziert die Anzahl an GD-Anfragen erheblich,
aber der komplette Suchseiten-Scan bleibt notwendig, um auch aeltere
geanderte Eintraege und Usernamen zu erkennen. Es ist kein Echtzeit-Push.
Der GD-Server kann Anfragen blockieren; die Anfragen werden begrenzt.

Vorhandene Eintraege werden nicht automatisch geloescht.
Bisherige Rating-Daten, manuelle Checkpoints, NONG/UNKNOWN-Regeln und
andere manuelle Felder bleiben erhalten; neue Levels erhalten den
Berliner Tag ihrer ersten Erkennung als `rateDate`.
Der Git-Push erfolgt nur bei Datenveraenderungen. Eine separate
Arbeitskopie liegt in `.sync-state/checkout`; offene Projektdateien
werden nicht ueberschrieben. Das Log ist `.sync-state/daily-sync.log`.

### Einmalige Einrichtung nach dem Update

Im lokalen Repository in PowerShell:

```powershell
git pull
.\.sync-state\venv\Scripts\python.exe -m unittest discover -s tests
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/install_daily_sync.ps1
```

Das Installationsskript aktualisiert **Pemon Daily Sync** auf den Anmelde-Ausloeser und **loescht die alte Aufgabe Pemon Rating Watch**.

Manuell ausloesen (die Tages-Sperre bleibt aktiv):

```powershell
Start-ScheduledTask -TaskName 'Pemon Daily Sync'
```

Fuer einen ausdruecklich erzwungenen Testlauf (auch am selben Tag)
oder den selten gewuenschten Vollabgleich:

```powershell
.\.sync-state\venv\Scripts\python.exe scripts/run_daily_sync.py --force
.\.sync-state\venv\Scripts\python.exe scripts/run_daily_sync.py --force --all
```

Nur ein erfolgreicher Lauf beider Listen zaehlt als Tageslauf.
Einzelne Listen lassen sich jederzeit manuell pruefen, ohne den Tagesmarker
zu veraendern:

```powershell
.\.sync-state\venv\Scripts\python.exe scripts/run_daily_sync.py --force --unrated-only
.\.sync-state\venv\Scripts\python.exe scripts/run_daily_sync.py --force --rated-only
```

Dabei wird nur die jeweilige Liste gescannt; bei einem Rating-Wechsel
werden beide Listen gemeinsam aktualisiert und gestaged. Ohne Scope-Parameter bleiben beide Listen aktiv. Mit `--all`
werden alle Eintraege der gewaehlten Liste erneut heruntergeladen.
Mit `--check` wird nur der GitHub-Zugriff ueberprueft und kein
erfolgreicher Tageslauf gespeichert.

## GitHub Actions

Der bisherige stündliche GitHub-Zeitplan ist entfernt. Der Workflow bleibt
manuell startbar. Der erste GitHub-Runner wurde vom GD-Server mit HTTP 403
abgewiesen; die Node.js-Warnung war nicht die Ursache. Der tägliche Windows-Lauf
verwendet keinen GitHub Actions Runner. Optional kann ein manueller Workflow
über die Repository-Variable `PEMON_RUNNER` andere Runner-Labels erhalten.



## Unrated / Hyped Platformer Demons

The same daily run also scans GD's Hyped search (type 31, demon,
platformer, noStar). It writes `src/assets/unrated-pemon-ids.txt` and
`src/assets/unrated-pemons.json`, which the website shows under
**Unrated Pemons** at `/unrated-pemons`.

This tracks discovered and manually added unrated levels permanently until
they receive a rating (or are verified not to be platformers). Leaving Hyped
alone does not remove a level. Tracked IDs outside Hyped are checked directly
each run. A newly rated platformer demon is moved to the rated JSON and ID
list, even in unrated-only mode, without scanning the full rated search.
Rated-only scans remove duplicates from unrated data without querying Hyped.
Unrated metadata uses the same schema and conservative merge rules as rated
data, with rating Unrated and firstSeen instead of a rate date. Only new
or changed Hyped entries and tracked IDs outside Hyped are downloaded;
creator names are refreshed from search.
An explicit full sync also refreshes all currently hyped entries. A failed
or ambiguous Hyped search does not overwrite the previous snapshot.
The unofficial API's filtering and availability depend on the GD server.

Hyped search results may describe a suggested rating rather than an official
Demon flag. The filtered search supplies candidates; the download endpoint
verifies that each new or changed candidate is a platformer with zero awarded
moons. The log shows the raw search difficulty, Demon flag, star and length
fields as well as the download verification. Unrated levels use the generic
Demon label instead of claiming an official Demon tier.

### Manually add unrated IDs

Append one numeric ID per line to `src/assets/unrated-pemon-ids.txt`, then
commit and push that file before running the daily sync. The automation uses
its own checkout and cannot see uncommitted local edits.

```powershell
git add src/assets/unrated-pemon-ids.txt
git commit -m "Add tracked unrated platformer demons"
git push
.\.sync-state\venv\Scripts\python.exe scripts/run_daily_sync.py --force --unrated-only
```

Manually added IDs are treated as demon candidates. Unrated levels have no
official demon tier to verify. An individual download returning `-1` removes the level from both the
unrated TXT and JSON files without aborting the run. This also applies to
temporarily unavailable levels; if rediscovered in Hyped or manually added
again, they can be included again. Other invalid responses and HTTP errors
still abort the sync rather than silently discarding data.

### Interrupted syncs / resume

Each successfully processed level (including removals and rating transitions)
is checkpointed immediately in `.sync-state/unrated-progress.json` or
`.sync-state/rated-progress.json` using atomic writes. After an interruption,
rerun the same sync command. Search pages are scanned again, but completed
level downloads are reused if their source metadata and existing record still
match. Checkpoints are kept outside the Git checkout and cleared only after
the respective data files have been saved successfully. The public website
is updated after the usual successful commit/push, not after every download.
