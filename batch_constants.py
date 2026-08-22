"""
Zentrale Konstanten für die Order-Batching-Demo. Ausgelagert, damit sowohl
app.py als auch alle Logik-Module (batch_*.py) und die Testsuite dieselben
Werte nutzen, ohne Streamlit importieren zu müssen - dasselbe Muster wie in
den anderen Demos (siehe z. B. vrp_constants.py).
"""

# Okabe/Ito (2008) - eine der Standard-Paletten für farbfehlsichtige
# Nutzer (Rot-Grün-Schwäche betrifft ~8% der Männer): jede Farbe bleibt
# auch bei Deuteranopie/Protanopie von den anderen unterscheidbar, anders
# als die ursprüngliche Palette (Rot #dc2626 direkt neben Grün #16a34a lag
# zu nah beieinander). Schwarz aus dem Original-Set ersetzt durch ein Braun,
# da die Packstation (DEPOT_COLOR) bereits fast schwarz ist. Bei mehr
# Batches als Farben (auf Nutzeranfrage geprüft, u. a. das
# "Heterogene Artikelgrößen"-Szenario mit 15 Batches) wiederholt sich die
# Farbe zwar, aber build_warehouse_overview_figure/build_batch_detail_figure
# wechseln dann zusätzlich das Marker-Symbol (siehe BATCH_MARKER_SYMBOLS) -
# beides zusammen bleibt bis zu len(BATCH_COLORS)*len(BATCH_MARKER_SYMBOLS)
# Batches eindeutig unterscheidbar.
BATCH_COLORS = ["#0072B2", "#D55E00", "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#F0E442", "#8B4513"]
BATCH_MARKER_SYMBOLS = ["circle", "square", "diamond", "triangle-up", "x", "cross", "pentagon", "hexagon"]
AISLE_COLOR = "#d1d5db"
CROSS_AISLE_COLOR = "#9ca3af"
DEPOT_COLOR = "#111827"
EPS = 1e-9

DEFAULT_N_ORDERS = 24
DEFAULT_ITEMS_MIN = 2
DEFAULT_ITEMS_MAX = 6
DEFAULT_N_AISLES = 8
DEFAULT_AISLE_LENGTH = 30.0
DEFAULT_AISLE_SPACING = 3.0
DEFAULT_BATCH_CAPACITY = 15

# Kapazitätsart: "Positionen" (jede Position zählt 1, das bisherige, in der
# Batching-Literatur übliche Modell) oder "Volumen (l)" (Positionen haben
# unterschiedliches Volumen, realistischer bei sehr heterogenen Artikel-
# größen, z. B. Grocery/General-Merchandise-Sortimenten - auf Nutzeranfrage
# als zweiter, umschaltbarer Modus ergänzt statt den bisherigen zu ersetzen,
# da "Positionen" für gleichförmige Sortimente weiterhin die einfachere,
# realistische Vereinfachung ist).
CAPACITY_MODE_POSITIONS = "Positionen"
CAPACITY_MODE_VOLUME = "Volumen (l)"
DEFAULT_ITEM_VOLUME_MIN = 1.0
DEFAULT_ITEM_VOLUME_MAX = 4.0
DEFAULT_BATCH_CAPACITY_VOLUME = 40.0

# Kommissionier-Kennzahlen: Richtwerte für einen Handkommissionierer im
# Lager mit Kommissionierwagen (kein Routenzug/automatisiertes System).
DEFAULT_WALKING_SPEED_MPS = 1.3
DEFAULT_PICK_TIME_S = 18.0
DEFAULT_COST_PER_HOUR = 28.0

LOCAL_SEARCH_MAX_MOVES = 200

# Iterated Local Search (Perturbation + Re-Optimierung) obendrauf auf die
# Inter-Batch-Suche: auf Nutzeranfrage benchmarkt und ergänzt (durchweg
# 1-4,8% kürzere Distanz auf realistischen Instanzgrößen, siehe README).
# ILS_TIME_BUDGET_S begrenzt statt einer festen Neustart-Zahl bewusst die
# ZEIT: bei kleinen Instanzen passen so viele Dutzend Neustarts in das
# Budget, bei sehr großen (teure Einzelsuche) nur wenige oder gar keiner -
# das Budget skaliert sich dadurch automatisch mit der Instanzgröße, ohne
# das ohnehin schon dokumentierte Extremfall-Risiko (siehe README) zu
# verschärfen. ILS_MAX_RESTARTS ist nur ein zusätzliches Sicherheitsnetz für
# sehr kleine, sehr schnelle Instanzen (verhindert unnötig viele Neustarts,
# wenn das Zeitbudget dort ohnehin nie ausgeschöpft würde).
ILS_TIME_BUDGET_S = 1.5
ILS_MAX_RESTARTS = 40
ILS_PERTURB_STRENGTH = 2

# UCB1 (Auer et al. 2002, klassische Bandit-Explorationsstrategie aus dem
# RL-Bereich, auf Nutzeranfrage ergänzt): die Ziel-Batch-Wahl in
# perturb_batches ist nicht mehr gleichverteilt zufällig, sondern gewichtet
# nach Erfolgsrate PLUS einem expliziten Unsicherheits-Bonus für wenig
# ausprobierte (Bestellung, Ziel-Batch)-Paare - anders als die zuvor
# verworfene reine Erfolgs-Verstärkung (Pheromon-Zielwahl) verhindert der
# Bonus strukturell, dass sich die Auswahl auf wenige "bewährte" Ziele
# einpendelt. UCB_EXPLORATION_C=1.4 (~sqrt(2)) ist die in der Literatur für
# binäre [0,1]-Belohnungen übliche Konstante, siehe README-Benchmark.
UCB_EXPLORATION_C = 1.4

# CP-SAT-Vergleichslöser (batch_ortools_solver.py): auf Nutzeranfrage
# ergänzt, um kleine Instanzen exakt (oder nahe-exakt) lösen und mit den
# eigenen Heuristiken vergleichen zu können. CPSAT_MAX_MODEL_SIZE begrenzt
# num_batches * (n_items+1)^2 (ungefähre Anzahl Bogen-Variablen des
# CP-SAT-Modells) - empirisch ermittelt: darüber dauert schon der reine
# Modellaufbau (nicht die Lösungssuche selbst, die durch das Zeitlimit
# gedeckelt ist) mehrere Sekunden bis Minuten, siehe README.
CPSAT_MAX_TIME_LIMIT = 20
CPSAT_COOLDOWN_BUFFER = 5
CPSAT_MAX_MODEL_SIZE = 100_000

FEEDBACK_FILE = "feedback_log.csv"
