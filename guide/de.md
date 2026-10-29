# UnityTranslator – Benutzerhandbuch

## Installation und Sprache

Entpacken Sie unter Windows x64 das **gesamte** Anwendungs-ZIP in einen eigenen Ordner
und starten Sie `UnityTranslator.exe`. Das fertige Paket benötigt kein Python.
Start aus dem Quellcode:

```powershell
uv sync --locked --extra ui
uv run --extra ui unitytranslator gui
```

Die Standardsprache ist Englisch. Unter **Language** neben **Help** stehen acht Sprachen
zur Auswahl. Die Änderung gilt nach dem nächsten Programmstart und ändert nicht die
Quell- oder Zielsprache des Projekts.

## Übersetzen

1. **Projekt:** Wählen Sie den Spielordner und einen separaten Projektordner sowie die
   Sprachcodes. Öffnen Sie vorhandene Projekte, um Ihre Arbeit fortzusetzen.
2. **Texte:** Prüfen Sie die Kompatibilität, wählen Sie eine unterstützte Quelle und
   extrahieren Sie die Texte. Lese- und Installationsunterstützung werden getrennt geprüft.
3. **Modell:** Starten Sie LM Studio oder llama-server und laden Sie selbst ein Modell.
   Tragen Sie die lokale Adresse und Modell-ID ein und testen Sie die Verbindung.
4. **Glossar:** Ergänzen Sie bei Bedarf geschützte Namen, Fachbegriffe und Stilregeln.
5. **Übersetzen:** Führen Sie zuerst einen repräsentativen Pilotlauf durch und prüfen
   Sie ihn, bevor Sie den Gesamtauftrag starten. Wählen Sie 1–36 parallele Anfragen
   passend zum Server. Minimieren stoppt den Auftrag nicht. Pause wartet auf laufende
   Anfragen; Abbrechen beendet die Client-Aufgaben.
6. **Prüfen:** Vergleichen und bearbeiten Sie Texte, speichern Sie und genehmigen Sie
   anschließend. Ein gespeicherter Entwurf ist keine Genehmigung. Die Seitengenehmigung
   gilt nur für ausgewählte geeignete Einträge. Bei der Genehmigung aller Übersetzungen
   bestätigen Sie erst Umfang und Warnungen und geben dann den angezeigten Satz genau
   ein. Bis zur letzten Schaltfläche können Sie abbrechen. Entwürfe und Formatfehler
   bleiben ausgenommen; bei Änderungen an der Vorschau wird nichts teilweise genehmigt.

## Sichern, installieren und teilen

Exportieren Sie JSON oder eine Projektsicherung. Schließen Sie das Spiel vor der
Installation. Lassen Sie unter „Auf Spiel anwenden“ einen Plan erstellen, prüfen Sie
die neuen Dateien und bestätigen Sie separat. Starten Sie das Spiel selbst und prüfen
Sie Zeichen, Layout und Bedeutung. Die Spielintegration ist experimentell.

Entfernen Sie Ergänzungen über das ursprüngliche Projekt. Überschreiben oder löschen
Sie `winhttp.dll`/`doorstop_config.ini` nicht blind und setzen Sie das Originalinventar
nicht zurück. Siehe [Entwicklerhilfe](../docs/installation.md).

Empfänger eines freigegebenen Übersetzungs-ZIPs wählen über `Kur.cmd` den passenden
Spielordner. `Kaldir.cmd` entfernt nur unveränderte eigene Ergänzungen. Modell und
UnityTranslator werden beim Empfänger nicht benötigt. Lizenz- und Quellmaterialien
müssen erhalten bleiben. Nicht jedes Unity-Spiel wird unterstützt; automatische Prüfungen
garantieren keine Übersetzungsqualität. Technische Diagnosen können im Original bleiben.


Quell- und Zielsprache der Spielübersetzung sind unabhängig von der Oberflächensprache. Verwenden Sie ja für Japanisch, it für Italienisch oder pt-BR für brasilianisches Portugiesisch; andere Sprachcodes können eingegeben werden. Die Quellsprache muss im Spiel vorhanden sein. Fehlende oder mehrdeutige Spalten werden abgelehnt. Das Modell muss das Sprachpaar unterstützen. Bestehende Projektsprachen, Freigaben und eigene Stilregeln bleiben erhalten; prüfen Sie ältere sprachspezifische Regeln. Prüfen Sie Schriftarten, RTL-Layout und Pluralformen mit einem kleinen Patch vor der Weitergabe. Englisch kann auch Zielsprache sein.

## Krypta FM

Für den passenden Krypta-FM-Build `en` als Quelle und `tr` als Ziel wählen. Profil 2 umfasst 449 Felder aus 34 TextAssets und einem Tagebuchraster; zwei Quellen und weitere UI-/Bildtexte bleiben ausgeschlossen. IDs und Freigaben bleiben erhalten.

Nach Prüfung und Freigabe das Spiel schließen und unter „Auf Spiel anwenden“ den Plan für die zwei neuen Dateien `winhttp.dll` und `doorstop_config.ini` prüfen. Die experimentelle Laufzeit bleibt im separaten Projekt; Originaldateien werden nicht ersetzt. Zusätze über dasselbe Projekt entfernen. Textexporte sind keine Installationspakete; teilbare Installations-ZIPs unterstützen auch den passenden Krypta-Build en→tr. Empfänger starten Install.cmd, prüfen den Dateiplan und geben INSTALL ein; Uninstall.cmd entfernt nur unveränderte eigene Zusätze. Die portable Kombination wurde synthetisch geprüft; eine eigene Prüfung im Spiel steht aus. Start/Menü, Optionen, Übergang ins Spiel, Pause und Untertitel wurden beobachtet. Andere Ansichten, Sprachwechsel und Textlayout müssen manuell geprüft werden; eine lange Optionsbeschriftung kann ihren Hilfetext überlagern.

In den erweiterten Modelleinstellungen lässt sich der Denkmodus für LM-Studio-Anfragen optional deaktivieren. Dadurch kann mehr Ausgabebudget für die Übersetzung bleiben. Die Unterstützung hängt vom geladenen Modell und Server ab; eine nicht unterstützte Option kann den Auftrag stoppen. Standardwerte und globale Servereinstellungen bleiben erhalten.

## Ren'Py-Übersetzung

Wählen Sie unter Texte die Engine und scannen Sie das Spiel. Eine Datei unter
`game/tl/<Sprache>/*.rpy` liest den gesamten Sprachordner. Ursprüngliche `.rpy`,
verifizierte `_ren.py` und RPA-3.0-Archive mit Quellen werden anhand geprüfter
Quellverträge aus Ren'Py 8.1.2 und 8.3.6 kontrolliert. Die Versionsnummer allein
gewährt keine Unterstützung. Große Mengen und überschneidungsfreie lose Dateien
und Archive werden unterstützt; gleiche Pfade oder Quellbasisnamen werden abgelehnt.
Abgedeckt sind einzeilige Dialoge mit Charakter- und temporären `@`-Attributen,
`nointeract`, ausdrückliche `_()`-Schlüssel und Menütexte. Menüsätze müssen vor den
Auswahlmöglichkeiten stehen und dürfen nicht mit Überschriften gemischt werden.
Voice/nvl-Gruppen, mehrzeilige Dialoge, dynamischer Text, rein kompilierte Eingaben
und Bildbeschriftungen bleiben ausgeschlossen. Beachten Sie die gemeldeten Lücken.
Spielcode wird nicht ausgeführt. Große Exporte können nummerierte Dateien enthalten;
bewahren Sie den vollständigen Export zusammen auf.

Installations-ZIPs bleiben auf Ren'Py `8.1.2.23090503` beschränkt; private Repository-, KI-Werkzeug- oder Zugangsdaten verhindern die Kopierpaketierung.

Verwenden Sie die vorhandene Modell-, Pilot-, Entwurfs- und Freigabeprüfung.
Vorlagentexte bleiben im Verlauf schreibgeschützt und werden nicht automatisch
freigegeben. Geben Sie nach menschlicher Freigabe eine Ren'Py-Zielkennung wie
`turkish` ein; Sprachcodes werden nicht automatisch zugeordnet. Entwürfe zuerst
abschließen oder verwerfen. Native Dateien werden nur im Projekt vorbereitet;
widersprüchliche freigegebene globale Schlüssel verhindern den Export.

**Ren'Py-Installations-ZIP erstellen** unterstützt den passenden Build mit genau
einer Spiel-EXE im Hauptordner. Das ZIP enthält keine Spielinhalte. Entpacken Sie
es außerhalb des Originals und starten Sie `Install.cmd`. Wählen Sie das passende
Original und einen separaten Ausgabeordner, dann prüfen Sie den genauen Dateiplan.
Die Installation erstellt eine vollständige übersetzte Kopie und benötigt zusätzlichen
Speicher. Originaldateien werden nicht ersetzt und das Spiel wird nicht gestartet.
`Play-Translated.cmd` in der Kopie startet die gewählte Sprache. Originalspielstände,
Logs und Caches werden nicht kopiert; neue Spielstände bleiben getrennt.
Empfänger benötigen weder Python noch ein Modell noch UnityTranslator.

Bewahren Sie das ZIP für `Remove.cmd` auf. Nur unveränderte eigene Kopiedateien
werden entfernt; geänderte oder neu erzeugte Laufzeitdateien und Belege bleiben
erhalten. Der Ordner wird nicht vollständig geleert.
CLI: `export-renpy-zip --game ... --project ... --language turkish`.
Direkte Installation in den Originalordner bleibt nicht unterstützt.

Zeigt der Pilotbericht einen laufenden Auftrag, aktualisieren Sie ihn nach dessen Ende. Ein abgebrochener Pilot kann bewertet werden, wenn die gesamte erforderliche Stichprobe versucht wurde und Ergebnisse vorliegen. Dies ermöglicht den Gesamtauftrag bei gleichen Einstellungen und Quellen, gibt aber keine Übersetzungen frei.

Nach der Pilotbewertung gelten gespeicherte Glossar-/Stiländerungen ohne neuen Pilotlauf für neue Anfragen. Laufende Anfragen verwenden ihre ursprünglichen Regeln; vorhandene Übersetzungen bleiben unverändert. Prüfen Sie betroffene Einträge und übersetzen Sie sie bei Bedarf ausdrücklich neu. Geprüfte Piloteinstellungen verwenden stellt Modell-/Generierungswerte wieder her und behält das aktuelle Glossar und den aktuellen Stil.
