# Order Batching (Kommissionier-Batchbildung)

Siebte Demo im Portfolio, nach Tourenplanung (VRP), 3D-Packungsoptimierung, Liniennetz-Design
(ÖPNV), Tor-Zuordnung (Cross-Dock), LKW-Zeitfenster-Buchung und Wechselbrücken-Hofmanagement.
Zurück im Kernfeld Intralogistik: Kundenbestellungen werden zu Kommissionier-Batches gruppiert,
die ein Kommissionierer in **einer** Tour durchs Lager abarbeitet, begrenzt durch eine Kapazität
(max. Positionen je Batch, z. B. die Fächer eines Kommissionierwagens) - das klassische **Order
Batching Problem** aus der Warehousing-Literatur (z. B. Gademann & van de Velde 2005).

Selbe Methodik wie bei den anderen Demos: Konstruktionsheuristik(en) + Bewertung + Vergleich,
Ergebnis zuerst ("Ihr optimierter Batchplan"), Methodenvergleich sekundär im Expander.

> **Hinweis zu allen Zeit-/Performance-Zahlen in diesem README:** Sämtliche Benchmark- und
> Rechenzeit-Angaben (Inter-Batch-Suche, Don't-Look-Bits, Iterated Local Search, CP-SAT) wurden auf
> einem lokalen Entwicklungsrechner gemessen (AMD Ryzen 7 7800X3D, 8 Kerne/16 Threads, ~4,2 GHz,
> 31 GB RAM) - aktuelle, vergleichsweise starke Desktop-Hardware mit hoher Single-Core-Leistung.
> Auf **Streamlit Community Cloud** (siehe Abschnitt 3 unten, der kostenlose Hosting-Weg für diese
> Demo) läuft die App typischerweise auf deutlich schwächerer, geteilter Hardware (oft nur 1
> geteilte vCPU, ~1 GB RAM). Die tatsächlichen Zeiten dort - insbesondere die Inter-Batch-Suche bei
> großen Instanzen, das `ILS_TIME_BUDGET_S`-Zeitbudget und die CP-SAT-Zeitlimits - dürften spürbar
> länger ausfallen als hier dokumentiert. Die Konstanten (`ILS_TIME_BUDGET_S`,
> `CPSAT_MAX_TIME_LIMIT`, `CPSAT_MAX_MODEL_SIZE` in `batch_constants.py`) sind bislang NICHT für
> schwächere Hosting-Hardware nachgemessen oder angepasst worden.

## Dateistruktur

| Datei | Inhalt |
|---|---|
| `app.py` | Streamlit-Ablauf: Sidebar, Datentabelle, Primäransicht, Tabs, Vergleich, Erklärungen |
| `batch_constants.py` | Farben, Toleranzen, Default-Werte für Lager/Kapazität/Kennzahlen |
| `batch_presets.py` | `SETTING_SPECS`, Ein-Klick-Presets, Permalink-Logik |
| `batch_warehouse.py` | Lagerlayout (Gänge + zwei Quergassen), Distanzberechnung |
| `batch_construction.py` | Greedy-Seed-Batching, Zonen-Sweep-Batching, Einzelbestellungs-Baseline |
| `batch_local_search.py` | NN+2-opt je Batch, Inter-Batch-Suche (Relocate/Swap, Don't-Look-Bits), Iterated Local Search |
| `batch_evaluation.py` | Distanz-/Kapazitätsbewertung, Umrechnung in Kommissionierzeit/Kosten/Durchsatz |
| `batch_visualization.py` | 2D-Lagergrundriss mit Plotly (Übersicht + Batch-Detail) |
| `batch_ui_panel.py` | Wiederverwendbares UI-Panel je Batching-Strategie |
| `batch_pdf_export.py` | PDF-Batchplan-Export |
| `batch_feedback.py` | Feedback-Logging (CSV) |
| `batch_ortools_solver.py` | Exakter/nahe-exakter CP-SAT-Vergleichslöser (Zuteilung + Routing gemeinsam) |
| `tests/test_app.py` | Testsuite (70 Tests) |

## Funktionsumfang

- Synthetisches Lagerlayout: parallele Gänge zwischen vorderer und hinterer Quergasse, Weg immer
  über die kürzere der beiden Quergassen bei Gangwechsel - das Standardmodell der
  Kommissionier-Routing-Literatur (Roodbergen & de Koster).
- Zwei selbst implementierte Batching-Strategien: **Greedy-Seed-Batching** (klassisches
  Seed-Verfahren) und **Zonen-Sweep-Batching** (sortiert nach Gang-Schwerpunkt, analog zum
  Sweep-Algorithmus der Tourenplanung-Demo).
- Zwei umschaltbare Kapazitätsarten: **max. Positionen je Batch** (die in der Batching-Literatur
  übliche Vereinfachung, realistisch bei einheitlichen Artikelgrößen) oder **max. Volumen je
  Batch** (realistischer bei stark heterogenen Sortimenten, z. B. Grocery/General Merchandise,
  wo eine einzelne großvolumige Position den Batch bereits füllen kann, ohne dass die
  Positionsanzahl das anzeigt) - auf Nutzeranfrage ergänzt, siehe Abschnitt unten.
- Je Batch eine unabhängig optimierte Kommissionierroute (Nearest-Neighbor + 2-opt), mit
  Iterations-Slider und Auto-Play je Batch.
- Zusätzlich eine **Inter-Batch-Lokalsuche** (Bestellungen zwischen Batches verschieben/tauschen,
  per Don't-Look-Bits beschleunigt) plus **Iterated Local Search** (gezielte Störung + Neu-
  optimierung innerhalb eines Zeitbudgets), mit eigenem Iterations-Slider - schließt einen
  Großteil des Abstands zum echten Optimum, den 2-opt allein offen lässt (auf Nutzeranfrage
  benchmarkt und ergänzt, siehe Abschnitt unten).
- Geschäftliche Kennzahlen: Kommissionierzeit, Personalkosten, Durchsatz (Positionen/h) statt
  abstrakter Distanzwerte - die reine Pickzeit ist über alle Strategien identisch, nur die
  Laufzeit unterscheidet sich.
- Primäransicht vergleicht die beste eigene Strategie gegen eine Einzelkommissionierungs-Baseline
  (eine Tour je Bestellung, kein Batching) - macht den wirtschaftlichen Nutzen von Batching an
  sich sichtbar, nicht nur den Unterschied zwischen den beiden Strategien.
- Optionaler Vergleich mit Googles **CP-SAT** (Open Source, exakter Constraint-Solver, Teil von
  OR-Tools) auf kleinen Instanzen - löst Zuteilung UND Routing gemeinsam in einem Modell, statt
  nacheinander wie die eigenen Heuristiken. Button-gesteuert mit Zeitlimit, da nur für kleine
  Instanzen praktikabel (auf Nutzeranfrage ergänzt, siehe Abschnitt unten).
- Direkt editierbare Positionstabelle, drei Ein-Klick-Beispielszenarien, Permalink (URL spiegelt
  die aktuelle Konfiguration), PDF-Batchplan-Export, Feedback-Mechanismus.

## Warum zwei Batching-Strategien statt einer

Order Batching zerfällt in zwei gekoppelte Teilentscheidungen (siehe Expander "📐 Mathematische
Formulierung" in der App): welche Bestellungen in denselben Batch kommen, und in welcher
Reihenfolge die Positionen eines Batches abgelaufen werden. Beide Entscheidungen sind für sich
genommen bereits NP-schwer (verwandt mit Bin Packing bzw. Traveling Salesman), eine gemeinsame
exakte Lösung ist bei realistischen Instanzgrößen praktisch nicht mehr berechenbar. Greedy-Seed
und Zonen-Sweep verfolgen zwei unterschiedliche Grundprinzipien für die erste Teilentscheidung
(Ähnlichkeit zum bisherigen Batch-Inhalt vs. geografische Zonierung) - welches besser abschneidet,
hängt vom Szenario ab (siehe Beispielszenario "Weitläufiges Lager"), weshalb beide direkt
vergleichbar angeboten werden statt sich auf eine einzige Strategie festzulegen.

## Benchmark: Zonen-Sweep war schwächer als gedacht - und ist jetzt nachgebessert

Auf Nutzeranfrage ("Zonen-Sweep scheint nicht sonderlich gut zu sein") systematisch mit 200
Zufallsinstanzen über 8 Szenarien gegen Greedy-Seed-Batching gebenchmarkt (reine Batch-Distanz
nach 2-opt, ohne Business-Umrechnung). Bestätigt: die ursprüngliche Fassung lag im Schnitt **3,9%**
hinter Greedy-Seed zurück, bei knapper Batch-Kapazität sogar **9,7%** (Greedy gewann dort 24 von
25 Läufen). Ursache: Zonen-Sweep sortierte einmal global nach Gang-Schwerpunkt und packte strikt
First-Fit in dieser Reihenfolge - sobald die nächste Bestellung in der Sortierung nicht mehr
passte, wurde der Batch sofort geschlossen, auch wenn eine SPÄTERE Bestellung in der Sortierung
noch gepasst hätte. Bei enger Kapazität verschenkte das systematisch Kapazität und erzeugte
unnötig viele zusätzliche Depot-Rundwege.

**Behoben:** Ein neuer Batch startet weiterhin an der nächsten unverteilten Stelle im räumlichen
Sweep (das bleibt der Kern von "Zonen-Sweep"), wird danach aber - wie bei Greedy-Seed - mit der
jeweils NÄCHSTGELEGENEN noch passenden Bestellung aufgefüllt, statt stur in Sortierreihenfolge
abzubrechen. Im selben Benchmark sinkt der Rückstand dadurch auf nur noch **0,8%** im Schnitt; in
mehreren Szenarien (kompaktes Lager, wenige Gänge, große Kapazität, sehr viele Gänge) liegt
Zonen-Sweep jetzt sogar vor Greedy-Seed. Eine zunächst ebenfalls getestete einfachere Variante
(Kapazitätsrest mit der GRÖSSTEN noch passenden Bestellung auffüllen, klassisches Best-Fit aus dem
Bin-Packing, ohne Rücksicht auf räumliche Nähe) reduzierte den Rückstand nur auf 2,0% - die
Kombination aus "räumlich sortiert starten" UND "räumlich nächstgelegen auffüllen" schlägt reines
Best-Fit-nach-Größe deutlich.

## Benchmark: wie viel Potenzial lässt reines 2-opt noch liegen?

Auf Nutzeranfrage ("gibt's noch weitere Verbesserungsstrategien?") erst systematisch benchmarkt,
bevor irgendetwas gebaut wurde. Zwei Teile:

**Teil 1 - Abstand zum echten Optimum.** Auf 12 winzigen, aber nicht trivialen Instanzen (7
Bestellungen, Kapazität 6) den ECHTEN Optimalwert per Vollenumeration bestimmt (alle zulässigen
Partitionen der Bestellungen, je Batch eine exakte Bruteforce-Route statt 2-opt) und mit
Greedy-Seed + 2-opt verglichen: **8,7%** Abstand zum Optimum im Schnitt, in Einzelfällen bis 25%,
nur 3 von 12 Instanzen trafen das Optimum exakt. Grund: 2-opt optimiert nur die Route INNERHALB
eines Batches - die Batch-ZUTEILUNG selbst blieb nach der Konstruktion unangetastet.

**Teil 2 - wie viel eine Inter-Batch-Lokalsuche davon schließt.** Ein Relocate/Swap-Prototyp
(Bestellungen zwischen Batches verschieben/tauschen, wenn das die Gesamtdistanz senkt - first
improvement, analog zu Or-opt in der Tourenplanung-Demo) auf denselben 12 Instanzen: Abstand zum
Optimum sinkt von 8,7% auf **0,12%**, 11 von 12 Instanzen treffen das Optimum exakt. Auf
realistischen Instanzgrößen (18-30 Bestellungen, kein bekanntes Optimum, aber relative
Verbesserung messbar) ergaben sich **7-18% kürzere Gesamtdistanz**, für beide Batching-Strategien
gleichermaßen - ein deutlich größerer Hebel als die Zonen-Sweep-Nachbesserung oben.

**Umgesetzt, mit einer wichtigen Performance-Korrektur:** Der erste Prototyp bewertete jeden
Kandidatenzug per komplettem Neu-Routing (volle NN+2opt-Neuberechnung) der betroffenen Batches -
bei den größten zulässigen Szenarien (80 Bestellungen) brauchte das mehrere Minuten und wurde
abgebrochen. Die produktive Fassung bewertet Kandidaten stattdessen wie find_or_opt_move in der
Tourenplanung-Demo: Cheapest-Insertion in die BESTEHENDE Route des Zielbatches (O(k) statt O(k³)
je Kandidat), erst der letzte Historien-Eintrag wird zusätzlich per vollem 2-opt poliert. Damit
läuft dieselbe Suche bei 80 Bestellungen in 1-11 Sekunden statt mehreren Minuten, bei den
realistischen Standardeinstellungen (~24 Bestellungen) im Bruchteil einer Sekunde.

## Exakter Solver: ein gescheiterter erster Versuch, dann CP-SAT

Auf Nutzeranfrage ("Ein exaktes Verfahren zum Vergleich für kleine Instanzen... vielleicht über
OR-Tools") als Vergleichsmaßstab ergänzt. Der naheliegende erste Ansatz - die OR-Tools-
**Routing-Bibliothek** (dieselbe, die die Tourenplanung-Demo für ihren OR-Tools-Tab nutzt), jede
Position als Routing-Knoten, "alle Positionen einer Bestellung müssen im selben Batch/Fahrzeug
landen" über eine `VehicleVar`-Gleichheitsnebenbedingung erzwungen - scheiterte an zwei
unabhängigen Problemen:

1. **Rohe `VehicleVar`-Gleichheit wird von den Standard-Konstruktionsheuristiken ignoriert.** Der
   Solver meldete praktisch immer `ROUTING_INVALID`, unabhängig von Instanzgröße oder gewählter
   Heuristik.
2. **Workaround über `AddPickupAndDelivery`-Verkettung** (OR-Tools' dokumentierter Mechanismus für
   "gleiches Fahrzeug", eigentlich für Abhol-/Lieferpaare gedacht) funktionierte korrekt - aber nur
   für Bestellungen mit sehr wenigen Positionen (1-2). Schon ab 4-6 Positionen je Bestellung fand
   der Solver **gar keine** zulässige Lösung mehr, auch mit mehr Zeit oder mehr Fahrzeugen nicht -
   die Kettenlänge pro Bestellung war der eigentliche Bruchpunkt, nicht die Gesamtinstanzgröße.
   Schlimmer: **mit der Konstruktionsheuristik `PATH_CHEAPEST_ARC` stürzte der native Solver bei
   etwas größeren Instanzen mit einem echten Segfault ab** (empirisch reproduziert) - das hätte bei
   Live-Einsatz den gesamten Streamlit-Prozess für alle gleichzeitigen Nutzer abgeschossen, nicht
   nur einen Fehler im Browser gezeigt. Ein inakzeptables Risiko für eine öffentlich erreichbare
   Demo.

**Die Lösung: CP-SAT statt der Routing-Bibliothek.** Google CP-SAT (derselbe OR-Tools-Baukasten,
aber der allgemeine Constraint-Solver statt der spezialisierten Routing-Bibliothek) erlaubt eine
saubere gemeinsame Formulierung: Zuordnungsvariablen $y_{o,k}$ (Bestellung $o$ → Batch-Slot $k$)
plus je Batch-Slot ein echter Hamiltonkreis (`model.AddCircuit`) über Depot und ALLE Positionen,
wobei Positionen, deren Bestellung nicht diesem Slot zugeteilt ist, per Selbstschleife
übersprungen werden ("optional node"-Muster). Validiert gegen dieselben 12 Referenzinstanzen mit
bekanntem Optimum (siehe Benchmark oben): **trifft das Optimum in allen 12 Fällen** (kleine
Abweichungen von <0,02 lediglich Rundungsartefakte der Integer-Skalierung, die CP-SAT intern
braucht). Kein einziger Absturz in allen Stresstests, selbst bei 80 Bestellungen/309 Positionen -
im schlimmsten Fall dauert der reine Modellaufbau spürbar lange (statt zu crashen), was
`CPSAT_MAX_MODEL_SIZE` als harte Obergrenze verhindert (button deaktiviert sich mit einer
Erklärung statt die App einzufrieren).

**Ehrlicher Nebenbefund:** Bei realistischen Instanzgrößen (24 Bestellungen, 20s Zeitlimit) fand
CP-SAT nur eine Lösung, die ca. **1,7% schlechter** war als die eigene Heuristik (Greedy-Seed +
Inter-Batch-Suche + 2-opt) - und das, obwohl CP-SAT exakt sucht. Exakte Verfahren sind bei NP-
schweren Problemen jenseits einer gewissen Größe nicht automatisch besser als gute Heuristiken,
wenn ihnen die Zeit zum Beweisen der Optimalität fehlt - für solche Fälle zeigt die App explizit
"Beste gefundene Lösung" statt "Nachweislich optimal" an, statt Optimalität zu suggerieren, die
nicht bewiesen wurde.

## Benchmark: Clustering als Konstruktionsheuristik - dreimal geprüft, dreimal kein Mehrwert

Auf Nutzeranfrage ("Clustering-basierte Verfahren wären doch einen Blick wert") systematisch
geprüft, ob eine ML-Clustering-Methode als Ersatz für die Startreihenfolge von Greedy-Seed/
Zonen-Sweep die Batch-Zuteilung verbessert. Alle drei Tests isolieren dieselbe eine Variable: die
Reihenfolge, mit der die bestehende Best-Fit-nach-Nähe-Füllschleife durchlaufen wird - danach
läuft in jedem Fall dieselbe Inter-Batch-Suche + 2-opt-Politur wie bei den beiden bestehenden
Strategien, damit der Vergleich fair bleibt (Konstruktionsqualität ALLEIN würde die eigentliche
Frage verfehlen, siehe unten).

**Drei strukturell unterschiedliche Methoden getestet** (je 15 Instanzen über 4 Szenarien,
Distanz nach vollständiger Pipeline):

1. **Hierarchisches Clustering** (scipy, average/complete/single Linkage auf den
   Bestell-Schwerpunkten) - alle drei Varianten innerhalb ±1-3% von Greedy-Seed, kein
   konsistenter Gewinner.
2. **HDBSCAN** (dichtebasiert, `min_cluster_size` 2 und 3) - dasselbe Bild, plus ein
   Nebenbefund: im Schnitt **15-20% der Bestellungen** wurden als "Rauschen" eingestuft (keinem
   Cluster zugehörig) und liefen ohnehin nur als Einzel-Saat in dieselbe Füllschleife wie bei den
   anderen Methoden - die dichtebasierte Clusterstruktur wurde für einen relevanten Teil der
   Bestellungen gar nicht genutzt.
3. **Balanciertes Graph-Partitioning** (rekursive Kernighan-Lin-Bisektion, networkx, mit
   Blattgröße 2 und 4) - strukturell die am besten passende der drei Methoden, da die
   Kapazitätsbalance direkt in der Zielfunktion steckt (gleich große Teile, minimaler Schnitt)
   statt nachträglich per Bin-Packing aufgezwungen zu werden. Trotzdem: wieder innerhalb von ±1%,
   Greedy-Seed gewann weiterhin 2 von 4 Szenarien.

**Warum das plausibel ist, nicht nur Zufall:** Order Batching hat keine *natürliche* Cluster-
struktur im geometrischen Sinn - die Bestellpositionen sind (so werden sie erzeugt, und in vielen
realen Lagern ist das nicht anders) im Wesentlichen gleichverteilt über das Lager, ohne echte
Dichtelücken zwischen "Gruppen". Dichtebasierte Verfahren wie HDBSCAN setzen aber genau solche
Lücken voraus, um Cluster zu *entdecken*. Order Batching ist kein Cluster-Entdeckungsproblem,
sondern ein Constraint-*Konstruktions*problem: jede zulässige Kapazitäts-Partition muss aktiv
gebaut werden, es gibt keine im Datensatz bereits vorhandene "wahre" Gruppierung, die nur
gefunden werden müsste. Das erklärt auch, warum selbst das strukturell passendere balancierte
Graph-Partitioning keinen Vorteil brachte: der eigentliche Hebel liegt gar nicht mehr in der
Konstruktion, seit die Inter-Batch-Suche (siehe Benchmark oben) jede vernünftige Startzuteilung
auf ein sehr ähnliches Niveau anhebt, bevor die Wahl der Konstruktionsheuristik überhaupt noch
zum Tragen kommt. Drei unabhängige, strukturell unterschiedliche Methoden mit demselben Ergebnis
sind ein starkes Indiz, nicht nur eine einzelne Negativ-Stichprobe - keine dieser drei Methoden
wurde in die App übernommen.

## Benchmark: Don't-Look-Bits + Iterated Local Search - der erste konsistente Zusatzgewinn

Auf Nutzeranfrage ("siehst du bei der lokalen Suche noch Potenzial, Qualität und Performance?")
zwei unabhängige, gut etablierte Techniken geprüft - im Gegensatz zu den drei Clustering-Versuchen
oben brachten hier BEIDE etwas.

**Performance: Don't-Look-Bits** (Bentley 1992, Standardtechnik in TSP/VRP-Lokalsuche). Die
Inter-Batch-Suche durchsuchte bislang bei JEDER Iteration wieder alle Batches von vorn, auch die,
die seit dem letzten Zug gar nicht betroffen waren. Stattdessen jetzt eine Warteschlange
"auffälliger" Batches: ein Batch verlässt sie, sobald von ihm aus kein verbessernder Zug mehr
gefunden wird, und kommt erst zurück, wenn ein späterer Zug ihn tatsächlich verändert hat.
Ergebnis: **1,2-3,2x schneller**, der größte Gewinn genau bei der größten getesteten Instanz (80
Bestellungen: 1,32s → 0,41s). Qualität schwankt dabei nur geringfügig und nicht systematisch
(zwischen −2,0% und +1,8% je nach Szenario) - plausibel, da eine andere Zug-Reihenfolge zu einem
anderen, aber vergleichbar guten lokalen Optimum führt, nicht zu einem grundsätzlich schlechteren.

**Qualität: Iterated Local Search** (Lourenço, Martin & Stützle 2003). Reine Lokalsuche stoppt
beim ERSTEN lokalen Optimum und kann es nicht wieder verlassen. Nach Erreichen eines lokalen
Optimums jetzt gezielt stören (ein paar zufällige, zulässige Relocates, auch wenn das kurzfristig
verschlechtert) und erneut optimieren, wiederholt für ein Zeitbudget statt eine feste Anzahl
Durchläufe, bestes Ergebnis behalten. Ergebnis über 4 Szenarien, kombiniert mit Don't-Look-Bits als
schnellerem Suchmotor (mehr Neustarts passen dadurch ins selbe Budget): **durchweg 0,9-4,8% kürzere
Distanz**, ohne eine einzige Verschlechterung - der erste Hebel seit der ursprünglichen
Inter-Batch-Suche selbst, der einen konsistenten zusätzlichen Gewinn brachte (im Unterschied zu
Or-opt innerhalb der Route und allen drei Clustering-Varianten oben, die alle im Rauschen
verschwanden).

**Zeitbudget statt fester Neustart-Zahl:** Ein erster Versuch mit einer festen Anzahl Neustarts
(30) zeigte am absoluten Größen-Maximum (80 Bestellungen, beide Strategien) ein Risiko: 8,3s je
Strategie, ~17s kombiniert - spürbar mehr als vorher. Umgestellt auf ein Zeitbudget
(`ILS_TIME_BUDGET_S`, geprüft NACH jedem Neustart, nicht währenddessen): bei kleinen Instanzen
passen dadurch viele Dutzend Neustarts hinein (dort ist ein einzelner Durchlauf günstig), bei
großen automatisch nur wenige oder gar keiner. Am selben Größen-Maximum sank die kombinierte Zeit
dadurch auf ~4s statt ~17s - nur bei der ohnehin schon dokumentierten Extremkombination aller
Regler gleichzeitig (siehe "Bewusst nicht enthalten" unten) dominiert weiterhin allein die
unvermeidbare erste Konvergenz, die das Zeitbudget selbst nicht abkürzen kann.

## Benchmark: Numpy-Indexierung als letzte, mechanische Optimierung

Auf Nutzeranfrage ("fallen dir noch weitere Performance-Optimierungen ein?") drei Ideen geprüft,
zwei davon verworfen, eine umgesetzt:

- **Batch-Größen-Cache** (Kapazitätsauslastung je Batch inkrementell statt bei jedem Suchschritt
  neu zu summieren): nur **1,08x** am Stresstest-Szenario - bei den hier üblichen Batch-Größen ist
  die Summe schon so klein, dass sich der zusätzliche Code (eine weitere, synchron zu haltende
  Cache-Liste) nicht lohnt. Nicht übernommen.
- **Doppelte `route_batch`-Berechnung** (siehe vorheriger Abschnitt, bereits als vernachlässigbar
  identifiziert): bestätigt bei 0,8% der Gesamtzeit, nicht übernommen.
- **`D[a][b]` → `D[a, b]`** (echtes 2D-Indexing eines numpy-Arrays statt erst eine Zeilen-Ansicht
  zu erzeugen und darin zu indizieren): **umgesetzt.** Mechanische Änderung ohne jede
  Verhaltensänderung (identisches Ergebnis vor/nach dem Fix, per Test bestätigt), betrifft aber die
  heißeste innere Schleife der gesamten App (`route_distance`, `_cheapest_insertion`,
  `nearest_neighbor_route` - aufgerufen bei praktisch jeder Kandidatenbewertung in DLB, ILS und
  2-opt). End-zu-Ende am Stresstest-Szenario: **2,15s → 1,86s (1,15x)**, im reinen
  Distanz-Mikrobenchmark 1,33x.

## Zwei Kapazitätsarten statt einer fixen

Ursprünglich war Kapazität ausschließlich als Positionsanzahl modelliert (jede Position zählt 1).
Auf Nachfrage, ob das realistisch genug ist: **kommt darauf an**. Bei einheitlichen Artikelgrößen
ist "Positionen" die in der Batching-Literatur übliche, einfache Vereinfachung und entspricht oft
auch der Praxis bei Mehr-Tablett-Wagen mit fester Slot-Zahl. Bei stark heterogenen Sortimenten
(Grocery, General Merchandise) ist dagegen das Volumen der tatsächliche Flaschenhals - eine
einzelne großvolumige Position kann einen Batch bereits füllen, ohne dass die reine
Positionsanzahl das zeigt (siehe Beispielszenario "🛒 Heterogene Artikelgrößen"). Statt die
Positionslogik zu ersetzen, wurde sie um einen umschaltbaren zweiten Modus ergänzt: `item_sizes`
(ein Array, ein Wert je Position - im Positionen-Modus lauter Einsen, im Volumen-Modus das
tatsächliche Volumen) macht beide Batching-Strategien und die Kapazitätsprüfung modusagnostisch,
ohne den Code zu verzweigen. Bewusst NICHT als volles 3D-Packungsproblem umgesetzt (Rotation,
Formpassung) - das deckt bereits die separate `pack_demo` ab; hier zählt nur ein skalares Volumen
je Position, das gegen eine Gesamtkapazität aufsummiert wird.

## Bewusst nicht enthalten (Scope-Entscheidungen)

- **Keine gemeinsame lokale Suche über Inter-Batch- UND Route-Nachbarschaften hinweg.** Relocate/
  Swap und 2-opt laufen nacheinander (erst Zuteilung, dann je Batch die Route poliert), nicht als
  eine gemeinsame, verschachtelte Suche wie Or-opt+2-opt in der Tourenplanung-Demo. Für die
  gefundenen Verbesserungen (siehe Benchmark oben) hat das gereicht - eine engere Verzahnung wäre
  der nächste Schritt, wenn noch mehr Potenzial gehoben werden soll.
- **Kein Move, der die Kapazität selbst neu verhandelt** (z. B. drei Bestellungen zwischen drei
  Batches gleichzeitig umschichten) - nur paarweise Relocate/Swap zwischen je zwei Batches.
- **Sehr seltener Randfall bei absoluten Maximalwerten aller Regler gleichzeitig** (80
  Bestellungen, 24 Gänge, 15 Positionen/Bestellung, Kapazität 60): schon die erste Konvergenz der
  Inter-Batch-Suche kann dort mehrere Sekunden pro Strategie brauchen (Don't-Look-Bits senkt das
  spürbar, kann diese Instanzgröße aber nicht beliebig günstig machen) und während dieser Zeit
  kurzzeitig einen "Verbindung getrennt"-Hinweis im Browser auslösen (Streamlit blockiert
  währenddessen den Event-Loop) - die App erholt sich danach vollständig, das Ergebnis ist korrekt.
  Das Iterated-Local-Search-Zeitbudget wird nur ZWISCHEN Neustarts geprüft und kann diese
  unvermeidbare erste Konvergenz nicht abkürzen, verschärft das Risiko dort aber auch nicht
  zusätzlich (siehe Benchmark oben). Bei realistischen Einstellungen (Standardwerte, alle drei
  Presets) tritt das nicht auf.
- **Keine Mehrfach-Kommissionierer-Koordination.** Jeder Batch wird unabhängig bewertet, als gäbe
  es keine Wegekonflikte zwischen gleichzeitig im Lager arbeitenden Kommissionierern.
- **Immer nur EINE Kapazitätsart gleichzeitig aktiv, keine Kombination.** Realistischer wäre oft
  eine Kombination (z. B. Kommissionierwagen mit begrenzten Fächern UND einer Volumengrenze
  gleichzeitig) - bewusst auf eine einzige, umschaltbare Nebenbedingung reduziert, analog zur
  Kapazitätsrestriktion der Tourenplanung-Demo.
- **CP-SAT-Vergleich nur für kleine Instanzen praktikabel.** `CPSAT_MAX_MODEL_SIZE` deaktiviert den
  Solve-Button bei zu vielen Bestellungen/Positionen - eine bewusste Grenze, keine Notlösung: schon
  der reine Modellaufbau (nicht die Zeitlimit-gesteuerte Suche selbst) würde jenseits davon mehrere
  Sekunden bis Minuten dauern. Für größere Instanzen bleiben die eigenen Heuristiken die einzig
  praktikable Option - was in der Praxis auch für reale Lagergrößen gilt.

## 1. Lokal ausführen

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 2. Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest
```

## 3. Kostenlos online stellen (Streamlit Community Cloud)

Repository auf GitHub pushen, auf [share.streamlit.io](https://share.streamlit.io) verbinden,
`app.py` als Einstiegspunkt wählen. `requirements.txt` wird automatisch erkannt.

## 4. Einbindung auf der Ionos-Website

Als iFrame einbetten (`<iframe src="https://<app-name>.streamlit.app" ...>`) oder als Link im
Portfolio-Bereich verlinken - identisches Vorgehen wie bei den anderen Demos.

## 5. Anpassungsideen für später

- Relocate/Swap und 2-opt zu einer gemeinsamen, verschachtelten lokalen Suche verzahnen statt sie
  nacheinander laufen zu lassen (siehe "Bewusst nicht enthalten" oben).
- Mehrfach-Umschichtungen (3+ Bestellungen zwischen mehreren Batches gleichzeitig) als weitere
  Nachbarschaft der Inter-Batch-Suche.
- Kombinierte Kapazität (Positionen UND Volumen gleichzeitig als harte Grenzen, statt nur einer
  umschaltbaren Kapazitätsart) sowie eine dritte Kapazitätsart nach Gewicht.
- Mehrere Kommissionierer gleichzeitig mit Wegekonflikten (verwandt mit dem Multi-Vehicle-Fall
  der Tourenplanung-Demo, nur mit fester statt freier Tourzuteilung).
- Kommissionierwellen mit Zeitfenstern (Bestellung muss bis Uhrzeit X versandfertig sein).
- Eine vollständige Metaheuristik (Simulated Annealing, Tabu Search) statt Iterated Local Search -
  würde vermutlich noch etwas mehr Qualität herausholen, aber mit spürbar mehr Komplexität
  (Abkühlplan bzw. Tabu-Liste pflegen) für einen nach den bisherigen Benchmark-Zahlen wahrscheinlich
  kleinen Zusatzgewinn.
- CP-SAT mit einem "warm start" aus der eigenen Heuristik füttern (`AddHint`) - könnte die Suche
  bei mittelgroßen Instanzen beschleunigen, ohne die Modellgröße selbst zu verändern.
