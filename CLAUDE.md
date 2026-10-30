# Up Front – Hinweise für Claude

Digitale Umsetzung des Kartenspiels Up Front (Python + Arcade). Server: `cardserver.py`, Client: `cardgame.py`. Aktuell nur Szenario A, Nationen: Deutsche vs. Amerikaner.

## Umfang

- Vorerst nur Regeln bis zum „STOP“-Hinweis für Szenario A umsetzen: Kapitel 1–16 (Regelbuch-PDF S. 1–28, Ende nach 16.5). Regeln ab Kapitel 17 (Flanking Fire usw.) nicht implementieren, auch wenn sie im Code oder in Q&As erwähnt werden – höchstens als Hinweis notieren.

## Git

- Nur Dateien lokal ändern; committen und pushen nur auf ausdrückliche Anfrage. Keine PRs.
- Commit-Nachrichten: kurz und prägnant, auf Englisch, beginnend mit einem Partizip (z. B. „fixed smoke reset", „implemented sniper check").
- Keine „Co-Authored-By"-Zeile oder sonstige Claude-Hinweise in Commit-Nachrichten.

## Änderungen an Dateien

- Vor jeder Dateiänderung zuerst eine Vorschau zeigen: betroffene Dateien und die geplanten Änderungen als Diff (wie `git diff`), kurz begründet.
- Danach warten und erst nach ausdrücklicher Zustimmung umsetzen.
- Ausnahme: Hilfsdateien im Scratchpad (Testskripte, Notizen).

## Projektentscheidungen

- Der Client gilt als vertrauenswürdig: keine serverseitige Prüfung, ob `group_ids` dem richtigen Spieler gehören.
- Erledigtes wird aus `TODO.csv` gelöscht; IDs bleiben stabil (nicht neu nummerieren).

## Dateiformate

- `TODO.csv` und `assets/cards/card_table.csv`: UTF-8 mit BOM, CRLF – beim Schreiben beibehalten (Excel).
- `TODO.csv`: Trennzeichen `;`, Spalten `ID;Status;Kategorie;Regel;Aufgabe`, Status leer = offen bzw. `Ignoriert`. Texte mit `;` in Anführungszeichen setzen.
- Wire-Karten haben in `card_table.csv` den Typ `wire` (nicht `terrain`); Terrain-Subtypen ohne Eintrag in `TERRAIN_MOD` werden abgelehnt.

## Spiel starten

- `start.bat` startet 1 Server + 2 Clients. Aus der Claude-Umgebung startete die Datei keine Prozesse – dann direkt starten:
  - Server: `python -u cardserver.py` (wartet auf Port-Eingabe → leere stdin-Datei umleiten = Port 52000)
  - Client (2×): `python cardgame.py "Player A"` bzw. `"Player B"` (Name optional, sonst aus `lobby_settings.json`), im Lobby-Fenster **Enter** drücken (oder „Join“) → verbindet zum Server im zweiten Feld (Default `localhost:52000`). Name/Server/Nation werden in `userdata/lobby_settings.json` gespeichert – beide Test-Clients teilen sich die Datei.
- Server-Fehler landen nur auf stderr (`traceback.print_exc` in `handle_client`) → stderr in Datei umleiten und nach jeder Aktion prüfen.

## GUI-Tests (Fenster fernsteuern)

- Kein pyautogui installiert → Steuerung per `ctypes` (SetForegroundWindow, SetCursorPos, mouse_event, keybd_event), Screenshots per `PIL.ImageGrab`. Prozess DPI-aware setzen.
- Fenster sind standardmäßig größer als der Bildschirm (Buttons unter der Taskleiste) → auf ca. 1280×720 verkleinern.
- Beide Fenster nicht übereinander legen: Ein Klick nach Fensterwechsel kann im falschen Fenster landen (z. B. ungewollte Einheiten-Auswahl).
- Bedienung: Linksklick auf Handkarte = ausspielen auf aktive Gruppe; Klick auf Gruppen-Kachel = aktive Gruppe wechseln; Klick auf Einheit = (de)selektieren (für Rally/Hero); Rechtsklick = Bewegungsmodus wechseln; **Leertaste** = Aktionsphase → Ablagephase → Zugende bzw. Passen auf gegnerisches Feuer.
- Abgelehnte Aktionen geben keine Rückmeldung – nur am unveränderten Zustand erkennbar.

## Headless-Tests (bevorzugt für Regel-Logik)

Schneller und deterministisch: `GameServer` direkt instanziieren, zwei `Client`-Objekte mit Fake-Socket (`sendall` = no-op) und `userdata/unit_allocation.yaml` anlegen, `broadcast` stubben, `setup_logic()` aufrufen, dann Aktionen über `process_action(action, client)` + `process_aftermath()` schicken. Karten gezielt per `location="hand"`, `owner=<name>` zuteilen; `draw_rnc` für feste Würfe überschreiben.

## Spielmechanik, die beim Testen wichtig ist

- Feuerkarten `fire X (ffY)`: Gruppe braucht Feuerkraft ≥ Y auf der relativen Reichweite. Relative Reichweite = Summe beider Range-Chits (höher = näher, max. 5). Bei Start (0+0) kann fast niemand feuern → erst mit Movement-Karten annähern oder Reichweite im Headless-Test direkt setzen.
- Feuer erzeugt eine `pending_action`; der Verteidiger spielt Concealed (Wert negativ, z. B. `-2`) oder passt mit Leertaste.
- Pro Gruppe eine Aktion pro Zug (mehrere Gruppen dürfen handeln). Hero zählt nicht als Aktion.
- Ablegen: Deutsche dürfen auch nach einer Aktion ablegen (max. 1), Amerikaner nur ohne Aktion (max. 2).
- Gelände nur auf Gruppen in Bewegung.
- Positionen: `unit.slot` ist 0-basiert (Regelbuch/RPN 1-basiert → Position n = slot n-1). Wo die Reihenfolge zählt (Feuer, Sniper, künftig RPC/Crew), nach `slot` sortieren; `process_aftermath` schließt Lücken nach Verlusten.

## Bekannte offene Punkte

- Offene Aufgaben stehen in `TODO.csv` (nicht hier doppelt pflegen).
- Regelbuch: `rules/UF RuleBook updated.pdf` (91 Seiten, inkl. Q&A). Das Read-Tool kann es nicht rendern (kein poppler) → Text per `pypdf` extrahieren (ggf. `pip install pypdf`): `pypdf.PdfReader(pfad).pages[i].extract_text()`, Regelnummern (z. B. „16.42“) per Textsuche über alle Seiten finden.