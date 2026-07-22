# Translayer (v0.2.1)

[English](README.md) | [简体中文](README.zh-CN.md) | Deutsch

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-active%20development-orange.svg)](#)

**Beliebige Formate hinein, beliebige Sprachen heraus – Layout, Satz und Bildtext bleiben möglichst erhalten.**

Translayer ist eine KI-native Zwischenschicht für die Dokumentlokalisierung. PPTX-, DOCX- und HTML-Dateien werden in ein einheitliches `DocumentIR` überführt, mit Layout-, Terminologie- und OCR-Daten angereichert, in einem überprüfbaren Workflow lokalisiert und anschließend in das ursprüngliche Format zurückgeschrieben. Neben normalem Dokumenttext kann Translayer auch Text in Bildern erkennen und bearbeiten.

## Hauptfunktionen

- Parser und Renderer für PPTX, DOCX und HTML.
- Englisch, vereinfachtes Chinesisch und Deutsch als Quell- und Zielsprachen.
- Präzises Zurückschreiben anhand von Seiten-, Form-, Absatz- und Tabellenkoordinaten.
- Unterstützung für PPTX-SmartArt, Tabellen, gruppierte Formen und Bildressourcen.
- Lokale Bildprüfung mit Tesseract zur Vermeidung unnötiger kostenpflichtiger Aufrufe.
- OCR, lokales Entfernen von Text und Neuzeichnen mit zielsprachlichen Schriftarten.
- Gemini-Ganzbildlokalisierung mit OCR-Qualitätsprüfung vor und nach der Generierung.
- Manuelle Bildfreigabe, Kostenschätzung und verbindliches Budgetlimit.
- Beliebige OpenAI-kompatible Chat-Completions-Endpunkte, einschließlich lokaler und interner APIs.
- DeepL Free und Pro.
- Auftragsbezogene Zugangsdaten für OpenAI-kompatible APIs, DeepL und Gemini.

## Ablauf

```text
Eingabedokument
  → DocumentIR erzeugen
  → Semantik, Terminologie, Layout und Bild-OCR anreichern
  → normalen Text übersetzen
  → Bilder lokal prüfen und manuell freigeben
  → Bereiche neu zeichnen oder ganzes Bild mit Gemini bearbeiten
  → Ergebnis per OCR validieren
  → in das Zielformat zurückschreiben
```

Bilder werden einer der folgenden Routen zugeordnet:

- `skip`: Dekoration, Symbol oder Bild ohne relevanten Text bleibt unverändert.
- `reuse`: Das Ergebnis eines identischen Bildes wird wiederverwendet.
- `region`: Erkannte Textbereiche werden entfernt und lokal neu gezeichnet.
- `whole_image`: Das ganze Bild wird mit Gemini bearbeitet.
- `review`: Der Benutzer entscheidet bei unsicherer Erkennung.

## Installation

Erforderlich ist Python 3.11 oder neuer. Für Bildprüfung und Seitenvorschau werden LibreOffice, Poppler, Tesseract und die benötigten Sprachpakete empfohlen.

macOS:

```bash
brew install libreoffice poppler tesseract tesseract-lang
```

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y \
  libreoffice poppler-utils \
  tesseract-ocr tesseract-ocr-eng \
  tesseract-ocr-chi-sim tesseract-ocr-deu
```

Python-Paket installieren:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Für Gemini-Aufrufe:

```bash
uv pip install -e ".[gemini]"
```

## Weboberfläche starten

```bash
translayer serve --host 127.0.0.1 --port 8000
```

Danach <http://127.0.0.1:8000> öffnen.

Beim Erstellen eines Auftrags stehen folgende Textübersetzer zur Verfügung:

1. **OpenAI-kompatible API**: Basis-URL, optionaler API-Schlüssel und Modellname. Bei lokalen APIs ohne Authentifizierung darf der Schlüssel leer bleiben.
2. **DeepL API**: DeepL-Schlüssel eingeben; anhand des Suffixes `:fx` wird automatisch Free oder Pro gewählt.
3. **Offline-Demo**: Keine externen Aufrufe, nur zur Prüfung des Workflows.

Der Gemini-API-Schlüssel ist optional und wird **nur benötigt, wenn Text in komplexen Bildern geändert werden soll**. Für normalen Dokumenttext ist kein Gemini-Schlüssel erforderlich. Enthält der freizugebende Plan Ganzbildbearbeitungen, fragt der Bestätigungsdialog erneut nach dem Schlüssel.

Die Oberfläche zeigt:

- die Anzahl der voraussichtlich zu ändernden Bilder;
- die erwartete Zahl kostenpflichtiger Aufrufe;
- den Planungswert pro Bild;
- die geschätzten Gesamtkosten;
- das vom Benutzer genehmigte Höchstbudget.

Die Werte dienen der sicheren Planung; maßgeblich ist die tatsächliche Abrechnung des Anbieters. Der Standardwert pro Aufruf wird mit `TRANSLAYER_IMAGE_ESTIMATED_COST_USD` konfiguriert.

## Kommandozeile

Dokument mit einem lokalen oder internen OpenAI-kompatiblen Modell übersetzen:

```bash
translayer translate input.pptx -o output.pptx \
  --from en \
  --to de \
  --engine openai \
  --api-url http://llm.internal:8000/v1 \
  --api-key optional-local-key \
  --model local-model \
  --ocr-engine tesseract
```

DeepL verwenden:

```bash
translayer translate input.pptx -o output.pptx \
  --from en \
  --to de \
  --engine deepl \
  --api-key YOUR_DEEPL_KEY
```

Lokalen Bild- und Kostenplan ohne API-Aufruf erzeugen:

```bash
translayer plan-images input.pptx -o cost-plan.json \
  --from en \
  --targets zh,de \
  --budget-usd 1.50
```

Ein einzelnes Bild lokalisieren:

```bash
translayer translate-image input.png -o output.png \
  --from en \
  --to de \
  --allow-paid-api \
  --max-cost-usd 0.10
```

## Konfiguration

Wichtige Umgebungsvariablen:

| Variable | Verwendung |
|---|---|
| `TRANSLAYER_TRANSLATION` | Standard-Textübersetzer |
| `OPENAI_API_KEY` | Standard-Schlüssel für OpenAI-kompatible APIs |
| `OPENAI_BASE_URL` | Standard-Basis-URL für OpenAI-kompatible APIs |
| `TRANSLAYER_OPENAI_MODEL` | Standard-Textmodell |
| `DEEPL_API_KEY` | Standard-DeepL-Schlüssel |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Standard-Gemini-Schlüssel |
| `TRANSLAYER_GEMINI_IMAGE_MODEL` | Standard-Gemini-Bildmodell |
| `TRANSLAYER_IMAGE_ESTIMATED_COST_USD` | Planungswert pro Bildaufruf |
| `TRANSLAYER_IMAGE_CACHE_DIR` | Cache für Gemini-Bilder |

Auftragsbezogene Werte aus der Weboberfläche haben Vorrang. Geheimnisse bleiben im Auftragsobjekt des laufenden Serverprozesses und werden weder in `DocumentIR` noch in öffentlichen API-Antworten gespeichert.

## Projektstruktur

```text
src/translayer/
├── api/             FastAPI, Auftragsstatus und Prüfschnittstellen
├── engines/         Übersetzung, OCR, Inpainting und Bildmodelle
├── enrich/          Semantik, Terminologie und Bildauswahl
├── ir/              DocumentIR-Modelle und JSON-Schema
├── localize/        Text-, Bild- und Qualitätspipelines
├── parsers/         PPTX-, DOCX- und HTML-Parser
├── renderers/       Rückschreiben in das Originalformat
└── web/             Einseitige Oberfläche auf Englisch, Chinesisch und Deutsch
```

Die Kernpipeline lautet:

```text
Parse → Enrich → Localize → Render
```

## Entwicklung und Tests

```bash
ruff check src/translayer tests
pytest -q
```

Externe Erweiterungen können über den Entry Point `translayer.plugins` zusätzliche Parser, Renderer, Übersetzer, OCR-, Inpainting- oder Bildlokalisierungs-Engines registrieren.

## Lizenz

Translayer steht unter der [Apache License 2.0](LICENSE).
