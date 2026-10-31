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

**Ren'Py-Installations-ZIP erstellen** verpackt freigegebene Übersetzungen für den passenden Build mit einer Spiel-EXE im Hauptordner. ZIP außerhalb des Spiels entpacken, `Install.cmd` starten, den Originalspielordner einmal wählen, Dateiplan prüfen und `INSTALL` eingeben. Das Spiel wird nicht kopiert; vorhandene Dateien werden nicht überschrieben. Konflikte stoppen die Installation. Nur Übersetzungen, `Play-Translated.cmd` und kleine Eigentumsbelege werden hinzugefügt; Originaldateien brauchen kein Backup.

`Play-Translated.cmd` im Spielordner wählt die Übersetzung. Normale Spielstände bleiben nutzbar; Spielen kann Spielstände, Caches, Logs und Bytecode verändern. Entfernen stellt keinen früheren Spielstand wieder her.

ZIP für `Remove.cmd` behalten. Spiel schließen und denselben Ordner wählen. Nur unveränderte belegte Zusätze werden entfernt; geänderte, verknüpfte oder unbekannte Dateien und Belege bleiben. Bei erzeugten Übersetzungs-`.rpyc` stoppt die Entfernung vor jedem Löschen: nur die gemeldeten Übersetzungsdateien manuell prüfen/entfernen, dann erneut versuchen. Keine anderen Spiel-`.rpyc` löschen. Alte ZIPs behalten ihr vollständiges Kopierverfahren.

CLI: `export-renpy-zip --game ... --project ... --language turkish`. Schrift, Layout und weitere Spielszenen separat prüfen.

Zeigt der Pilotbericht einen laufenden Auftrag, aktualisieren Sie ihn nach dessen Ende. Ein abgebrochener Pilot kann bewertet werden, wenn die gesamte erforderliche Stichprobe versucht wurde und Ergebnisse vorliegen. Dies ermöglicht den Gesamtauftrag bei gleichen Einstellungen und Quellen, gibt aber keine Übersetzungen frei.

Nach der Pilotbewertung gelten gespeicherte Glossar-/Stiländerungen ohne neuen Pilotlauf für neue Anfragen. Laufende Anfragen verwenden ihre ursprünglichen Regeln; vorhandene Übersetzungen bleiben unverändert. Prüfen Sie betroffene Einträge und übersetzen Sie sie bei Bedarf ausdrücklich neu. Geprüfte Piloteinstellungen verwenden stellt Modell-/Generierungswerte wieder her und behält das aktuelle Glossar und den aktuellen Stil.

In der Prüfung sendet Einträge dieser Seite erneut übersetzen bis zu 200 Einträge der sichtbaren gefilterten Seite mit aktuellen Modelleinstellungen und gespeichertem Glossar/Stil an die gemeinsame Warteschlange. Ein passender geprüfter Pilotlauf ist erforderlich. Entwürfe und laufende Einträge sind ausgeschlossen. Freigegebener Text bleibt ausgewählt; neue Kandidaten erscheinen im Verlauf. Der Übersetzungsreiter zeigt den Fortschritt.

Unter Prüfung kann **Sammelaktionen** nichtleere, exakt mit der Quelle identische Übersetzungen freigeben oder leere Übersetzungen auf Ausstehend setzen. Beide Aktionen umfassen alle Seiten der aktuellen Filter; Anzahl und Beispiele erscheinen vor der Bestätigung. Für das ganze Projekt Filter löschen. Entwürfe, wartende/laufende Einträge und bestehende Freigaben sind ausgeschlossen. Quelltextkopien können unübersetzte Sätze sein; die Freigabe ist Ihre ausdrückliche Entscheidung. Leere Einträge behalten ihren Verlauf; es werden keine Modellanfragen gesendet. Starten Sie danach unter Übersetzen einen Sammelauftrag mit der üblichen Pilotprüfung.

Beim Zurücksetzen leerer Übersetzungen auf Ausstehend sind Warteschlangeneinträge pausierter Aufträge zulässig. Die Vorschau zeigt ihre Anzahl; beim Fortsetzen werden die alten Einträge wegen der geänderten Arbeitsversion übersprungen. Auftrags- und Versuchsverlauf bleiben erhalten. Andere wartende/laufende Einträge blockieren die Aktion weiterhin; ausgeschlossene Treffer werden getrennt von fehlenden Treffern gemeldet.
