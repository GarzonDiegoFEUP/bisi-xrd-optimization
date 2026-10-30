"""Generate a PDF report summarizing the XRD analysis and BO suggestions."""

from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .bayesian_opt import prepare_optimization_data
from .config import (
    BO_PARAMETER_COLUMNS,
    FIGURES_DIR,
    GENERATED_XRD_METRICS_CSV,
    NOMAD_SYNTHESIS_CSV,
    REPORTS_DIR,
    RESULTS_DATA_DIR,
    TARGET_PHASE,
    UNASSIGNED_AREA_DIAGNOSTICS_CSV,
    UNASSIGNED_AREA_PENALTY_LAMBDA,
)

PAGE_WIDTH, _ = A4
CONTENT_WIDTH = PAGE_WIDTH - 4 * cm


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SectionHead",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#1a3b5d"),
            spaceBefore=14,
            spaceAfter=6,
        )
    )
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=10, leading=14))
    styles.add(
        ParagraphStyle(
            name="TableHeaderSmall",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=8.5,
            alignment=1,
        )
    )
    return styles


def _figure(path: Path, width: float = CONTENT_WIDTH) -> Image | None:
    if not path.is_file():
        return None
    img = ImageReader(str(path))
    img_width, img_height = img.getSize()
    height = width * img_height / img_width
    return Image(str(path), width=width, height=height)


def _suggestions_table(suggestions: pd.DataFrame, parameter_columns) -> KeepTogether:
    """Build a styled table of suggested conditions."""
    styles = _styles()
    # Only show parameters actually present in this suggestions table.
    parameter_columns = [c for c in parameter_columns if c in suggestions.columns]
    cols = ["rank", *parameter_columns]
    cols.extend(
        column
        for column in ("se_pulse_on_ms", "se_pulse_off_ms")
        if column in suggestions.columns and column not in cols
    )
    has_std = "predicted_std" in suggestions.columns
    if "predicted_objective" in suggestions.columns:
        cols += ["predicted_objective"] + (["predicted_std"] if has_std else [])
    header_labels = {
        "rank": "#",
        "hard_bake_temp_c": "Hard bake<br/>°C",
        "bismuth_concentration_mol_l": "Bi concentration<br/>mol/L",
        "s_to_bi_molar_ratio": "S:Bi<br/>molar ratio",
        "i_to_bi_molar_ratio": "I:Bi<br/>molar ratio",
        "selenization_temp_c": "Process temp<br/>°C",
        "selenization_time_s": "Process time<br/>s",
        "predicted_objective": "Predicted<br/>score",
        "predicted_std": "GP<br/>std",
    }
    header = [
        Paragraph(header_labels.get(column, column.replace("_", " ")), styles["TableHeaderSmall"])
        for column in cols
    ]
    table_data = [header]
    for _, row in suggestions.iterrows():
        entry = []
        for column in cols:
            if column == "rank":
                entry.append(str(int(row[column])))
            elif pd.isna(row[column]):
                entry.append("—")
            elif column == "bismuth_concentration_mol_l":
                entry.append(f"{row[column]:.4f}")
            elif column in ("s_to_bi_molar_ratio", "i_to_bi_molar_ratio"):
                entry.append(f"{row[column]:.3f}")
            elif column in ("predicted_objective", "predicted_std"):
                entry.append(f"{row[column]:.3f}")
            elif column == "hard_bake_temp_c":
                entry.append(f"{row[column]:.0f}")
            elif pd.api.types.is_number(row[column]):
                entry.append(f"{row[column]:.3g}")
            else:
                entry.append(str(row[column]))
        table_data.append(entry)
    col_widths = {
        "rank": 22,
        "hard_bake_temp_c": 47,
        "bismuth_concentration_mol_l": 74,
        "s_to_bi_molar_ratio": 66,
        "i_to_bi_molar_ratio": 66,
        "selenization_temp_c": 48,
        "selenization_time_s": 48,
        "predicted_objective": 50,
        "predicted_std": 38,
    }
    table = Table(
        table_data,
        colWidths=[col_widths.get(column, 50) for column in cols],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3b5d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f8")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b0bec5")),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return KeepTogether([table])


def build_report(output_path: Path | None = None) -> Path:
    """Assemble the BiSI synthesis, XRD, and optimization report."""
    output_path = output_path or (REPORTS_DIR / "bisi_xrd_bo_report.pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    required_paths = (
        GENERATED_XRD_METRICS_CSV,
        NOMAD_SYNTHESIS_CSV,
        UNASSIGNED_AREA_DIAGNOSTICS_CSV,
        RESULTS_DATA_DIR / "bisi_bo_suggestions.csv",
    )
    missing_paths = [path for path in required_paths if not path.is_file()]
    if missing_paths:
        raise FileNotFoundError(
            "BiSI report inputs are missing: "
            + ", ".join(str(path) for path in missing_paths)
        )

    metrics = pd.read_csv(GENERATED_XRD_METRICS_CSV)
    synthesis = pd.read_csv(NOMAD_SYNTHESIS_CSV)
    diagnostics = pd.read_csv(UNASSIGNED_AREA_DIAGNOSTICS_CSV)
    df_bo = prepare_optimization_data(
        metrics,
        parameter_columns=BO_PARAMETER_COLUMNS,
        synthesis=synthesis,
        include_process=True,
        diagnostics=diagnostics,
        unassigned_area_penalty_lambda=UNASSIGNED_AREA_PENALTY_LAMBDA,
    )
    suggestions = pd.read_csv(RESULTS_DATA_DIR / "bisi_bo_suggestions.csv")
    if "penalty_lambda" not in suggestions or not suggestions["penalty_lambda"].eq(
        UNASSIGNED_AREA_PENALTY_LAMBDA
    ).all():
        raise ValueError(
            "Saved BiSI suggestions do not match the configured XRD penalty; rerun notebook 3's optimization cell."
        )

    styles = _styles()
    story = []

    story.append(Paragraph("BiSI Thin-Film XRD Analysis and Bayesian Optimization", styles["Title"]))
    story.append(Paragraph("NOMAD-driven extraction, phase screening, and exploratory synthesis planning", styles["Italic"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("1. Dataset and method", styles["SectionHead"]))
    main_coverage = int(synthesis["bismuth_concentration_mol_l"].notna().sum())
    seed_coverage = int(synthesis["seed_bismuth_concentration_mol_l"].notna().sum())
    le_bail_path = REPORTS_DIR.parent / "rietx_lebail_bisi" / "lebail_summary_all_samples.csv"
    le_bail_text = ""
    if le_bail_path.is_file():
        le_bail = pd.read_csv(le_bail_path)
        fit_count = int(le_bail["status"].eq("converged").sum()) if "status" in le_bail else 0
        skipped_count = int(le_bail["status"].eq("skipped_metadata").sum()) if "status" in le_bail else 0
        le_bail_text = (
            f" An optional Le Bail proxy converged for {fit_count} scans; "
            f"{skipped_count} scans lacked an exact matching GIXRD archive-array record."
        )
    summary = (
        f"The BiSI NOMAD extraction contains {len(synthesis)} thin-film records; "
        f"{main_coverage} have matched main-layer precursor chemistry and {seed_coverage} "
        f"have seed-solution chemistry. XRD analysis produced {len(metrics)} scan metric rows, "
        f"with {len(df_bo)} complete observations for the optimizer. The target phase is {TARGET_PHASE}; "
        "the configured candidate phases are BiOI, Bi2O3, Bi2S3, and BiI3. "
        f"Composition metrics are calculated from NOMAD solution solute formulas and amounts: "
        "Bi molar concentration and atomic S:Bi and I:Bi ratios. "
        "Crystallinity is the inverse FWHM of the strongest matched target peak. "
        f"{le_bail_text}"
    )
    story.append(Paragraph(summary, styles["BodySmall"]))
    story.append(Paragraph("2. XRD phase screening", styles["SectionHead"]))
    story.append(Paragraph(
        "Stacked BiSI XRD patterns per series with reference bars for the target and candidate phases. "
        "Markers flag target (star), impurity (square), and unmatched (triangle) peaks.",
        styles["BodySmall"],
    ))
    # The all-scan stack is tall; scale it down to stay within the A4 frame.
    all_scans = _figure(
        FIGURES_DIR / "bisi_xrd_all_samples.png", width=CONTENT_WIDTH * 0.58
    )
    if all_scans is not None:
        story.append(Spacer(1, 0.15 * cm))
        story.append(all_scans)
    for path in sorted(FIGURES_DIR.glob("bisi_xrd_series_*.png")):
        fig = _figure(path, width=CONTENT_WIDTH * 0.92)
        if fig is not None:
            story.append(Spacer(1, 0.15 * cm))
            story.append(fig)

    story.append(Paragraph("3. Observed results", styles["SectionHead"]))
    best = df_bo.loc[df_bo["objective"].idxmax()]
    results = (
        f"For the {len(df_bo)} complete observations, mean phase purity is "
        f"{df_bo['phase_purity'].mean():.3f} and mean crystallinity is "
        f"{df_bo['crystallinity'].mean():.3f}. The highest screening-adjusted score is "
        f"{best['objective']:.3f} for {best['sample_id']} (phase purity "
        f"{best['phase_purity']:.3f}, crystallinity {best['crystallinity']:.3f}, "
        f"unmatched/overlap area proxy A={best['unassigned_or_overlap_area_fraction']:.3f}). "
        "The score is an exploratory ranking metric, not a phase-fraction determination. "
        f"It uses (0.7 × phase purity + 0.3 × normalized crystallinity) × "
        f"(1 − {UNASSIGNED_AREA_PENALTY_LAMBDA:.2f} × A)."
    )
    story.append(Paragraph(results, styles["BodySmall"]))
    diagnostic_figure = _figure(FIGURES_DIR / "bisi_bo_parameter_plots.png")
    if diagnostic_figure is not None:
        story.append(Spacer(1, 0.15 * cm))
        story.append(diagnostic_figure)

    story.append(Paragraph("4. Single-objective candidate recipes", styles["SectionHead"]))
    story.append(Paragraph(
        "The Gaussian-process candidates use measured levels for the composition variables and a "
        "hard-bake grid spanning the observed conditions. Predictions are model estimates, not "
        "validated performance or ready-to-run recipes:",
        styles["BodySmall"],
    ))
    story.append(Spacer(1, 0.15 * cm))
    story.append(_suggestions_table(suggestions, df_bo.attrs["parameter_columns"]))

    story.append(Paragraph("5. Multi-objective candidates", styles["SectionHead"]))
    moo_path = RESULTS_DATA_DIR / "bisi_ax_moo_suggestions.csv"
    if moo_path.is_file():
        moo = pd.read_csv(moo_path)
        story.append(Paragraph(
            "Ax optimizes the screened phase-purity and crystallinity objectives separately. "
            "All input values are selected from observed levels; proposals are exploratory "
            "and should be checked against process feasibility.",
            styles["BodySmall"],
        ))
        story.append(Spacer(1, 0.15 * cm))
        fig = _figure(FIGURES_DIR / "bisi_ax_pareto_front.png")
        if fig is not None:
            story.append(fig)
            story.append(Spacer(1, 0.15 * cm))
        story.append(_suggestions_table(moo, df_bo.attrs["parameter_columns"]))
    else:
        story.append(Paragraph("Ax candidate output was not present when this report was generated.", styles["BodySmall"]))

    story.append(Paragraph("Interpretation limits", styles["SectionHead"]))
    story.append(Paragraph(
        "Peak classification depends on the selected RTF cards, intensity threshold, peak detector, "
        "and matching tolerance. The unmatched/overlap area is a screening proxy, not a quantitative "
        "phase fraction. The Le Bail fits use a Bragg–Brentano profile model as a proxy for GIXRD "
        "and are qualitative only; fitted intensities do not establish validated phase fractions. "
        "Verify phase references and process feasibility before choosing follow-up experiments.",
        styles["BodySmall"],
    ))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="BiSI XRD + BO report",
    )
    doc.build(story)
    return output_path


if __name__ == "__main__":
    print(f"Wrote {build_report()}")
