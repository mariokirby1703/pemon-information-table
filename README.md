# pemon-information-table
A table that displays various information about Geometry Dash's Platformer Demons

## Automatisierung

Der Workflow `Sync Pemon data` läuft stündlich um :03 (GitHub kann Starts
verzögern). Er liest die gefilterte Platformer-Demon-Liste seitenweise und
vergleicht Metadaten und Levelversionen mit dem letzten erfolgreichen Lauf.
Nur neue/geänderte Levels werden vollständig heruntergeladen. Es gibt keinen
bekannten öffentlichen Änderungsfeed; Listenabfragen bleiben erforderlich.
Zusätzlich werden stündlich 20 bestehende Einträge reihum vollständig geprüft,
um Änderungen zu finden, die nicht in den Listen-Metadaten erscheinen.
Jede Runde beginnt bei den zuletzt hinzugefügten Tabelleneinträgen und arbeitet
sich zu den älteren vor; der nächste Lauf setzt die Runde fort. Neu entdeckte
und geänderte Einträge werden ebenfalls vom neuesten zum ältesten verarbeitet.
Zwischen GD-Anfragen liegen mindestens fünf Sekunden (höchstens etwa zwölf
pro Minute); bei Rate Limits oder Serverfehlern kann die Wartezeit länger sein.
Diese zusätzliche Runde dauert bei 1.000 Einträgen etwa 50 Stunden.
Beim ersten Lauf oder Cacheverlust wird der Vergleichsstand neu aufgebaut;
Difficulty und Rating werden dabei direkt mit der JSON verglichen.

Neue IDs werden angehängt und erhalten in `rateDate` das Berliner Datum der
ersten Erkennung (`TT.MM.JJJJ`), kein historisch belegtes Ratingdatum.
Vorhandene Datumsangaben bleiben erhalten. Sinkende Estimated Times und
Objektzahlen bleiben ignoriert, ebenso 65535 bei bekannten höheren Zahlen.
Die bestehenden NONG/UNKNOWN-Regeln und manuelle Checkpoints bleiben erhalten.
Nur vom Server gelieferte Felder können aktualisiert werden. Gelöschte oder
ungeratete Einträge werden nicht automatisch entfernt. Fehlerhafte Antworten
brechen den Lauf vor dem Schreiben ab.

Bei Datenänderungen committet und pusht der Bot `pemons.json` und
`pemon_ids.txt` auf den Default-Branch. Ohne Datenänderungen gibt es keinen
Commit. Der Vergleichsstand liegt im Actions-Cache.
Der Workflow muss auf dem Default-Branch liegen, Actions muss aktiv sein und
Branchschutz muss Bot-Pushes zulassen. Es werden keine GD-Zugangsdaten benötigt.
Pushes mit `GITHUB_TOKEN` lösen gewöhnlich keine weiteren Actions-Workflows aus;
ein Actions-basiertes Deployment muss ausdrücklich angeschlossen werden.

Manuell: **Actions → Sync Pemon data → Run workflow**.

### HTTP 403 auf GitHub

Der erste GitHub-Lauf wurde vom GD-Server mit HTTP 403 abgewiesen, obwohl die
gleiche Listenabfrage lokal funktioniert hat. Der genaue Sperrgrund ist nicht
bekannt. Der Fünf-Sekunden-Abstand hebt eine Zugriffssperre nicht auf.
Die Node.js-Deprecation-Warnung war nicht die Fehlerursache.

Der Workflow unterstützt deshalb optional einen eigenen GitHub Actions Runner.
Nach Einrichtung eines dedizierten Runners kann unter **Settings → Secrets and
variables → Actions → Variables** die Repository-Variable `PEMON_RUNNER` auf
`["self-hosted", "Windows", "X64"]` gesetzt werden (Labels an den Runner
anpassen). Ohne diese Variable wird weiterhin `ubuntu-latest` verwendet.
Ein eigener Runner muss eingeschaltet sein, Python 3.13 über `setup-python`
bereitstellen können und vom GD-Server Zugriff erhalten. Auf öffentlichen
Repositories eigene Runner nur für vertrauenswürdige Workflows verwenden.
Die Runner-Einrichtung und Variable sind nicht automatisch vorgenommen worden.

Lokal (schreibt Daten, pusht nicht):

```sh
python -m pip install -r requirements.txt
python scripts/sync_pemons.py
python -m unittest discover -s tests
```
