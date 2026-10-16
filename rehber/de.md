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
   Sie ihn, bevor Sie den Gesamtauftrag starten. Wählen Sie 1–16 parallele Anfragen
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
nicht zurück. Siehe [Entwicklerhilfe](../docs/development.md).

Empfänger eines freigegebenen Übersetzungs-ZIPs wählen über `Kur.cmd` den passenden
Spielordner. `Kaldir.cmd` entfernt nur unveränderte eigene Ergänzungen. Modell und
UnityTranslator werden beim Empfänger nicht benötigt. Lizenz- und Quellmaterialien
müssen erhalten bleiben. Nicht jedes Unity-Spiel wird unterstützt; automatische Prüfungen
garantieren keine Übersetzungsqualität. Technische Diagnosen können im Original bleiben.


Quell- und Zielsprache der Spielübersetzung sind unabhängig von der Oberflächensprache. Verwenden Sie ja für Japanisch, it für Italienisch oder pt-BR für brasilianisches Portugiesisch; andere Sprachcodes können eingegeben werden. Die Quellsprache muss im Spiel vorhanden sein. Fehlende oder mehrdeutige Spalten werden abgelehnt. Das Modell muss das Sprachpaar unterstützen. Bestehende Projektsprachen, Freigaben und eigene Stilregeln bleiben erhalten; prüfen Sie ältere sprachspezifische Regeln. Prüfen Sie Schriftarten, RTL-Layout und Pluralformen mit einem kleinen Patch vor der Weitergabe. Englisch kann auch Zielsprache sein.
