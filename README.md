# BiSI Thin-Film Synthesis Data

This project extracts BiSI synthesis records and XRD scans from configured
NOMAD uploads, identifies peaks against the current BiSI target and candidate
impurity references, and explores synthesis optimization. The workflow has
been run on six configured uploads: 41 synthesis records were extracted, 33
XRD scans were analyzed, and 25 complete observations entered the current
optimizer. BaCuSe data and outputs are retained only as historical material.

BiSI chemistry features are calculated from NOMAD solution solute formulas and
amounts: bismuth concentration plus atomic S:Bi and I:Bi ratios. Main coating
and seed-solution values are kept separately when available. They are distinct
precursor recipes and should not be conflated.

The XRD/optimization outputs are exploratory. Some scans have no detected
peaks or no exact metadata match for the optional Le Bail fit. The Le Bail
routine uses a Bragg–Brentano profile model as a proxy for GIXRD. Peak-purity
values depend on the selected reference cards and detection settings; the
unmatched/overlap-area penalty is a screening indicator, not a phase fraction.

## Repository structure

- `xrd_bo_optimization_tf/` — NOMAD archive access, synthesis extraction, and
  the legacy XRD/optimization modules.
- `notebooks/` — Run notebooks 1–4 in order for extraction, XRD analysis,
  single-objective optimization, and Ax multi-objective optimization.
- `data/processed/bisi_upload_ids.txt` — BiSI NOMAD upload IDs, one per line.
- `data/processed/bisi_synthesis_database_nomad.csv` — extracted BiSI records.
- `data/results/bisi_xrd_analysis_metrics.csv` — BiSI phase-matching metrics.
- `data/results/bisi_xrd_peak_area_diagnostics.csv` — screening diagnostics.
- `data/results/bisi_bo_suggestions.csv` and
  `data/results/bisi_ax_moo_suggestions.csv` — single- and multi-objective
  candidate tables.
- `data/raw/bisi_nomad_staging/` — gitignored archive cache downloaded by
  notebook 1.
- `outputs/figures/bisi_*.png` — generated BiSI plots.
- `outputs/rietx_lebail_bisi/` — optional qualitative Le Bail fits and
  diagnostics for scans with matching GIXRD archive metadata.
- `outputs/reports/bisi_xrd_bo_report.pdf` — generated BiSI summary report.
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
its BiSI staging directory is separate from the legacy BaCuSe cache.

## Run order and report

1. Run all cells in `notebooks/1. synthesis_parameters_extraction.ipynb`.
2. Run all cells in `notebooks/2.xrd_analysis.ipynb` to calculate metrics and
  generate plots and optional Le Bail diagnostics.
3. Run `notebooks/3.bo_xrd.ipynb` for weighted single-objective suggestions.
4. Run `notebooks/4.bo_xrd_ax.ipynb` for Pareto candidates.
5. Build the report from the latest BiSI result files using the project Python
  environment and `xrd_bo_optimization_tf.report.build_report()`.

The optimizer currently uses measured hard-bake values and observed levels of
Bi concentration, S:Bi, and I:Bi. Candidate chemistry values are therefore
restricted to measured levels; suggestions are exploratory rather than
validated recipes.

## Data and reference materials

Check the terms governing NOMAD data and ICDD reference-card materials before
redistributing them. Replace the legacy phase references with BiSI target and
impurity CIF/RTF files before resuming XRD analysis.
