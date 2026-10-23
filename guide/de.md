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
nicht zurück. Siehe [Entwicklerhilfe](../docs/installation.md).

Empfänger eines freigegebenen Übersetzungs-ZIPs wählen über `Kur.cmd` den passenden
Spielordner. `Kaldir.cmd` entfernt nur unveränderte eigene Ergänzungen. Modell und
UnityTranslator werden beim Empfänger nicht benötigt. Lizenz- und Quellmaterialien
müssen erhalten bleiben. Nicht jedes Unity-Spiel wird unterstützt; automatische Prüfungen
garantieren keine Übersetzungsqualität. Technische Diagnosen können im Original bleiben.


Quell- und Zielsprache der Spielübersetzung sind unabhängig von der Oberflächensprache. Verwenden Sie ja für Japanisch, it für Italienisch oder pt-BR für brasilianisches Portugiesisch; andere Sprachcodes können eingegeben werden. Die Quellsprache muss im Spiel vorhanden sein. Fehlende oder mehrdeutige Spalten werden abgelehnt. Das Modell muss das Sprachpaar unterstützen. Bestehende Projektsprachen, Freigaben und eigene Stilregeln bleiben erhalten; prüfen Sie ältere sprachspezifische Regeln. Prüfen Sie Schriftarten, RTL-Layout und Pluralformen mit einem kleinen Patch vor der Weitergabe. Englisch kann auch Zielsprache sein.

## Krypta FM

Für den geprüften Build die Quellsprache `en` wählen und Texte normal extrahieren. Das Profil liest drei Container zusammen: 34 TextAssets mit 442 Feldern. Zwei Quellen sind ausdrücklich ausgeschlossen; weitere Spieltexte liegen außerhalb des Profils. Nach Modellübersetzung, Prüfung und Freigabe unter Export die genehmigten TextAsset-Texte exportieren. Es entstehen vorbereitete Textdateien und ein Manifest im Projekt; ungeprüfte Felder behalten ihren Originaltext. Dies installiert keine Übersetzung und verändert keine Unity-Dateien. Die Spielinstallation wird für dieses Profil nicht unterstützt. Ältere App-Versionen vor dem Öffnen eines Schema-5-Projekts schließen.

In den erweiterten Modelleinstellungen lässt sich der Denkmodus für LM-Studio-Anfragen optional deaktivieren. Dadurch kann mehr Ausgabebudget für die Übersetzung bleiben. Die Unterstützung hängt vom geladenen Modell und Server ab; eine nicht unterstützte Option kann den Auftrag stoppen. Standardwerte und globale Servereinstellungen bleiben erhalten.

Profilversion 2 liest außerdem sieben englische Tagebuchziele aus statischen Metadaten. Insgesamt werden 449 Felder aus 34 TextAssets und einem Tagebuchraster erfasst; bisherige Quellidentitäten und Freigaben bleiben erhalten. Der neue Tagebuch-Hook wurde nur kompiliert und synthetisch getestet; der frühere Menüpilot mit drei Beschriftungen wurde im Spiel beobachtet. Die normale Krypta-Installation über die Oberfläche ist noch nicht unterstützt.
