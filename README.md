# BiSI Thin-Film Synthesis Data

This repository is being migrated from BaCuSe to BiSI. The current migration
stage extracts synthesis records from configured BiSI NOMAD upload IDs and
writes them to `data/processed/bisi_synthesis_database_nomad.csv`. Notebook 1
uses the existing archive-based extraction and fallback pattern, with isolated
BiSI staging and output paths.

Only synthesis extraction is active in this migration pass. The existing XRD
phase-matching, CIF/RTF references, metrics, and Bayesian-optimization results
are historical BaCuSe artifacts and must not be used to analyze BiSI. The BiSI
CIF/RTF files and phase configuration need to be updated before running the
XRD or optimization notebooks.

## Repository structure

- `xrd_bo_optimization_tf/` — NOMAD archive access, synthesis extraction, and
  the legacy XRD/optimization modules.
- `notebooks/` — Run only `1. synthesis_parameters_extraction.ipynb` for the
  current BiSI migration. Notebooks 2–4 still contain the prior BaCuSe XRD and
  optimization workflow and are intentionally not run.
- `data/processed/bisi_upload_ids.txt` — BiSI NOMAD upload IDs, one per line.
- `data/processed/bisi_synthesis_database_nomad.csv` — extracted BiSI records.
- `data/raw/bisi_nomad_staging/` — gitignored archive cache downloaded by
  notebook 1.
- BaCuSe tables, reference cards, reports, and figures are retained as
  historical data; they are not BiSI results.

## Environment setup

Create a virtual environment and install the pinned dependencies:

```bash
python3.12 -m venv xrd_bo_env
source xrd_bo_env/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Select the environment as the notebook kernel.

## NOMAD access

Create a personal access token in the Oasis GUI (Profile → Settings → Tokens,
READ ONLY scopes), copy `.env.example` to `.env`, and set the token:

```text
NOMAD_API_URL="https://nomad-sadewasser.inl.local/nomad-oasis/api/v1"
NOMAD_PAT="paste-your-token-here"
NOMAD_VERIFY_SSL="0"
```

`.env` is gitignored and must not be committed. BiSI uploads are routed by ID
because entry search by composition is not reliable for these ELN records.
Notebook 1 selects `INLThinFilmStack` samples and writes the synthesis table;
this migration pass does not fetch or analyze XRD patterns.

## Data and reference materials

Check the terms governing NOMAD data and ICDD reference-card materials before
redistributing them. Replace the legacy phase references with BiSI target and
impurity CIF/RTF files before resuming XRD analysis.
