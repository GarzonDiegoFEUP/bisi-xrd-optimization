"""Project paths and shared analysis/optimization defaults."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT_ROOT / "xrd_bo_optimization_tf"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
DOCS_DIR = PROJECT_ROOT / "docs"

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
REFERENCES_DIR = DATA_DIR / "references"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
RESULTS_DATA_DIR = DATA_DIR / "results"
NOMAD_VOLUME_DIR = PROJECT_ROOT / ".volumes" / "fs" / "staging" / "bisi"
# Local staging area for archives downloaded from the NOMAD REST API.
NOMAD_STAGING_DIR = RAW_DATA_DIR / "bisi_nomad_staging"
# Complete synthesis database extracted from the NOMAD API.
NOMAD_SYNTHESIS_CSV = PROCESSED_DATA_DIR / "bisi_synthesis_database_nomad.csv"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
REPORTS_DIR = OUTPUTS_DIR / "reports"

PHASE_PURITY_WEIGHT = 0.7
CRYSTALLINITY_WEIGHT = 0.3
UNASSIGNED_AREA_PENALTY_LAMBDA = 0.25
UNASSIGNED_AREA_DIAGNOSTICS_CSV = (
    RESULTS_DATA_DIR / "bisi_xrd_peak_area_diagnostics.csv"
)

# Reference intensities use the percentage scale shown on the ICDD cards.
REF_MIN_INTENSITY = 10.0
# Peak matching tolerance and minimum accepted width are in degrees 2-theta.
MATCH_TOL = 0.15
MIN_FWHM = 0.1
MAX_CANDIDATE_PEAKS = 30

TARGET_PHASE = "BiSI"
IMPURITY_PHASES = ("BiOI", "Bi2O3", "Bi2S3", "BiI3")
PHASES = (TARGET_PHASE, *IMPURITY_PHASES)

REFERENCE_CARD_FILES = {
    "BiSI": "01-088-884 Bi S I.rtf",
    "BiOI": "01-073-2062 Bi O I.rtf",
    "Bi2O3": "01-091-8160 Bi2O3.rtf",
    "Bi2S3": "96-152-1541 Bi2S3.rtf",
    "BiI3": "96-810-4288 BiI3.rtf",
}

SYNTHESIS_CSV = PROCESSED_DATA_DIR / "bisi_synthesis_database.csv"
XRD_METRICS_CSV = PROCESSED_DATA_DIR / "bisi_xrd_analysis_metrics.csv"
BO_SUGGESTIONS_CSV = PROCESSED_DATA_DIR / "bisi_bo_suggestions.csv"
GENERATED_XRD_METRICS_CSV = RESULTS_DATA_DIR / "bisi_xrd_analysis_metrics.csv"

BO_PARAMETER_COLUMNS = (
    "hard_bake_temp_c",
    "bismuth_concentration_mol_l",
    "s_to_bi_molar_ratio",
    "i_to_bi_molar_ratio",
)
XRD_PARAMETER_COLUMNS = (
    "spin_speed_rpm",
    "soft_bake_temp_c",
    "hard_bake_temp_c",
    "bismuth_concentration_mol_l",
    "s_to_bi_molar_ratio",
    "i_to_bi_molar_ratio",
)

# Leave composition dimensions categorical over measured recipes until a wider
# validated experimental range is established.
BO_PARAMETER_GRID_SPECS = {
    "hard_bake_temp_c": (150.0, 350.0, 10.0, 0),
}

SE_PULSE_DUTY_CYCLE_COLUMN = "se_pulse_duty_cycle"
SE_PULSE_PERIOD_MS = 3200
SE_PULSE_FREQUENCY_HZ = 1000.0 / SE_PULSE_PERIOD_MS
SE_PULSE_ON_MS_BOUNDS = (300, 1000)
SE_PULSE_DUTY_CYCLE_BOUNDS = tuple(
    on_ms / SE_PULSE_PERIOD_MS for on_ms in SE_PULSE_ON_MS_BOUNDS
)
