# Order Batching (Kommissionier-Batchbildung)

**[→ Demo live ausprobieren](https://sebastianhanisch-orderbatch-demo.streamlit.app/)**

Siebte Demo im Portfolio, nach Tourenplanung (VRP), 3D-Packungsoptimierung, Seefracht-
Konsolidierung (LCL), Liniennetz-Design (ÖPNV), Tor-Zuordnung (Cross-Dock) und LKW-Zeitfenster-
Buchung. Zurück im Kernfeld Intralogistik: Kundenbestellungen werden zu Kommissionier-Batches
gruppiert, die ein Kommissionierer in **einer** Tour durchs Lager abarbeitet, begrenzt durch eine
Kapazität (max. Positionen je Batch, z. B. die Fächer eines Kommissionierwagens) - das klassische
**Order Batching Problem** aus der Warehousing-Literatur (grundlegend bereits Elsayed 1981; das
hier verwendete parallele-Gang-Modell folgt Gademann & van de Velde 2005).

Selbe Methodik wie bei den anderen Demos: Konstruktionsheuristik(en) + Bewertung + Vergleich,
Ergebnis zuerst ("Ihr optimierter Batchplan"), Methodenvergleich sekundär im Expander.

> **Hinweis zu allen Zeit-/Performance-Zahlen in diesem README:** Sämtliche Benchmark- und
> Rechenzeit-Angaben (Inter-Batch-Suche, Don't-Look-Bits, Iterated Local Search) wurden auf
> einem lokalen Entwicklungsrechner gemessen (AMD Ryzen 7 7800X3D, 8 Kerne/16 Threads, ~4,2 GHz,
> 31 GB RAM) - aktuelle, vergleichsweise starke Desktop-Hardware mit hoher Single-Core-Leistung.
> Auf **Streamlit Community Cloud** (siehe Abschnitt 3 unten, der kostenlose Hosting-Weg für diese
> Demo) läuft die App typischerweise auf deutlich schwächerer, geteilter Hardware (oft nur 1
> geteilte vCPU, ~1 GB RAM). Die tatsächlichen Zeiten dort - insbesondere die Inter-Batch-Suche bei
> großen Instanzen und das `ILS_TIME_BUDGET_S`-Zeitbudget - dürften spürbar länger ausfallen als
> hier dokumentiert. Die Konstante `ILS_TIME_BUDGET_S` (`batch_constants.py`) ist bislang NICHT für
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
| `tests/test_app.py` | Testsuite (82 Tests) |

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

**Nachtrag:** Diese frühe Zahl (Prototyp-Benchmark, bevor Don't-Look-Bits/ILS existierten) wurde
später durch den konsolidierten Stufen-Benchmark weiter unten ("Benchmark: konsolidierte
Kennzahlen für Inter-Batch-Suche, verschachtelte Suche und ILS") ersetzt - derselbe Vergleich
(Inter-Batch-Suche ggü. bereits 2-opt-polierter Konstruktion) ergab dort auf einem breiteren
Instanz-Set 5-20%. Für die aktuell in App-Texten und Code-Kommentaren zitierten Zahlen ist dieser
spätere Benchmark maßgeblich.

**Umgesetzt, mit einer wichtigen Performance-Korrektur:** Der erste Prototyp bewertete jeden
Kandidatenzug per komplettem Neu-Routing (volle NN+2opt-Neuberechnung) der betroffenen Batches -
bei den größten zulässigen Szenarien (80 Bestellungen) brauchte das mehrere Minuten und wurde
abgebrochen. Die produktive Fassung bewertet Kandidaten stattdessen wie find_or_opt_move in der
Tourenplanung-Demo: Cheapest-Insertion in die BESTEHENDE Route des Zielbatches (O(k) statt O(k³)
je Kandidat), erst der letzte Historien-Eintrag wird zusätzlich per vollem 2-opt poliert. Damit
läuft dieselbe Suche bei 80 Bestellungen in 1-11 Sekunden statt mehreren Minuten, bei den
realistischen Standardeinstellungen (~24 Bestellungen) im Bruchteil einer Sekunde.

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

## Benchmark: Warm-Start für Iterated-Local-Search-Neustarts

Weitere Nachfrage ("wäre die andere Maßnahme sinnvoll, wenn wir noch Metaheuristiken ausbauen?
Was für andere Performanceverbesserungen wären noch sinnvoll?") führte auf eine deutlich
wirksamere Idee als die zuvor verworfenen Kandidaten: Jeder ILS-Neustart perturbiert nur 2-4 von
oft Dutzenden Batches (`perturb_batches`), baute bisher aber trotzdem für ALLE Batches die
Nearest-Neighbor-Route neu auf und startete die Don't-Look-Bits-Warteschlange mit allen Batches -
obwohl die meisten davon unverändert und bereits lokal optimal sind.

Umgesetzt: `perturb_batches` gibt jetzt zusätzlich zurück, welche Batch-Indizes tatsächlich
verändert wurden. `iterated_local_search_history` übernimmt für alle unberührten Batches Route und
Distanz unverändert aus der aktuell besten Lösung und baut nur für die berührten Batches eine neue
Route auf; die DLB-Warteschlange startet direkt mit genau diesen berührten Batches
(`_inter_batch_search_dlb_from_state`, der gemeinsame Kern für Kalt- und Warmstart).

| Instanz | Neustarts | Kaltstart | Warmstart | Speedup | Distanz kalt → warm |
|---|---|---|---|---|---|
| 24 Bestellungen | 40 | 0,72s | 0,46s | **1,6x** | 1082 → 1043 |
| 30 Bestellungen | 40 | 1,39s | 0,67s | **2,1x** | 1388 → 1373 |
| 80 Bestellungen | 10 | 1,59s | 0,95s | **1,7x** | 3518 → 3370 |

Bemerkenswert: der Warmstart ist nicht nur schneller, sondern findet auch durchweg **bessere**
Lösungen - kein Kompromiss. Grund: die kaltgestartete Suche beginnt ihre Warteschlange immer bei
Batch 0 und verbraucht ihr First-Improvement-Zugbudget oft an längst optimierten Batches, bevor sie
überhaupt bei der eigentlichen Störungsstelle ankommt. Der Warmstart setzt die Warteschlange direkt
an die Störungsstelle, sodass sich verbessernde Zugketten von dort aus ungebremst ausbreiten
können - ein reiner Nebeneffekt der Warteschlangen-Reihenfolge bei First-Improvement-Suche, nicht
der eigentliche Zweck der Änderung, aber ein willkommener.

Auf Nutzeranfrage anschließend zwei weitere Kandidaten geprüft:

- **Bestellgrößen-Memoisierung** (`sum(item_sizes[k] for k in orders[oid])` einmalig cachen, da
  sich die Zusammensetzung einer Bestellung während der Suche nie ändert, nur ihre
  Batch-Zugehörigkeit): nur **1,03-1,06x** über mehrere Instanzgrößen (24/30/80 Bestellungen) -
  die Bestellungen sind klein genug (2-6 Positionen), dass die Summe selbst bei tausendfachem
  Neuberechnen kaum ins Gewicht fällt. Nicht übernommen.
- **Numpy-vektorisierte `_cheapest_insertion`** (die Suche nach der günstigsten Einfügeposition
  über alle Kandidatenpositionen vektorisiert statt in einer Python-Schleife über die Route): bei
  der Standardkapazität (15) ein Wash (0,98x, im Rauschen), wächst aber mit der Batch-Kapazität -
  **1,14x bei Kapazität 30, 1,38x bei Kapazität 60** (End-zu-Ende am 80-Bestellungen-Stresstest,
  inkl. Iterated Local Search) - genau der bereits oben als Risikozone dokumentierte
  Maximalwerte-Randfall. Kein Nachteil beim Normalfall, spürbarer Gewinn im Worst Case. **Umgesetzt.**

## Benchmark: 2-opt-Distanz-Delta statt kompletter Neuberechnung je Kandidat

Weitere Nachfrage ("hast du noch weitere Performance-Verbesserungsideen?") fand den größten
algorithmischen Einzelgewinn dieser ganzen Optimierungsreihe: `find_two_opt_move` baute für JEDES
Kandidatenpaar `(i, j)` die komplette Kandidatenroute und rief `route_distance()` (O(n)) darauf neu
auf - macht eine einzelne 2-opt-Suchrunde O(n³) statt der üblichen O(n²), obwohl beim Umdrehen eines
zusammenhängenden Teilstücks nur die zwei Rand-Kanten sich ändern; alle Kanten innerhalb des
Teilstücks bleiben unverändert (die Distanzmatrix ist symmetrisch). Klassischer 2-opt-Delta-Trick:
Kandidatenbewertung O(1) statt O(n).

Isoliert (reine `two_opt_history`-Läufe über zufällige Routen, 300 Versuche zur
Ergebnisgleichheit): **7,4x bei Kapazität 15, 12,8x bei Kapazität 30, 23,5x bei Kapazität 60** -
identische Endergebnisse in allen 300 Versuchen. End-zu-Ende (kompletter App-Durchlauf inkl. warm-
gestartetem ILS) fällt der Gewinn deutlich bescheidener aus, weil die volle 2-opt-Politur nur EINMAL
je Batch NACH Konvergenz der Inter-Batch-Suche läuft - der Großteil der Gesamtzeit steckt in dieser
Suche selbst (Cheapest-Insertion-Bewertungen), nicht in der abschließenden Politur:

| Szenario | Speedup End-zu-Ende |
|---|---|
| 24 Bestellungen, Kapazität 15 | 1,02x |
| 80 Bestellungen, Kapazität 60 | 1,21x |

Trotzdem umgesetzt: mechanisch, ohne jede Verhaltensänderung (identische Ergebnisse vor/nach dem
Fix), kein Nachteil irgendwo - dieselbe Kategorie wie die Numpy-Indexierung weiter oben.

## Benchmark: vierzehn Metaheuristik-Varianten geprüft - eine davon übernommen

Nach den Performance-Runden auf Nutzeranfrage die Qualitätsseite noch einmal geprüft: taugt eine
andere ILS-Akzeptanzregel oder eine andere Störung als das aktuelle "Better"-Kriterium (jeder
Neustart stört von der bisher besten Lösung, ein Kandidat wird nur bei echter Verbesserung neue
Basis - Lourenço/Martin/Stützle 2003) plus reine Relocate-Störung? Vier etablierte Varianten isoliert
getestet (je eine Variable geändert, über 5 Zufalls-Seeds gemittelt, gleiches Zeitbudget wie
produktiv):

- **Random-Walk-Akzeptanz**: jeder Neustart stört vom zuletzt akzeptierten Kandidaten statt von der
  besten Lösung, akzeptiert IMMER den neuen lokalen Optimum-Kandidaten als nächste Basis (mehr
  Diversifikation, bestes Ergebnis separat mitgeführt).
- **Adaptive Störstärke**: Störstärke steigt nach jedem nicht-verbessernden Neustart, fällt nach
  einer Verbesserung zurück auf den Basiswert.
- **Simulated-Annealing-artige Akzeptanz**: milder als Random Walk - schlechtere Kandidaten werden
  nur mit sinkender Wahrscheinlichkeit `exp(-delta/T)` akzeptiert, T sinkt über die Neustarts linear
  gegen 0.
- **Gemischte Störung (Relocate + Swap)**: statt ausschließlich einzelne Bestellungen zu verschieben,
  je Störzug 50/50 Relocate oder Swap zweier Bestellungen zwischen zwei Batches.

| Szenario | Baseline | Random Walk | Adaptive Stärke | Simulated Annealing | Gemischte Störung |
|---|---|---|---|---|---|
| 24 Bestellungen | 1891 | 1896 (−0,25%) | 1886 (+0,29%) | 1886 (+0,27%) | 1878 (+0,69%) |
| 30 Bestellungen | 2435 | 2499 (−2,61%) | 2499 (−2,61%) | 2499 (−2,61%) | 2424 (+0,45%) |
| 80 Bestellungen, Kapazität 60 | 2867 | 2969 (−3,56%) | 3000 (−4,62%) | 2973 (−3,68%) | 3029 (−5,65%) |

Kein Kandidat gewinnt konsistent über alle Instanzgrößen - und ausgerechnet beim größten,
praktisch wichtigsten Szenario schneiden alle vier schlechter ab als die aktuelle Konfiguration.
Plausible Erklärung: Warm-Start + Don't-Look-Bits führen die Suche bereits sehr gezielt zur
Störungsstelle zurück - Abdriften in schlechtere Regionen (Random Walk, SA) oder aggressiveres
Stören bei Stagnation (Adaptive Stärke) verbraucht das Zeitbudget eher an neuen, unterlegenen
Basislösungen statt die eine gute Basis feiner nachzuschärfen. Die gemischte Relocate+Swap-Störung
zeigt bei kleinen/mittleren Instanzen einen kleinen echten Gewinn, kehrt sich aber bei der großen
Stresstest-Instanz ins deutliche Gegenteil um (vermutlich weil Swap-Züge bei großer Kapazität
teurere, disruptivere Störungen erzeugen, die im Zeitbudget nicht mehr sauber rekonvergieren) - eine
instanzgrößenabhängige Umschaltung wäre technisch möglich, aber genau die Art zusätzlicher
Komplexität für unsicheren Nutzen, die in dieser Session bei den Performance-Kandidaten mehrfach
bewusst verworfen wurde. Keine der vier Varianten übernommen.

Auf Nachfrage, ob auch ein GRUNDSÄTZLICH anderes Metaheuristik-Paradigma (Tabu Search, Genetic
Algorithm, Beam Search, ...) besser abschneiden könnte, wurde **Tabu Search** als vielversprechendster
Kandidat geprüft (bester Fit zur bestehenden Zug-Infrastruktur - Genetic Algorithm hätte für ein
Kapazitäts-Partitionierungsproblem aufwendige, machbarkeitserhaltende Crossover-Operatoren gebraucht,
Beam Search als reine Konstruktionsheuristik trifft vermutlich dieselbe Wand wie die drei
Clustering-Versuche oben). Statt wie DLB den ERSTEN verbessernden Zug zu nehmen, wertet Tabu Search
in jeder Iteration die KOMPLETTE Relocate+Swap-Nachbarschaft aus und wählt den besten Zug - auch
verschlechternd, wenn kein besserer verfügbar ist -, sperrt aber kürzlich rückgängig gemachte Züge für
eine Tabu-Dauer (Zyklenvermeidung), mit einer Aspirationsregel für neue globale Bestlösungen. Nutzt
dieselbe Cheapest-Insertion/Distanz-Delta-Maschinerie wie die bestehende Suche.

| Szenario | Baseline | Random Walk | Adaptive Stärke | Simulated Annealing | Gemischte Störung | Tabu Search |
|---|---|---|---|---|---|---|
| 24 Bestellungen | 1891 | 1896 (−0,25%) | 1886 (+0,29%) | 1886 (+0,27%) | 1878 (+0,69%) | 1968 (−4,04%) |
| 30 Bestellungen | 2435 | 2499 (−2,61%) | 2499 (−2,61%) | 2499 (−2,61%) | 2424 (+0,45%) | 2475 (−1,64%) |
| 80 Bestellungen, Kapazität 60 | 2867 | 2969 (−3,56%) | 3000 (−4,62%) | 2973 (−3,68%) | 3029 (−5,65%) | 3058 (−6,66%) |

Ebenfalls durchweg schlechter - und deutlicher als alle vier vorherigen Kandidaten. Um auszuschließen,
dass das nur am (gegenüber ILS knapperen) Zeitbudget lag, wurde beim größten Szenario das Zeitbudget
verzehnfacht (15s statt 1,5s): Tabu Search kam von 15 auf 148 Iterationen, der Rückstand wurde aber
GRÖSSER statt kleiner (**−10,14%** statt −6,66%) - kein Zeitproblem, sondern ein struktureller
Mismatch. Grund: die vollständige Nachbarschaftsauswertung pro Iteration ist O(Batches² ×
Bestellungen²) - von Natur aus teuer. Die bestehende DLB-Suche nimmt dagegen den ersten
verbessernden Zug und bleibt dank Warm-Start auf die tatsächlich betroffenen Batches fokussiert -
dadurch passen um Größenordnungen mehr Iterationen ins gleiche Budget, was die fehlende
"bester Zug"-Cleverness von Tabu Search mehr als ausgleicht. Nicht übernommen.

Als zweiter, ebenfalls vielversprechend eingeschätzter Kandidat wurde **Adaptive Large Neighborhood
Search** (ALNS, Ropke/Pisinger 2006) geprüft - der VRP-Standardansatz für genau dieses Muster
(Destroy-and-Repair statt zufälliger Einzelzüge). Ersetzt die bisherige leichte Störung (2 zufällige
Relocates) durch: gezielt mehrere Bestellungen entfernen (Random- oder Worst-Removal, also die
Bestellungen mit dem größten aktuellen Distanz-Beitrag) und per Greedy- oder Regret-2-Insertion
wieder einfügen (Regret-2: die Bestellung zuerst platzieren, bei der die zweitbeste Einfügeposition
am stärksten von der besten abweicht - vermeidet, sich in eine Ecke zu manövrieren). Vier Operatoren
(2 Destroy × 2 Repair), adaptiv per Roulette-Wheel nach bisherigem Erfolg gewichtet - die
Akzeptanzregel blieb bewusst unverändert "Better" (hat sich als robusteste Wahl erwiesen), nur die
Störung selbst wurde durch die strukturiertere ALNS-Variante ersetzt.

| Szenario | Baseline | ALNS |
|---|---|---|
| 24 Bestellungen | 1891 | 1883 (+0,44%) |
| 30 Bestellungen | 2435 | 2454 (−0,81%) |
| 80 Bestellungen, Kapazität 60 | 2867 | 3014 (−5,1% bis −5,4%, je nach Entfernungsgröße) |

Anders als bei Tabu Search lag es beim großen Szenario NICHT am Zeitbudget - ALNS bekam dort sogar
*mehr* Restarts als die Baseline (8 vs. 5) - und auch nicht an einer zu aggressiven Entfernungsgröße:
ein Sweep über die Anzahl entfernter Bestellungen (2, 4, 6, 10) ergab durchweg denselben ~5%
Rückstand, selbst bei einer zur Baseline vergleichbar kleinen Entfernungsgröße (k=2). Bei nur 5-8
Restarts insgesamt dominiert bei dieser Instanzgröße vermutlich eher, welche wenigen Störungen
konkret ausprobiert werden, als die Cleverness des Mechanismus dahinter. Nicht übernommen.

Auf Nachfrage, ob sich diese Ansätze statt als VOLLERSATZ der Perturbation/Akzeptanz auch DOSIERT an
anderer Stelle einbauen oder mit der bestehenden Suche kombinieren lassen, drei gezielt abgeschwächte
Varianten geprüft:

- **Worst-Order-Auswahl**: `perturb_batches` wählt aktuell rein zufällig, welche Bestellung
  verschoben wird. Diese Variante wählt stattdessen die Bestellung mit dem größten aktuellen
  Distanz-Beitrag (ALNS-Idee "Worst Removal"), ohne die Störgröße selbst zu ändern (weiterhin nur
  2 Bestellungen).
- **Gelegentlicher ALNS-Kick**: die meisten Neustarts bleiben die billige 2-Relocate-Störung, aber
  nach 5 erfolglosen Neustarts in Folge einmal eine stärkere ALNS-Destroy-Repair-Störung einstreuen,
  danach Stagnationszähler zurücksetzen - hedged zwischen vielen billigen Versuchen und gelegentlicher
  tieferer Diversifikation.
- **Tabu-verstärktes DLB**: läuft die Don't-Look-Bits-Warteschlange leer (kein verbessernder Zug
  mehr), statt sofort zu stoppen bis zu 2 zusätzliche "beste verfügbare" Züge zulassen (auch
  verschlechternd) mit kurzer Tabu-Sperre auf den Rückzug, dann DLB von den berührten Batches aus
  fortsetzen - Tabu Searchs Zyklenvermeidungs-Idee, aber ohne die teure vollständige
  Nachbarschaftsauswertung JEDER Iteration.

| Szenario | Baseline | Worst-Order-Auswahl | Gelegentlicher Kick | Tabu-verstärktes DLB |
|---|---|---|---|---|
| 24 Bestellungen | 1891 | 1897 (−0,31%) | 1888 (+0,17%) | 1888 (+0,17%) |
| 30 Bestellungen | 2435 | 2499 (−2,61%) | 2472 (−1,51%) | 2499 (−2,61%) |
| 80 Bestellungen, Kapazität 60 | 2867 | 3000 (−4,61%) | 2948 (−2,81%) | 2986 (−4,12%) |

Der gelegentliche Kick ist am wenigsten schlecht - beim großen Szenario der beste Wert unter allen
neun getesteten Varianten (−2,81%), bei 24 Bestellungen sogar minimal besser - aber weiterhin
unterlegen. Überraschend schwach: die Worst-Order-Auswahl, die naheliegendste und am wenigsten
invasive der drei Ideen (ändert nur WELCHE Bestellung verschoben wird, nicht wie stark), schneidet am
schlechtesten ab - sogar minimal schlechter als reiner Zufall. Plausible Erklärung: die zufällige
Auswahl sorgt für Streuung, welche Bestellung über verschiedene Neustarts hinweg ausprobiert wird;
"immer die teuerste zuerst" verengt diese Vielfalt und probiert über viele Neustarts hinweg tendenziell
ähnliche Züge, statt den Suchraum breiter abzudecken. Keine der drei Varianten übernommen.

Auf Nachfrage, ob auch schwarmbasierte Verfahren (Ant Colony, Bee Colony) etwas beitragen könnten:
Ant Colony passt strukturell schlecht auf die Batch-ZUTEILUNG (lebt von schrittweiser
Pfadkonstruktion wie bei TSP-Routing, wofür es hier keine vergleichbare Struktur gibt) und würde auf
Routing-Ebene dieselbe Wand treffen wie die Clustering-Versuche (die kleinen Routing-Teilprobleme
werden bereits durch 2-opt nahezu optimal gelöst). Bee Colony ist strukturell populationsbasiert -
würde das ohnehin knappe Neustart-Budget der großen Instanz auf mehrere parallele Lösungen verteilen,
derselbe Mechanismus, der Tabu Search und ALNS dort das Genick gebrochen hat. Als dosierte,
ACO-inspirierte Idee stattdessen geprüft: **Pheromon-gewichtete Zielwahl** - statt das Ziel-Batch
für eine verschobene Bestellung in `perturb_batches` rein zufällig zu wählen, ein leichtes
Pheromon-Gewicht je (Bestellung, Batch)-Paar mitführen (verstärkt nach erfolgreichen Neustarts,
verdunstet jeden Neustart) und die Zielwahl probabilistisch danach gewichten - anders als die
gescheiterte Worst-Order-Auswahl mit eingebauter Exploration durch Verdunstung, und genauso billig
pro Neustart wie die Baseline (kein Restart-Budget-Konflikt wie bei Tabu Search/ALNS).

| Szenario | Baseline | Pheromon-Zielwahl |
|---|---|---|
| 24 Bestellungen | 1891 | 1874 (+0,90%) |
| 30 Bestellungen | 2435 | 2499 (−2,61%) |
| 80 Bestellungen, Kapazität 60 | 2867 | 3007 (−4,86%) |

Bemerkenswert: obwohl diese Variante genauso billig wie die Baseline ist (keine zusätzliche
Berechnung pro Neustart, das "zu wenig Neustarts passen ins Budget"-Argument von Tabu Search/ALNS
greift also nicht), verliert sie beim großen Szenario fast identisch stark. Nicht die Kosten einer
Verfeinerung scheinen das Problem zu sein, sondern dass jede systematische Verzerrung der
Zufallsauswahl - selbst eine milde, durch Verdunstung regulierte - die Explorationsbreite genau in
dem Maß einschränkt, das bei größeren Instanzen etwas kostet.

**Methodische Nachprüfung (auf Nutzeranfrage: "hast du mal mehrere Szenarien getestet, nicht dass
das Ausreißer sind?"):** berechtigter Einwand - alle zehn bisherigen Vergleiche liefen gegen JEWEILS
EINE FESTE Szenario-Instanz je Größe, nur der algorithmus-eigene Zufalls-Seed wurde variiert, nicht
das zugrundeliegende Lagerlayout/die Bestellungen selbst. Nachgeprüft mit der Pheromon-Zielwahl
(billigster, fairster direkter Vergleich) über 3 UNABHÄNGIGE Szenario-Instanzen je Größe:

| Größe | Mittel über 3 Instanzen | Streuung über die Instanzen |
|---|---|---|
| 24 Bestellungen | +0,45% | −1,22% bis +2,10% |
| 30 Bestellungen | −0,36% | −1,99% bis +0,58% |
| 80 Bestellungen, Kapazität 60 | **−3,06%** | −1,35% bis −4,70% (durchweg negativ) |

Ergebnis: bei 24/30 Bestellungen war das bisherige Bild (z. B. die wiederholt beobachteten "−2,61%"
bei 30 Bestellungen) ein Artefakt der EINEN genutzten Instanz - über mehrere unabhängige Instanzen
gemittelt liegt die Streuung ZWISCHEN Instanzen in derselben Größenordnung wie die gemeldeten
Unterschiede selbst, also im Rauschen. Beim großen Stresstest-Szenario dagegen bleibt der negative
Befund robust - alle drei unabhängigen Instanzen zeigen ein Minus, auch wenn die genaue Höhe
schwankt (−1,35% bis −4,70%). **Der Kernbefund hält also:** die aktuelle Konfiguration ist speziell
bei der großen, praktisch wichtigsten Instanzgröße robust schwer zu schlagen - aber die genauen
Prozentzahlen bei kleinen/mittleren Instanzen aus der gesamten vorangegangenen Untersuchung (alle
neun anderen Varianten oben) beruhen auf einer einzelnen Instanz und sollten dort mit Vorsicht
behandelt werden, nicht als verlässliche Punktschätzung.

Auf gezielte Nachfrage nach neuerer, problem-spezifischer Literatur (statt allgemeiner
Metaheuristik-Paradigmen) recherchiert: **Variable Neighborhood Search** (VNS) ist mehrfach explizit
für das Order Batching Problem untersucht worden (u. a. Scholz et al., "Variable Neighborhood
Search strategies for the Order Batching Problem", *European Journal of Operational Research*).
Kern: eine GEORDNETE FOLGE strukturell unterschiedlicher Störungs-Nachbarschaften statt nur
zunehmender Störstärke (der Unterschied zur bereits gescheiterten "Adaptiven Störstärke") - bei
Stagnation wird zur nächsten, andersartigen Nachbarschaft eskaliert, bei jeder Verbesserung sofort
zurück zur billigsten. Getestet: N1 = bestehende Relocate-Störung, N2 = Swap-Störung, N3 =
Ketten-Relocate (zwei Bestellungen AUS DEMSELBEN Batch atomar gemeinsam in einen anderen Batch
verschieben - ein einzelner, unteilbarer Zug, den die bestehende Suche so nicht kennt). Aufgebaut
auf der bereits verschachtelten Zuteilungs+2-opt-Suche (siehe nächster Abschnitt), also ein fairer
Vergleich gegen die aktuell beste Konfiguration:

| Größe | Mittel über 3 Instanzen | Streuung |
|---|---|---|
| 24 Bestellungen | −0,21% | −0,52% bis +0,10% |
| 30 Bestellungen | −0,42% | −1,21% bis +0,35% |
| 80 Bestellungen, Kapazität 60 | −0,61% | −1,64% bis −0,12% |

Elfte getestete Variante, elftes Mal durchweg (wenn auch diesmal nur leicht) unterlegen - kein
einziges positives Größen-Mittel. Plausible Erklärung, dieselbe wie bei der Worst-Order-Auswahl
weiter oben: die zusätzliche STRUKTUR der geordneten Eskalation engt die Vielfalt der ausprobierten
Störungen leicht ein, während die bereits sehr effektive Kombination aus Warm-Start,
Don't-Look-Bits und verschachtelter 2-opt-Suche nahe an dem liegt, was mit diesem
Störungsmechanismus erreichbar ist. Nicht übernommen.

Auf Nachfrage, ob sich RL-Explorationsstrategien anwenden lassen (nach der zuvor als schlechter Fit
eingestuften Idee eines vollen Deep-Reinforcement-Learning-Ansatzes): **UCB1** (Upper Confidence
Bound, Auer et al. 2002), die klassische Bandit-Explorationsstrategie. Statt die Ziel-Batch-Wahl in
`perturb_batches` gleichverteilt zufällig zu treffen, bekommt jedes (Bestellung, Ziel-Batch)-Paar
einen Score aus Erfolgsrate PLUS einem expliziten Unsicherheits-Bonus für wenig ausprobierte Paare
(`score = Erfolgsrate + c·√(ln(N)/n)`, unbesuchte Paare zuerst). Der entscheidende Unterschied zur
bereits gescheiterten Pheromon-Zielwahl: reine Erfolgs-Verstärkung kann sich auf wenige "bewährte"
Ziele einpendeln, der UCB1-Bonus verhindert das strukturell.

| Größe | Mittel über 3 Instanzen | Streuung |
|---|---|---|
| 24 Bestellungen | +0,01% | −0,16% bis +0,11% |
| 30 Bestellungen | **+0,50%** | −0,04% bis +0,78% |
| 80 Bestellungen, Kapazität 60 | **+0,19%** | −0,12% bis +0,75% |

Die erste Variante seit der verschachtelten Zuteilungs+Routing-Suche (siehe nächster Abschnitt), die
bei KEINER Instanzgröße im Mittel schlechter abschneidet - kleiner als der dortige Gewinn
(+0,8-1,7%), aber der einzige durchweg nicht-negative Befund unter allen zwölf geprüften
Metaheuristik-Varianten. **Übernommen**, trotz des zusätzlichen Zustands (Versuchs-/Erfolgszähler je
Bestellung-Batch-Paar über alle ILS-Neustarts hinweg), da es das erste Ergebnis seiner Art ist, nicht
weil der Gewinn für sich genommen riesig wäre.

Auf Nachfrage, ob sich der UCB1-Erfolg noch ausbauen lässt ("wir wissen jetzt, dass mehr Exploration
gut ist - gibt's noch bessere Ansätze, z. B. Novelty Search?"), zunächst eine Korrektur der Prämisse:
nicht "mehr Exploration" war der Erfolgsfaktor - Random Walk, Simulated Annealing und ALNS waren
alle explorativer als die Baseline und sind alle gescheitert. UCB1 hat spezifisch geholfen, weil es
die Vielfalt der bestehenden Zufallsauswahl NICHT reduziert (jede Option wird garantiert mindestens
einmal probiert), sondern nur eine zusätzliche Gewichtung ergänzt. Zwei naheliegende Erweiterungen
DERSELBEN erfolgreichen Idee trotzdem geprüft, beide gegen die jetzt produktive UCB1-Baseline (nicht
gegen die alte Zufallsversion):

- **Thompson Sampling** statt UCB1: probabilistisch (Beta-Verteilung je (Bestellung,Ziel)-Paar, bei
  jeder Wahl daraus sampeln) statt deterministischer Score-Formel - der andere große Bandit-Klassiker,
  oft mit Vorteilen bei verrauschten Belohnungssignalen (unser Verbessert-Ja/Nein hängt vom kompletten
  nachgelagerten Suchergebnis ab, ist also durchaus verrauscht).
- **UCB1 auch für die QUELL-Auswahl** (welche Bestellung überhaupt verschoben wird, bisher weiterhin
  rein zufällig) - anders als die bereits gescheiterte rein-gierige Worst-Order-Auswahl schließt
  UCB1s Bonus nie eine Option komplett aus.

| Größe | Thompson Sampling | UCB1 auch für Quelle |
|---|---|---|
| 24 Bestellungen | −0,00% (Wash) | −0,23% |
| 30 Bestellungen | −0,24% | **−1,75%** |
| 80 Bestellungen, Kapazität 60 | −0,36% | −0,36% |

Beide schlechter, keine übernommen. Thompson Sampling bringt hier keinen Vorteil gegenüber UCB1s
fester Formel - eher im Gegenteil. UCB1 für die Quell-Auswahl ist klarer negativ (besonders bei 30
Bestellungen): obwohl der Explorationsbonus nie eine Option komplett ausschließt, kostet schon die
bloße Umgewichtung, WELCHE Bestellung verschoben wird, etwas Wertvolles - dieselbe Grundrichtung wie
bei der gescheiterten Worst-Order-Auswahl, nur milder. Fazit: der UCB1-Gewinn saß offenbar genau in
der schmalen Kombination "nur für die Ziel-Wahl" - weder ein anderer Bandit-Algorithmus noch dieselbe
Idee auf mehr Entscheidungspunkte auszuweiten, verbessert das weiter.

Fazit nach vierzehn geprüften Metaheuristik-Varianten (vier ILS-Akzeptanz-/Störungsvarianten, zwei
grundsätzlich andere Paradigmen als Vollersatz - Tabu Search, ALNS -, vier dosierte Kombinationen
derselben Ideen einschließlich der Pheromon-Zielwahl, Variable Neighborhood Search als
problem-spezifisch literaturbelegter Kandidat, UCB1 als RL-Explorationsstrategie, sowie zwei
Erweiterungen von UCB1 selbst): dreizehn der vierzehn Varianten schlagen die aktuelle Konfiguration
nicht - speziell beim größten, praktisch wichtigsten Stresstest-Szenario schneidet über mehrere
unabhängige Instanzen bestätigt fast jede getestete Verfeinerung schlechter ab. UCB1 (nur für die
Ziel-Batch-Wahl) ist die einzige Ausnahme und wurde übernommen.

## Benchmark: Zuteilung und Routing verschachtelt statt nacheinander optimiert

Ursprünglich liefen Zuteilungssuche und Routen-Politur zweistufig: die Inter-Batch-Suche
konvergierte komplett mit Nearest-Neighbor-Qualitäts-Routen, ERST DANACH wurde jeder Batch einmalig
per 2-opt poliert. Zuteilungs-Kandidatenzüge wurden also anhand noch nicht routenoptimierter
Distanzen bewertet - das kann zu suboptimalen Zuteilungsentscheidungen führen. Auf Nutzerfrage
("ist das, was Won & Olafsson 2005 vorgeschlagen haben?") in der Literatur verortet: Won/Olafsson
(2005), "Joint order batching and order picking in warehouse operations" (*Int. J. Prod. Res.*
43(7): 1427–1442), verfolgen denselben Grundgedanken - die Batchbildung anhand der TATSÄCHLICHEN
Routenqualität statt einer groben Näherung zu bewerten -, allerdings für eine andere Zielfunktion
(Kommissionierzeit UND Bestellungs-Wartezeit statt hier nur Distanz) und in einem Online-Kontext mit
Bestellungs-Ankunftszeiten, den diese Demo nicht modelliert. "Joint Order Batching and Picker
Routing Problem" (JOBPRP) ist mittlerweile ein eigenes, aktiv beforschtes Teilgebiet mit weiteren
Ansätzen (cluster-basierte Tabu Search, exakte Branch-and-Cut-Verfahren, ein PSO+ACO-Hybrid).

Umgesetzt: ein Batch verlässt die Don't-Look-Bits-Warteschlange erst, wenn WEDER ein verbessernder
Relocate/Swap-Zug NOCH ein verbessernder 2-opt-Zug auf seiner eigenen Route mehr gefunden wird
(`_try_move_or_two_opt`) - dieselbe Warteschlangen-Logik wie zuvor, nur um die Routing-Nachbarschaft
erweitert. Über mehrere unabhängige Testinstanzen (Lehre aus der Metaheuristik-Untersuchung oben:
eine einzelne Instanz kann irreführen):

| Größe | Einmalige Konvergenz | Volle ILS-Suche (gleiches Zeitbudget) |
|---|---|---|
| 24 Bestellungen | +1,42% | +1,29% |
| 30 Bestellungen | +1,05% | +1,73% |
| 80 Bestellungen, Kapazität 60 | +0,82% | +0,92% |

Der erste durchweg positive Befund seit Iterated Local Search selbst - und der erste, der auch bei
der großen Instanz nicht negativ ausfällt (anders als alle zehn zuvor getesteten
Metaheuristik-Varianten). Kostet ~1,8-2x mehr Zeit je Konvergenz (weniger ILS-Neustarts passen ins
Zeitbudget), aber die bessere Qualität pro Neustart gleicht das mehr als aus - anders als bei Tabu
Search/ALNS, wo genau dieser Mechanismus zum Verlust führte.

**Wichtige Einschränkung, empirisch gefunden:** 2-opt wird jetzt INKREMENTELL auf die Route
angewendet, die durch Einfügen/Entfernen während der Zuteilungssuche entstanden ist - ein anderer,
nicht zwingend besserer Startpunkt für 2-opt als ein kompletter Neuaufbau (2-opt kennt mehrere
lokale Optima je nach Startroute). Eine billige Absicherung (`_apply_final_safety_net`, einmalig am
Ende, nicht pro Neustart: je Batch die kürzere von verschachtelt gefundener Route vs. frischem
NN+2opt-Aufbau) fängt das auf Routen-Ebene ab. Sie kann aber nicht verhindern, dass die
verschachtelte Suche gelegentlich zu einer ANDEREN Batch-ZUTEILUNG als die alte Suche führt, die
sich auf einer EINZELNEN Instanz als leicht schlechter herausstellt (konkret beobachtet am
Standard-Demo-Szenario dieser App: 899m statt vorher 883m, über 10 Perturbations-Seeds hinweg
stabil reproduzierbar, also kein Zufallsrauschen) - dieselbe Einzelinstanz-Varianz wie oben bei den
Metaheuristik-Kandidaten, hier nur zufällig auf dem meistgesehenen Szenario. Bewusst nicht behoben:
beide Suchpfade parallel laufen zu lassen und das bessere Ergebnis zu nehmen würde das garantieren,
verdoppelt aber die Rechenzeit je Neustart und damit den Effizienzvorteil der Verschachtelung selbst
- der Mittelwert über viele Instanzen zählt (siehe Benchmark-Methodik oben), nicht jede einzelne.

## Bugfix: angezeigte Laufdistanz konnte vom tatsächlichen Suchergebnis abweichen

Auf Nutzeranfrage ("Kannst du bitte mal ein komplettes Code Review machen?") ein echter, bereits
produktiv gewesener Fehler gefunden: `app.py` baute die je-Batch-2opt-Animation für den UI-Slider
unabhängig per `route_batch` (frischer Nearest-Neighbor+2opt-Aufbau) neu auf und verwarf dabei die
vom eigentlichen Suchalgorithmus (`iterated_local_search_history`) gefundenen, bereits optimierten
Routen komplett. Da `route_batch` einen ANDEREN 2-opt-Startpunkt hat als die verschachtelte Suche
(siehe Abschnitt oben), kann es dabei ein schlechteres lokales Optimum treffen - empirisch bestätigt:
bei 14 von 20 zufälligen Testinstanzen war die tatsächlich angezeigte "Laufdistanz" messbar (bis zu
~3%) schlechter als das, was die Suche selbst gefunden hatte, nie besser. Betraf sowohl die
Kennzahlen-Kachel als auch den PDF-Export (beide nutzen dieselben, unabhängig neu aufgebauten
Routen) - und führte zu einer sichtbaren Inkonsistenz zwischen der "Laufdistanz"-Kennzahl und der
Bildunterschrift "Gesamtdistanz beim angezeigten Schritt" direkt darunter, die aus der (korrekten)
Such-Historie stammt.

Behoben mit einer neuen, eigens getesteten Funktion `reconcile_per_batch_histories` in
`batch_local_search.py`: vergleicht je Batch das Ende der unabhängig aufgebauten Animation mit dem
tatsächlichen Suchergebnis und hängt bei Bedarf einen zusätzlichen, verbessernden Schritt an - die
volle 2-opt-Animation bleibt für den Slider erhalten, endet aber garantiert nicht schlechter als das,
was die Suche tatsächlich gefunden hat. Auf 20 Testinstanzen verifiziert: 0 Abweichungen nach der
Reparatur (vorher 14/20). Nebenbei bemerkt: dieser Fehler existierte erst SEIT der verschachtelten
Zuteilungs+Routing-Suche weiter oben - davor waren die Politur-Phase und `app.py`s unabhängiger
Neuaufbau exakt dieselbe Operation (`route_batch` auf dieselben `final_batches` angewendet), also
zwangsläufig identisch.

**Nachtrag (auf Nutzerhinweis "Die Gesamtvisualisierung scheint von der Einzelbatchvisualisierung
abzuweichen!?"):** der erste Fix verglich nur die DISTANZ (`dist < history[-1][1] - EPS`), nicht die
Route selbst. Zwei unterschiedliche Reihenfolgen können aber exakt dieselbe Distanz ergeben
(Gleichstand) - ein reiner Distanzvergleich ließ solche Gleichstände unangetastet, wodurch dieselbe
Batch-Route im "Batch-Zuteilung optimieren"-Übersichtsplot (zeigt das Suchergebnis direkt) und in
"Batch im Detail" (zeigt die unabhängig aufgebaute Animation) unterschiedlich AUSSEHEN konnte, obwohl
beide exakt gleich kurz waren. Empirisch bestätigt: **80 von 142 zufällig geprüften Batches
betroffen** - deutlich mehr als die 14/20 der ursprünglichen, reinen Distanz-Abweichung. Da das
Suchergebnis nachweislich nie schlechter als die unabhängige Rekonstruktion ist (siehe oben), genügt
jetzt ein reiner Routen-Vergleich (`route != history[-1][0]`) - sicher und ohne Distanzberechnung im
Normalfall. Live im Browser verifiziert: die Routen-Koordinaten des Übersichts- und des
Detail-Plots stimmen jetzt exakt überein (per direktem Vergleich der Plotly-Figurdaten).

## UX: Batch-Farben in Übersicht und Detailansicht waren inkonsistent

Auf Nutzeranfrage nach Verbesserungen an der Visualisierung geprüft und gefunden:
`build_batch_detail_figure` nahm die Batch-Nummer nie entgegen und färbte die Detailansicht deshalb
immer mit der ersten Palettenfarbe (`BATCH_COLORS[0]`) - unabhängig davon, welcher Batch tatsächlich
ausgewählt war. Wählte man z. B. "Batch 3" (Grün in der Übersicht), erschien er in der Detailansicht
trotzdem in Blau. Behoben, indem beide Figuren jetzt dieselbe kleine Hilfsfunktion (`_batch_style`)
nutzen; per Skript gegen die Übersichtsfigur verifiziert (`batch_idx` 0, 2, 5 → alle Farben/Symbole
stimmen exakt überein).

Dabei gleich zwei weitere, selbst beobachtete Schwächen der Farbpalette behoben:
- **Nur 8 Farben, wiederholten sich bei mehr Batches** (im "Heterogene Artikelgrößen"-Szenario
  waren schon 15 Batches zu sehen) - Batch 1 und Batch 9 waren farblich nicht unterscheidbar.
  Behoben: ab der zweiten Palettenrunde wechselt zusätzlich das Marker-Symbol (Kreis, Quadrat,
  Raute, ...), sodass bis zu 8×8=64 Batches eindeutig unterscheidbar bleiben.
- **Rot und Grün lagen direkt nebeneinander** in der ursprünglichen Palette (`#dc2626`, `#16a34a`)
  - für farbfehlsichtige Nutzer (Rot-Grün-Schwäche betrifft ~8% der Männer) schwer zu unterscheiden.
  Ersetzt durch die Okabe/Ito-Palette (2008), eine Standardempfehlung für farbfehlsichtige
  Zugänglichkeit; Schwarz aus dem Original-Set durch ein Braun ersetzt, da die Packstation
  (Depot-Symbol) bereits fast schwarz eingefärbt ist.

Vier neue, gezielte Tests für `_batch_style` (Übereinstimmung mit der Übersichtsfigur,
Determinismus, Eindeutigkeit über 64 Kombinationen, Symbolwechsel nach Palettenerschöpfung).

## UX: Ergebnis nachvollziehbarer gemacht (Distanz je Wegabschnitt, räumliche Streuung)

Auf Nutzeranfrage ("kann man das Ergebnis noch besser nachvollziehbar machen?") zwei gezielte
Ergänzungen statt allgemeiner Politur:

- **Distanz je Wegabschnitt in der Detailansicht**: bisher zeigte jeder Halt nur seine Nummer in der
  Besuchsreihenfolge. Der Hover-Text nennt jetzt zusätzlich die Distanz DIESES Abschnitts (vom Depot
  bzw. vom vorherigen Halt) - sichtbar, wo die Gesamtdistanz eines Batches tatsächlich anfällt, statt
  nur die Summe zu kennen. Die Bildunterschrift ergänzt außerdem den Rückweg vom letzten Halt zum
  Depot, der bisher gar nicht separat sichtbar war. Neue Funktion `route_leg_distances` in
  `batch_evaluation.py` (Summe entspricht exakt `route_distance`) - bewusst NICHT in die bereits
  optimierte `route_distance` selbst integriert, um den sorgfältig getunten Hot-Path unangetastet zu
  lassen (siehe numpy-Indexierungs-Benchmark oben).
- **Räumliche Streuung je Batch**: neue Bildunterschrift bei "Batch im Detail" zeigt, über wie viele
  Gänge sich die Positionen eines Batches erstrecken ("liegen in 3 Gängen (Gang 2 bis 4)") - macht
  sichtbar, wie räumlich kompakt oder verstreut eine Zuteilung tatsächlich ist, ohne die (bereits im
  Dropdown-Label vorhandene) Bestell-/Positionsanzahl zu wiederholen.

Eine dritte, naheliegende Idee (eine Kausalerklärung, WARUM Greedy-Seed oder Zonen-Sweep in einem
konkreten Szenario vorne liegt) wurde bewusst NICHT umgesetzt - eine belastbare Erklärung dafür wäre
kaum verlässlich zu generieren, ohne im Einzelfall zu überinterpretieren.

Drei neue Tests für `route_leg_distances` (Summe entspricht `route_distance`, korrekte Anzahl
Abschnitte, leere Route). Live im Browser verifiziert: Hover-Text je Halt und beide neuen
Bildunterschriften rendern korrekt.

## `/code-review` über die gesamte Codebasis (alle Commits als ein Diff)

Auf Nutzeranfrage ("Kannst du den Befehl auch auf alle Commits anwenden?") den strukturierten
`/code-review`-Ablauf (8 Finder-Blickwinkel über parallele Subagenten, danach Einzelverifikation)
nicht nur auf den letzten Commit, sondern auf den KOMPLETTEN kumulierten Diff seit dem allerersten
Commit angewendet (`git diff` gegen den leeren Git-Baum) - im Effekt eine vollständige Durchsicht
der gesamten ~5100-Zeilen-Codebasis. Zehn Funde, alle nach Verifikation umgesetzt:

1. **`recommended_num_batches` rundete vor der Division statt danach** (`batch_ortools_solver.py`):
   im Volumen-Kapazitätsmodus konnte das die nötige CP-SAT-Batch-Slot-Zahl systematisch
   unterschätzen (verifiziert per Simulation, nicht nur als theoretische Rundungs-Koinzidenz:
   capacity=5,5, total_size=533,8 über 31 Positionen ergab vorher 90 statt der tatsächlich nötigen
   98 Slots) - eine eigentlich zulässige Instanz im CP-SAT-Tab konnte dadurch fälschlich als
   "INFEASIBLE" erscheinen. Fix: exakt auf den echten Fließkommawerten aufrunden (`math.ceil`)
   statt total_size/capacity vorher einzeln zu runden.
2. **Politur-Cooldown skalierte anders als der CP-SAT-Tab-Cooldown**: der CP-SAT-Tab bremst gezielt
   proportional zur zuletzt genutzten Rechenzeit, die neuere Politur-Sektion nutzte dagegen einen
   festen 5s-Cooldown, obwohl ein Politur-Lauf selbst bis zu ~20s dauern kann - genau das
   Missbrauchsmuster, vor dem der CP-SAT-Tab bewusst schützt, blieb hier offen. Fix: Cooldown
   skaliert jetzt ebenfalls mit der zuletzt tatsächlich gemessenen Politur-Laufzeit.
3. **`greedy_seed_batching`/`zone_clustering_batching` vertauschten die letzten zwei Parameter**
   (`aisle_spacing`/`item_sizes`) zwischen zwei sonst identischen Signaturen - an den bestehenden
   Aufrufstellen nie live falsch, aber ein Fallstrick für künftige Änderungen. Fix: Reihenfolge
   angeglichen, alle Aufrufstellen (inkl. positionaler Test-Aufrufe) entsprechend angepasst.
4. **`polish_key` dupliziert weiterhin von Hand, was `cache_key` bereits zusammensetzt**: dieselbe
   Verdopplungs-Falle, die `current_key_cpsat` schon einmal das Vergessen von `capacity_mode`
   kostete. Fix: neue gemeinsame Funktion `distance_scenario_key` (`batch_warehouse.py`, direkt
   neben `build_distance_matrix` definiert) - sowohl `app.py`s `distance_key`/`cache_key` als auch
   `polish_key` nutzen sie jetzt als einzige Quelle der Wahrheit.
5. **Die Distanzmatrix `D` wurde bei JEDEM Rerun neu berechnet**, auch bei Widget-Interaktionen, die
   sie gar nicht betreffen (z. B. Personalkosten-Regler) - eine O(n²)-Berechnung außerhalb jeder
   Cache-Grenze. Fix: `_build_distance_matrix_cached` (`@st.cache_data`, Muster wie
   `_compute_solutions`), gekeyt über `distance_scenario_key`.
6. **Eine je-Batch-Kapazitätsgröße wurde in `_try_moves_from_batch` wiederholt neu aufsummiert**,
   obwohl sie im jeweiligen Schleifendurchlauf konstant war (Muster war an einer dritten Stelle in
   derselben Funktion bereits korrekt vorgehoben). Fix: einmalig vorab in `batch_sizes` berechnet,
   an allen vier betroffenen Stellen per Lookup statt Neuberechnung genutzt.
7. **`two_opt_history` verwarf das von `find_two_opt_move` bereits berechnete Distanz-Delta** und
   summierte die komplette Route stattdessen bei jedem akzeptierten Zug neu auf - läuft bis zu 200x
   je Aufruf, und wird über die gesamte Suche hinweg wiederholt aufgerufen. Fix:
   `find_two_opt_move` gibt das Delta jetzt zusätzlich zurück, `two_opt_history` UND
   `_try_move_or_two_opt` nutzen es per einfacher Addition statt `route_distance` neu aufzurufen.
8. **`classify_comparison`s 3+-Kandidaten-Zweig (`top_two_tied`) hatte keinerlei Testabdeckung**,
   obwohl die Produktion ihn mit bis zu 4 echten Kandidaten aufruft. Fix: zwei neue Tests (Zweig
   trifft zu / trifft nicht zu, beide mit 3 Kandidaten).
9. **Die "liegen in N Gängen"-Bildunterschrift behauptete Belegung, maß aber nur eine Spannweite**
   (`max_aisle - min_aisle + 1`) - bei Batches mit Lücken (z. B. nur Gang 2 und Gang 9 belegt) eine
   irreführende Übertreibung. Fix: Formulierung auf "erstrecken sich über eine Spanne von N Gängen"
   geändert, misst weiterhin bewusst die Spannweite (korreliert besser mit der Routenlänge als eine
   reine Belegungszahl).
10. **Zwei Tests konnten nicht fehlschlagen, selbst wenn der geprüfte Code kaputt wäre**: eine
    2-Item-Route hat strukturell kein nicht-benachbartes Kantenpaar, der Test war also unabhängig
    von `find_two_opt_move`s Korrektheit grün; ein Zeitbudget-Test tolerierte das 10-fache des
    erwarteten Werts (`elapsed < 3.0s` bei `time_budget_s=0.3`), was auch eine komplett
    deaktivierte Prüfung nicht zuverlässig aufgefangen hätte. Fix: erster Test nutzt jetzt eine
    5-Item-Instanz mit per Vollenumeration verifiziertem Optimum (plus ein neuer Gegentest für den
    tatsächlichen Verbesserungsfall, inkl. Delta-Korrektheit); zweiter Test nutzt `max_restarts`
    so hoch (1 Million), dass eine deaktivierte Zeitprüfung ~45 Minuten statt ~0,3s bräuchte -
    gemessen: mit funktionierender Prüfung konsistent ~0,31s, Toleranz auf `< 1.0s` verschärft.

Alle zehn Funde nach der Umsetzung live/per Test erneut verifiziert - 92/92 Tests grün (3 neu:
zwei `classify_comparison`-Tests, ein `find_two_opt_move`-Verbesserungstest), CP-SAT-Tab und
Politur-Cooldown live im Browser bestätigt.

## `/code-review` über die gesamte Codebasis, zweite Runde

Auf Nutzeranfrage ("Kannst du solch ein komplettes Code Review über alle Diffs bitte gleich noch
einmal machen?") den kompletten Ablauf ein zweites Mal auf den kumulierten Diff angewendet - diesmal
speziell auch geprüft, ob die Fixes der ersten Runde selbst konsistent sind und ob sie neue Probleme
eingeführt haben. Bemerkenswert: ein Finder-Agent behauptete, Streamlit-Slider/Selectbox würden
abstürzen, wenn ihr gültiger Wertebereich unter einen gespeicherten Session-State-Wert schrumpft -
das widersprach direkt einem Befund aus der VORHERIGEN Runde. Statt einer der beiden Behauptungen zu
vertrauen, per `streamlit.testing.v1.AppTest` selbst nachgebaut: kein Absturz, Streamlit setzt
den Wert graceful zurück - der Fund war falsch und wurde verworfen, bevor er umgesetzt wurde.
Ebenso wurde ein Fund zu einer potenziell negativen "Ersparnis"-Anzeige vor der Umsetzung über 598
zufällige Szenarien (volle Reglerspannweite) stress-getestet: schlechtester beobachteter Fall war
Gleitkomma-Rauschen (3,4e-16), nie ein echter Verlust - der Fund blieb bestehen (die Anzeige war
technisch ungeschützt), aber mit ehrlich eingeordneter, sehr geringer praktischer Eintrittswahr-
scheinlichkeit.

Zehn verifizierte Funde, alle umgesetzt:

1. **CP-SAT-Tab-Cooldown nutzte das KONFIGURIERTE Zeitlimit, nicht die tatsächliche Laufzeit** -
   `elapsed` wurde berechnet, aber nie für den Cooldown verwendet; ein Solve, der nach 2s von 10s
   Limit bereits optimal bewies, musste trotzdem 10s+Puffer abwarten. Die Politur-Sektion (Runde 1)
   nutzte dagegen schon korrekt die tatsächliche Laufzeit - ihr eigener Kommentar behauptete
   faelschlich, das Verhalten des CP-SAT-Tabs zu spiegeln.
2. **`sync_query_params` dupliziert `SETTING_SPECS.url_param` von Hand** (14 hart codierte
   Literale) statt sie wie `load_permalink_settings` zu lesen - dieselbe Bug-Klasse ein drittes Mal,
   diesmal bei der Permalink-URL statt einem Cache-Key.
3. **Cooldown-Gate-Logik zwischen CP-SAT-Tab und Politur-Sektion dupliziert** - hing direkt mit Fund
   1 zusammen (die Verdopplung erlaubte genau die stillschweigende Abweichung).
4. **Je-Batch-Distanzen wurden nach jedem verbessernden ILS-Neustart komplett neu berechnet**,
   obwohl die Suche sie bereits intern kannte (`current_dists`) - nur ihre Summe landete in der
   Historie.
5. **`batch_capacity_size` ~10x als rohes `sum()` reimplementiert** statt aufgerufen (drei Module).
6. **`solution_totals` totes Code, 3 Aufrufstellen reimplementieren es inline** (app.py,
   batch_pdf_export.py, batch_ortools_solver.py).
7. **Auffüll-Schleifen beider Batching-Strategien fast wortgleich dupliziert.**
8. **`_try_moves_from_batch`s drei Zug-Arten verpacken das Ergebnis je dreimal identisch.**
9. **`math.ceil` kann durch Summierungs-Rundungsrauschen einen Batch-Slot zu viel vorschlagen**
   (einseitig, sehr geringe Schwere).
10. **Ersparnis-Kennzahlen (Laufdistanz/Zeit/Kosten ggü. Einzelkommissionierung) waren nicht
    formal gegen negative Werte abgesichert** - hätte ein doppeltes Minuszeichen wie "--7%" erzeugt.

**Fixes:** (1)+(3) gemeinsam gelöst über einen neuen geteilten Helfer
`cooldown_seconds_remaining`/`cooldown_record` (`batch_presets.py`), der mit der tatsächlich
gemessenen Laufzeit statt einem konfigurierten Limit skaliert - von beiden Aufrufstellen genutzt.
(2) `sync_query_params` iteriert jetzt `SETTING_SPECS` und wendet `spec.caster` vor dem
Stringifizieren an (verhindert z. B., dass ein als float gehaltener Seed als "11.0" statt "11"
geschrieben und beim Zurücklesen mit einem stillen `ValueError` verworfen wird). (4)
`_inter_batch_search_dlb_from_state` gibt die je-Batch-Distanzen jetzt zusätzlich zurück
(`(history, dists)` statt nur `history`), `iterated_local_search_history` übernimmt sie direkt.
(5)+(6) alle betroffenen Stellen rufen jetzt `batch_capacity_size`/`solution_totals` auf. (7) neue
gemeinsame Funktion `_fill_batch_from_seed` (`batch_construction.py`) - beide Strategien
unterscheiden sich jetzt nur noch darin, WELCHE Bestellung als nächster Seed gewählt wird. (8) neue
gemeinsame Funktion `_package_move` (`batch_local_search.py`). (9) `math.ceil(total_size / capacity
- EPS)`. (10) Vorzeichen über `{-x:+.0f}`-Formatspec statt eines hart codierten `-`-Präfix - zeigt
korrekt "-23%" (Ersparnis) oder "+7%" (Mehrweg) statt eines garantiert falschen "--7%".

99/99 Tests grün (7 neu: 3 `sync_query_params`, 3 Cooldown-Helfer, 1 Delta-Korrektheit für die
neuen `_inter_batch_search_dlb`-Rückgabewerte). Live im Browser verifiziert: Standardszenario
liefert weiterhin exakt 883 m (identisch zu Dutzenden früheren Beobachtungen in dieser Session -
starke Bestätigung, dass die Auffüll-Schleifen- und Zug-Verpackungs-Refactorings verhaltensgleich
sind), CP-SAT-Tab-Cooldown reagiert korrekt auf die tatsächliche Solve-Zeit, Politur-Cooldown über
den geteilten Helfer weiterhin fehlerfrei, Permalink-URL enthält weiterhin alle erwarteten Felder.

## `/code-review` über die gesamte Codebasis, dritte Runde

Auf Nutzeranfrage ein drittes Mal denselben Ablauf angewendet. Diesmal deutlich weniger Funde als in
den ersten beiden Runden (3 von 5 Finder-Blickwinkeln kamen komplett leer zurück) - ein plausibles
Zeichen, dass sich die Codebasis nach zwei gründlichen Runden tatsächlich stabilisiert hat, ehrlich
so berichtet statt künstlich auf eine Mindestanzahl Funde aufgefüllt. Fünf echte Funde, alle
umgesetzt:

1. **Die beiden Relocate-Blöcke in `_try_moves_from_batch` sind dieselbe Operation mit
   vertauschten Quelle/Ziel-Rollen**, keine zwei unabhängigen Zug-Arten - Runde 2 hatte nur den
   identischen Abschluss (`_package_move`) zusammengefasst, nicht die ~40 Zeilen Kernlogik selbst.
2. **PDF-Export lief bei JEDEM Streamlit-Rerun neu**, an jeder Aufrufstelle (Hauptergebnis,
   CP-SAT-Tab, je Strategie-Tab, je Politur-Ergebnis) - `st.download_button` braucht die Bytes
   vorab berechnet, war aber nirgends gecacht, obwohl genau das der Grund für
   `_compute_solutions`/`_build_distance_matrix_cached` war.
3. **`classify_comparison` schreibt dieselbe Gap-Prozent-Formel zweimal** im selben Funktionskörper.
4. **Bestellungsgrößen im Tausch-Zweig von `_try_moves_from_batch` wurden redundant neu
   berechnet** - der Batch-Ebene-Fall (`batch_sizes`) war in Runde 2 schon behoben, der
   Bestellungs-Ebene-Fall bewusst für später zurückgestellt.
5. **`solve_with_cpsat` und `exact_tsp_single_batch` duplizieren die Hamiltonkreis-Auslese-Logik**
   (Knoten-für-Knoten-Rundgang ab Depot) fast wortgleich.

**Fixes:** (1) neue gemeinsame Funktion `_try_relocate_one(src, dst, oid, ...)` - beide
Relocate-Richtungen rufen sie jetzt mit vertauschten `(src, dst)` auf, bei UNVERÄNDERTER
Verschachtelungsreihenfolge der äußeren Schleifen (damit sich an der "erste Verbesserung
gewinnt"-Suchreihenfolge nichts ändert). (2) neue Funktionen `pdf_cache_key`/
`generate_batch_plan_pdf_cached` (`batch_ui_panel.py`, per `@st.cache_data`), gekeyt über
`distance_scenario_key` plus Bestellzuordnung/Artikelgrößen - `batches`/`final_routes` selbst
bleiben bewusst unmaskiert (Streamlit hasht normale Listen/Dicts direkt und günstig). (3) neue
Hilfsfunktion `_relative_gap_pct`. (4) zwei Bestellungsgrößen-Dicts (`order_sizes_i`/
`order_sizes_j`) vorab je Batch statt pro Kandidatenpaar neu berechnet. (5) neue gemeinsame
Funktion `_extract_circuit_route(solver, arc_lits)` - die Übersetzung von lokaler Knotennummer auf
tatsächlichen Item-Index bleibt bewusst Sache der beiden Aufrufer, da sie sich unterscheidet.

99/99 Tests grün (keine neuen - reiner Refactor, die bestehende Suite deckt das Verhalten bereits
ab). Live im Browser erneut bestätigt: Standardszenario weiterhin exakt 883 m (auch nach der
riskantesten Änderung dieser Runde, der Relocate-Vereinheitlichung), PDF-Download-Button rendert
fehlerfrei (der Cache-Wrapper muss dafür bereits einmal erfolgreich gelaufen sein), Vergleichs-Tab
zeigt weiterhin korrekt "Greedy-Seed-Batching liegt hier vorn".

## UX: Einleitungstext war seit den größeren Suche-Erweiterungen nicht mehr aktualisiert

Auf Nutzerhinweis ("Der Einleitungstext in der App scheint veraltet") geprüft: der sichtbare
Absatz direkt unter dem Titel (nicht der bereits mehrfach aktualisierte "Wie funktioniert diese
Demo?"-Expander) sagte noch "jede Batch-Route zusätzlich mit 2-opt Local Search verbessert" - das
stammt offenbar aus einer frühen Phase, bevor Inter-Batch-Suche, Iterated Local Search und die
CP-SAT-Politur ergänzt wurden, und wurde bei keiner der früheren "App-Texte prüfen"-Runden mit
angefasst (die kümmerten sich um den Expander und die mathematische Formulierung, nicht um diesen
kurzen Eröffnungsabsatz). Das unterschlug den eigentlichen Kern dessen, was die App leistet: nicht
nur die Route je Batch wird optimiert, sondern auch die Batch-ZUTEILUNG selbst.

Text ergänzt um "durch eine verschachtelte Lokalsuche weiter verbessert: sowohl die Batch-Zuteilung
selbst... als auch die Route je Batch (2-opt), ergänzt um Iterated Local Search... und optional eine
exakte CP-SAT-Politur" - bewusst weiterhin kurz gehalten (Details bleiben im Expander), nur die
irreführende Verkürzung auf "nur 2-opt" korrigiert. Live im Browser verifiziert (inkl. eines selbst
verursachten Zeilenumbruch-Fehlers - "Batch-\nZuteilung" wurde als "Batch- Zuteilung" mit
überflüssigem Leerzeichen gerendert, direkt behoben und erneut bestätigt).

## Benchmark: konsolidierte Kennzahlen für Inter-Batch-Suche, verschachtelte Suche und ILS

Beim gründlichen Prüfen der App-Texte (Nutzeranfrage, nach der bereits behobenen Veraltung des
Einleitungstexts oben) fiel eine Inkonsistenz auf: drei verschiedene Stellen zitierten drei
verschiedene Zahlen für eng verwandte, aber nicht identische Vergleiche - der "Wie funktioniert
diese Demo?"-Expander in app.py sprach von **19-26%** kürzerer Gesamtdistanz "gegenüber reiner
Konstruktion ohne jede Verbesserung", der Modul-Docstring von `batch_local_search.py` von **8-18%**
für die Inter-Batch-Suche allein, und der ursprüngliche Prototyp-Benchmark oben von **7-18%**. Die
19-26%-Zahl ließ sich dabei in keiner einzigen Quelle - weder README noch Code-Kommentar -
irgendwo tatsächlich nachweisen; sie beschrieb offenbar einen anderen (breiteren) Vergleich als die
anderen beiden Zahlen, wurde aber nie durch einen eigenen Benchmark belegt.

**Statt eine der drei Zahlen zu raten, ein neuer, einheitlicher Stufen-Benchmark**, aus dem sich
jetzt alle drei App-/Code-Zahlen ableiten: 4 Szenarien (Standard 24/Kapazität 15, Mittel 40/15,
Knappe Kapazität 30/10, Worst Case 80/60 - dieselben Eckwerte wie in den Benchmarks oben) × 3
unabhängige Seeds × beide Strategien (Greedy-Seed, Zonen-Sweep) = 24 Läufe je Pipeline-Stufe. Jede
Instanz durchläuft dieselben vier Stufen:

| Stufe | Beschreibung |
|---|---|
| 0 | Reine Konstruktion, Routen per Nearest-Neighbor OHNE 2-opt |
| 1 | + 2-opt je Batch (`route_batch`), OHNE Inter-Batch-Suche |
| 2 | + Inter-Batch-Suche verschachtelt mit 2-opt (`inter_batch_local_search_history`) |
| 3 | + Iterated Local Search obendrauf (`iterated_local_search_history`) |

Daraus drei Kennzahlen, jede über alle 24 Läufe als Min-Max-Spanne:

| Kennzahl | Vergleich | Ergebnis | Ersetzt |
|---|---|---|---|
| A: Inter-Batch-Suche-Beitrag | Stufe 1 → Stufe 2 | **5-20%** (Mittel 13,8%) | die alten 7-18%/8-18% |
| B: verschachtelte Suche gesamt | Stufe 0 → Stufe 2 | **10-25%** (Mittel 18,0%) | das unbelegte 19-26% |
| C: ILS-Zusatzgewinn | Stufe 2 → Stufe 3 | **0-6%** (Mittel 1,8%) | die alte 1-4,8%/0,9-4,8%-Zahl |

Kennzahl A und die frühere Prototyp-Zahl (7-18%) messen denselben Vergleich auf unterschiedlichen
Instanz-Sets - beide Spannen überlappen deutlich, die neue ist nur breiter, weil sie zusätzlich das
Worst-Case-Szenario (80 Bestellungen, Kapazität 60) und eine knappe Kapazität (30/10) einschließt,
in denen wenig Verschiebespielraum bleibt (Kennzahl A dort so niedrig wie 4,5%). Kennzahl B ist die
tatsächlich zutreffende Ersetzung für die vorher unbelegte 19-26%-Zahl im Einleitungs-Expander:
"gegenüber reiner Konstruktion ohne jede Verbesserung" bedeutet dort ausdrücklich auch ohne 2-opt
(Stufe 0), nicht nur ohne Inter-Batch-Suche (Stufe 1) - ein systematisch größerer Vergleich als
Kennzahl A, was erklärt, warum B durchweg über A liegt.

App-Text (`app.py`), Modul-Docstring (`batch_local_search.py`) und die `ILS_TIME_BUDGET_S`-Konstante
(`batch_constants.py`) zitieren jetzt alle drei aus genau diesem einen Benchmark, statt wie zuvor
unabhängig voneinander gepflegte (und dadurch auseinandergelaufene) Zahlen zu tragen.

## UX: "Auf Nutzeranfrage ergänzt"-Formulierungen aus den App-Erklärtexten entfernt

Auf Nutzerhinweis: Formulierungen wie "Auf Nutzeranfrage ergänzt" sind in diesem README als
Entstehungs-Protokoll passend (siehe die vielen Benchmark-Abschnitte oben), wirken in den
Erklärtexten der App selbst aber merkwürdig - eine Demo-Besucherin hat keinen Kontext für "wessen
Anfrage" und die Formulierung lenkt vom eigentlichen Inhalt ab. Betroffen waren drei Stellen im
"Wie funktioniert diese Demo?"-Expander (app.py): die Einleitung zur Inter-Batch-Suche, zu
Iterated Local Search und zum CP-SAT-Solver. Alle drei umformuliert, ohne Informationsverlust -
die Entwicklungshistorie ("wieso wurde das gebaut") bleibt weiterhin in den Modul-Docstrings
(`batch_local_search.py` etc.) und im README erhalten, wo sie hingehört; nur die dem Endnutzer
zugewandten Texte beschreiben jetzt direkt WAS die Funktion tut, nicht WARUM sie ins Backlog kam.
Die beiden Vorkommen im app.py-Modul-Docstring (nicht user-sichtbar, da nie gerendert) blieben
bewusst unverändert.

Beim Umformulieren selbst noch einen Zeilenumbruch-Fehler produziert (derselbe Fehlertyp wie beim
Einleitungstext oben, diesmal an zwei Stellen: "Inter-Batch-\nSuche" und "Greedy-Seed/\nZonen-Sweep"
wären als "Inter-Batch- Suche" bzw. "Greedy-Seed/ Zonen-Sweep" mit überflüssigem Leerzeichen
gerendert worden) - beide vor dem Testen bemerkt und behoben, live im Browser bestätigt (kein
"Nutzeranfrage" mehr im Expander, keine der beiden Leerzeichen-Varianten im gerenderten Text).

## Bugfix: Literaturverweis behauptete falsches Gründungsjahr des Order-Batching-Problems

Auf Nutzerfrage ("Sind die Literaturverweise korrekt? Grundproblem von 2005 klingt merkwürdig")
alle Zitate in App-Texten und Code-Kommentaren per Web-Recherche gegen die tatsächlichen
Publikationen geprüft. Der Verdacht bestätigte sich für genau eine Stelle: Der "Wie funktioniert
diese Demo?"-Expander (app.py) behauptete "Das Grundproblem geht auf Gademann & van de Velde
(2005) zurück" - das Order Batching Problem als Forschungsfeld ist aber deutlich älter. Früheste
identifizierte Arbeit: Elsayed, E.A. (1981), "Algorithms for Optimal Material Handling in
Automatic Warehousing Systems", *International Journal of Production Research* 19(5), 525-535,
gefolgt von Elsayed & Stern (1983) und Gibson & Sharp (1992), "Order Batching Procedures",
*European Journal of Operational Research*. Gademann & van de Velde (2005) ist ein reales, korrekt
zitiertes Paper - aber eine spätere Arbeit zu einem spezifischen Modell (paralleles Gang-Layout,
Laufzeit-Minimierung), nicht die Begründung des Forschungsfelds. Genau dieses spezifische Modell
folgt tatsächlich Gademann & van de Velde, das bleibt an den anderen Stellen (`batch_construction.py`-
Docstring, README-Einleitung) unverändert korrekt attribuiert - nur die "Grundproblem geht zurück
auf..."-Formulierung im App-Text war falsch.

**Fix:** Text umformuliert auf "Das Grundproblem geht auf frühe Arbeiten wie Elsayed (1981) zurück
[...]; das hier verwendete Modell [...] folgt insbesondere Gademann & van de Velde (2005)" - beide
Zitate bleiben erhalten, aber jedes an der fachlich zutreffenden Stelle.

**Die übrigen Zitate wurden ebenfalls stichprobenartig gegen echte Publikationen geprüft** (Autoren,
Jahr, Titel, Journal) und für korrekt befunden: Won & Olafsson (2005), "Joint order batching and
order picking in warehouse operations", *Int. J. Prod. Res.* 43(7); Ratliff & Rosenthal (1983),
"Order-Picking in a Rectangular Warehouse...", *Operations Research* 31(3); Roodbergen & de Koster
(2001a/b) zu S-Shape/Return/Largest-Gap- und Zwei-Block-Routing; Bentley (1992), "Fast Algorithms
for Geometric Traveling Salesman Problems" (Don't-Look-Bits); Auer, Cesa-Bianchi & Fischer (2002),
"Finite-time Analysis of the Multiarmed Bandit Problem" (UCB1); Lourenço, Martin & Stützle (2003),
"Iterated Local Search" im *Handbook of Metaheuristics*.

## UX: Personalkosten-Regler ohne Kontext, warum der Wert höher als ein Stundenlohn liegt

Auf Nutzerfrage ("Prüf bitte auch die restlichen Zahlen in der App auf Plausibilität") die übrigen
Default-Werte (nicht die bereits geprüften Algorithmus-Prozentzahlen/Zitate) gegen reale Quellen
geprüft: Gehgeschwindigkeit (1,3 m/s, Fachliteratur nennt 1,0-1,4 m/s für Fußkommissionierer),
Pickzeit (18s, plausibel innerhalb der stark streuenden dokumentierten Bandbreite) und der
Farbfehlsichtigkeits-Kommentar in `batch_constants.py` (~8% der Männer - korrekt für die hier
relevante nord-/westeuropäische Population) waren alle unauffällig.

Eine Stelle war zwar rechnerisch plausibel, aber im UI ohne jeden Kontext: **Personalkosten
28 €/h.** Der reine Bruttolohn für Lagerarbeiter/Kommissionierer liegt 2025 in Deutschland bei ca.
13,68-16 €/h - 28 €/h wirkt isoliert deutlich zu hoch. Rechnet man aber mit dem üblichen deutschen
Vollkostensatz (Lohnnebenkosten ~20% plus Gemeinkosten-Aufschlag, in Summe eine gängige Faustregel
von ca. dem 1,8-fachen des Bruttolohns), ergibt sich ca. 15 €/h × 1,8 ≈ 27 €/h - der Default ist
also korrekt, aber nur unter dieser (bislang nirgends erklärten) Interpretation als voll beladener
Kostensatz statt Bruttolohn. Anders als alle anderen Regler in diesem Abschnitt hatte
"Personalkosten (€/h)" bislang gar keinen Hilfetext.

**Fix:** Hilfetext ergänzt: "Vollkostensatz je Arbeitsstunde (Bruttolohn plus Lohnnebenkosten und
anteilige Gemeinkosten), nicht der reine Bruttolohn - deshalb liegt der Wert deutlich über einem
typischen Stundenlohn für Lagerpersonal." 99/99 Tests weiterhin grün (reiner Text-Zusatz), live im
Browser bestätigt (Tooltip rendert korrekt, keine Server-Fehler, Standardszenario weiterhin bei den
goldenen 883 m).

## Archiv: CP-SAT-Vergleichslöser und -Politur (entfernt)

Auf Nutzerhinweis ("für eine Demo scheint mir das schon ein ziemlicher algorithmischer Overkill zu
sein") entfernt: der CP-SAT-Vergleichslöser (Tab "🧮 Exakter Solver") und die optionale CP-SAT-
Politur (Button "🎯 Touren exakt nachschärfen"). Beide waren zusätzliche Komplexität ohne
Kernnutzen für eine Demo - die eigentliche Aussage der App (Batching + verschachtelte Lokalsuche +
Iterated Local Search bringt den Löwenanteil des Gewinns) steht auch ohne sie. Entfernt: das
komplette Modul `batch_ortools_solver.py`, die CP-SAT-Tab-/Politur-UI in `app.py` und
`batch_ui_panel.py`, die zugehörigen Konstanten (`CPSAT_*`) und der gemeinsame Cooldown-Helfer
(`cooldown_seconds_remaining`/`cooldown_record`, ausschließlich von diesen beiden Features
genutzt), 17 Tests, sowie die `ortools`-Abhängigkeit aus `requirements.txt`. 82 der bisherigen 99
Tests bleiben grün. Live im Browser bestätigt: keine CP-SAT-Reste in Tabs oder Erklärtexten, die
verbliebenen zwei Strategie-Tabs plus Vergleich funktionieren unverändert, Standardszenario weiter
bei den goldenen 883 m.

Komprimierte Historie beider Features, bevor sie entfernt wurden (Details standen zuvor in zwei
eigenen README-Abschnitten sowie einem dedizierten Bugfix-Abschnitt):

**Vergleichslöser:** Ursprünglich mit der OR-Tools-Routing-Bibliothek versucht (dieselbe, die die
Tourenplanung-Demo nutzt) - scheiterte an zwei Problemen: Standard-Konstruktionsheuristiken
ignorierten die nötige "gleiches Fahrzeug je Bestellung"-Nebenbedingung (`ROUTING_INVALID`), und ein
Workaround über `AddPickupAndDelivery` stürzte bei größeren Instanzen mit der Heuristik
`PATH_CHEAPEST_ARC` reproduzierbar mit einem echten Segfault ab - inakzeptabel für eine öffentliche
Demo. Ersetzt durch Google CP-SAT (allgemeiner Constraint-Solver statt Routing-Bibliothek):
Zuordnung + Hamiltonkreis je Batch-Slot in einem Modell, traf das Optimum in allen 12
Referenzinstanzen mit bekanntem Ergebnis, kein Absturz in allen Stresstests. Ehrlicher Nebenbefund:
bei realistischen Instanzgrößen war die eigene Heuristik nur ca. 1,7% hinter CP-SAT - exakte
Verfahren sind bei NP-harten Problemen jenseits einer gewissen Größe nicht automatisch besser als
gute Heuristiken, wenn die Zeit zum Beweisen der Optimalität fehlt.

**Politur:** Zunächst gemessen, wie groß die tatsächliche 2-opt-Optimalitätslücke für dieses
Lagermodell überhaupt ist (klein: 0-2% je nach Batch-Größe). Ein passender exakter Algorithmus in
Polynomialzeit existiert in der Literatur (Ratliff & Rosenthal 1983, später von Roodbergen & de
Koster auf Zwei-Block-Lager erweitert), ließ sich aber nicht sicher genug nachbauen (die kritische
Zustands-Übergangstabelle des Originalpapers war trotz mehrerer Recherche-Runden nicht zuverlässig
extrahierbar, keine verifizierbare Referenzimplementierung auffindbar) - das Risiko eines stillen
Korrektheitsfehlers war zu hoch. Held-Karp (der klassische exakte TSP-DP-Algorithmus) wurde
ebenfalls geprüft, skaliert aber ab n≈12 exponentiell und war für die hier vorkommenden Batch-Größen
(bis n=60) ungeeignet. Stattdessen wurde die bereits vorhandene CP-SAT-Infrastruktur für einzelne,
bereits feststehende Batches wiederverwendet (n=40 in <0,4s je Batch). Gemessener Nutzen: im Schnitt
unter 1% kürzere Routen, meist bestätigte die Politur nur, dass die Heuristik bereits optimal war.

**Ein Cache-Key-Bug** (fehlende `aisle_spacing`/`aisle_length`/`aisles`/`positions` in den
Gültigkeits-Keys beider Features) hatte zwischenzeitlich dazu geführt, dass ein gecachtes CP-SAT-
Ergebnis nach einer Eingabeänderung fälschlich als "gültig" angezeigt wurde - identifiziert per
`/code-review`, in zwei Runden vollständig behoben. Mit der Entfernung beider Features ist auch
diese Fehlerklasse hinfällig.

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

- Mehrfach-Umschichtungen (3+ Bestellungen zwischen mehreren Batches gleichzeitig) als weitere
  Nachbarschaft der Inter-Batch-Suche (siehe "Bewusst nicht enthalten" oben).
- Kombinierte Kapazität (Positionen UND Volumen gleichzeitig als harte Grenzen, statt nur einer
  umschaltbaren Kapazitätsart) sowie eine dritte Kapazitätsart nach Gewicht.
- Mehrere Kommissionierer gleichzeitig mit Wegekonflikten (verwandt mit dem Multi-Vehicle-Fall
  der Tourenplanung-Demo, nur mit fester statt freier Tourzuteilung).
- Kommissionierwellen mit Zeitfenstern (Bestellung muss bis Uhrzeit X versandfertig sein).

**Zwei Punkte dieser Liste sind inzwischen nicht mehr offen** (ursprünglich hier als Ideen gelistet,
dann tatsächlich benchmarkt): Relocate/Swap und 2-opt zu einer verschachtelten Suche zu verzahnen
ist **umgesetzt** (siehe "Benchmark: Zuteilung und Routing verschachtelt..." oben). Eine
vollständige Metaheuristik (Simulated Annealing, Tabu Search) statt Iterated Local Search wurde
dagegen explizit getestet und **verworfen** - schnitt durchweg schlechter ab als die aktuelle
ILS+Don't-Look-Bits-Kombination, Tabu Search sogar deutlicher und selbst bei einem
verzehnfachten Zeitbudget noch schlechter (siehe "Benchmark: vierzehn Metaheuristik-Varianten
geprüft" oben für alle 14 getesteten Varianten inkl. ALNS).
---

Teil des [Operations-Research-Demo-Portfolios](https://sebastianhanisch.net/demos.html) von [Sebastian Hanisch](https://sebastianhanisch.net) — Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html).
