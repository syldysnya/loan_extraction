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
