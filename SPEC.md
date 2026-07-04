# Emploi — Specification Document

**Version:** 1.0
**Date:** July 04, 2026
**Built with:** Streamlit + Google Gemini
**Goal:** A single, easy-to-use web app that combines curated job lists with AI-powered application tailoring.

## 1. Overview

Emploi is an all-in-one personal job application assistant. It merges manual/curated job lists (e.g. Halo-style Google Sheets), professional profile management, AI-powered job analysis and tailoring (Gemini), and application tracking.

**Target users:** anyone looking for jobs — fresh graduates, career switchers, remote workers. Simple enough for non-technical users.

## 2. Core Features

### 2.1 Profile Management
- Fields: Name, Title, Location/Remote Preference, Experience, Skills, Education, Career Goals
- Persistent in Streamlit session state
- Rich text areas for detailed input (more detail → better AI output)

### 2.2 Job List Import
- Upload CSV or Excel files (compatible with curated sheets)
- Preview table; jobs stored in session for reference

### 2.3 AI Application Generator (core)
- Paste full job description + optional company name
- Uses Google Gemini (model selectable; default `gemini-2.5-flash`)
- Outputs: 1-page cover letter, 6–8 tailored CV bullets, fit score (0–100) with explanation
- Human, keyword-optimized, non-fabricated content
- PDF and text download of generated output

### 2.4 Application Tracker
- Logs every generated application: Date, Company, Status, Notes
- DataFrame view + CSV export

### 2.5 Settings
- Gemini API key input (password field, or `GEMINI_API_KEY` env var)
- Model selector, clear-all-data button, status indicators

## 3. Technical Stack

- **Frontend:** Streamlit (Python)
- **AI:** Google Gemini API (`google-generativeai`)
- **Data:** pandas, openpyxl
- **Export:** fpdf2 (PDF), CSV
- **Storage:** in-memory session state (v1); future: local JSON / SQLite

## 4. File Structure

```
emploi/
├── app.py            # entire app (single file, v1)
├── requirements.txt
├── README.md
└── SPEC.md
```

## 5. Roadmap

- Persistent storage (JSON/SQLite)
- Auto-import jobs from curated posts
- Batch generation across an imported job list
- Formatted DOCX/PDF CV output
