# Loan Document Extraction

An unstructured data extraction system for a provided corpus of loan documents.

## Problem

The corpus contains documents with variable formatting, mixed file types, and structured data embedded within unstructured text. The system extracts meaningful, structured data from these documents.

## Goal

Produce a structured record for each borrower that includes:

- Extracted PII, such as name and address
- Full income history
- Associated account and loan numbers
- A clear reference to the original document(s) the information came from

## Components

- **Document ingestion pipeline**
- **Extraction logic** using AI/LLM tooling
- **Query or retrieval interface**, such as an API, to serve the processed data
- **Tests** for critical paths

## Deliverables

A design document and this README, along with the other deliverables listed on the cover page.

## Run locally

### Prerequisites

- Python 3.12 and [Hatch](https://hatch.pypa.io/)
- Tesseract, for OCR of scanned pages (macOS: `brew install tesseract`, Debian/Ubuntu: `apt install tesseract-ocr`)
- A Gemini API key (or an OpenAI key, to run with `model=openai`)

The worker reads the key from the `GOOGLE_API_KEY` (or `OPENAI_API_KEY`) environment variable. Keys are never written in code, config or `.env` files in the repo. Keep the key in a secret store (a password manager or the OS keychain) and export it in the terminal that runs the worker:

```bash
export GOOGLE_API_KEY=<your key>
```

In production, the key lives in a secret manager (e.g. AWS Secrets Manager) and is injected into the worker's environment at runtime.

### Steps

Put the corpus in `data/loan_data/`, then:

```bash
hatch run ingest folder=data/loan_data   # register the documents, upload them to s3/ and queue them
hatch run document-worker                # parse and extract each document; stop with Ctrl+C when the queue is empty
hatch run api                            # serve the results on http://127.0.0.1:8000
```

```bash
curl http://127.0.0.1:8000/borrowers                 # every borrower
curl http://127.0.0.1:8000/borrowers/<borrower_id>   # one borrower's full record, with sources
```

Interactive API docs: http://127.0.0.1:8000/docs

### Other commands

```bash
hatch run document-worker model=openai   # extract with GPT-4o mini instead of Gemini
hatch run redrive [batch_id=<id>]        # move failed (DLQ) messages back to the queue
hatch run resolve                        # rebuild the borrower records from the stored extractions
hatch run costs [batch_id=<id>]          # LLM calls, tokens and cost per model
hatch run test
hatch run lint
```

Local state: `loan.db` (SQLite), `s3/` (files and page images), `queue/` (queue and DLQ), `log/` (logs per run).
