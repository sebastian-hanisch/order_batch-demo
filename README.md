# 🧺 Order Batching (Kommissionier-Batchbildung)

Interaktive Demo zum Order-Batching-Problem: Kundenbestellungen werden zu Kommissionier-Batches gruppiert, die je ein Kommissionierer in einer einzigen Tour durchs Lager abarbeitet.

**[→ Demo live ausprobieren](https://sebastianhanisch-orderbatch-demo.streamlit.app/)**

## Worum geht's?

Ziel ist es, die gesamte Laufdistanz zu minimieren, ohne die Zahl der zu kommissionierenden Positionen zu verändern — jede Position wird so oder so genau einmal gepickt, nur wie viele Depot-Rundwege und Gangwechsel dafür nötig sind, hängt von der Gruppierung ab.

## Methodik

- Zwei selbst implementierte Batching-Strategien im Vergleich: **Greedy-Seed** (klassisches Seed-Verfahren) und **Zonen-Sweep** (sortiert nach Gang-Schwerpunkt, analog zum Sweep-Algorithmus der Tourenplanung-Demo)
- Je Batch eine unabhängig optimierte Kommissionierroute: Nearest-Neighbor-Konstruktion + 2-opt-Verbesserung
- Zusätzlich eine Inter-Batch-Lokalsuche plus Iterated Local Search, die einen Großteil des Abstands zum Optimum schließt, den 2-opt allein offen lässt
- Zwei umschaltbare Kapazitätsarten (max. Positionen oder max. Volumen je Batch), Geschäftskennzahlen (Kommissionierzeit, Personalkosten, Durchsatz), PDF-Export, Permalink

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `pytest tests/ -v`

---

Teil des [Operations-Research-Demo-Portfolios](https://sebastianhanisch.net/demos.html) von [Sebastian Hanisch](https://sebastianhanisch.net) — Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html).
