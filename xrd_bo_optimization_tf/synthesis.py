"""Extraction of synthesis parameters from NOMAD archive JSON data."""

import re
from pathlib import Path
from typing import Any

import pandas as pd

from .nomad_client import iter_archive_files, read_archive


def _sample_name(samples: Any) -> str | None:
    if not isinstance(samples, list):
        return None
    for sample in samples:
        if isinstance(sample, dict) and sample.get("name"):
            return str(sample["name"]).split()[0]
    return None


def extract_sample_id_from_archive(
    archive_path: Path, archive_data: dict[str, Any]
) -> str | None:
    """Get a sample identifier from sample metadata, archive name, or filename."""
    sample_id = _sample_name(archive_data.get("samples"))
    if sample_id:
        return sample_id

    name = str(archive_data.get("name", "")).split()
    if name and any(character.isdigit() for character in name[0]):
        return name[0]

    filename = archive_path.name.split("_")[0]
    return filename if any(character.isdigit() for character in filename) else None


def _temperature_c(step: dict[str, Any]) -> float | None:
    if step.get("temperature_K") is not None:
        return float(step["temperature_K"]) - 273.15
    # INL hotplate-annealing steps store `temperature` in Kelvin.
    if step.get("temperature") is not None:
        return float(step["temperature"]) - 273.15
    return None


def extract_processing_archive(archive_path: Path) -> dict[str, Any] | None:
    """Extract a sample identifier and recognized synthesis steps from an archive."""
    root = read_archive(archive_path)
    archive_data = root.get("data")
    if not isinstance(archive_data, dict):
        return None

    sample_id = extract_sample_id_from_archive(archive_path, archive_data)
    if not sample_id:
        return None

    activities = []
    steps = archive_data.get("steps", [])
    if not isinstance(steps, list):
        return {
            "sample_id": sample_id,
            "activities": [],
            "archive_path": archive_path,
        }

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("m_def", ""))
        parameters: dict[str, Any] = {}
        activity: dict[str, Any] = {
            "step_index": len(activities),
            "type": step_type,
            "name": step.get("name"),
            "parameters": parameters,
        }

        if "SpinCoating" in step_type:
            parameters.update(
                speed_rpm=step.get("speed"),
                duration_s=step.get("duration"),
                acceleration=step.get("acceleration"),
            )
            solution = step.get("solution")
            if isinstance(solution, list) and solution:
                solution = next(
                    (item for item in solution if isinstance(item, dict)), None
                )
            if isinstance(solution, dict):
                activity["solution"] = {
                    "reference": solution.get("name"),
                    "volume_ml": solution.get("volume"),
                }
        elif "HotplateAnnealing" in step_type or "Annealing" in step_type:
            duration = step.get("duration")
            parameters.update(
                temperature_c=_temperature_c(step),
                duration_s=duration,
                duration_min=float(duration) / 60 if duration is not None else None,
            )
        elif "Selenization" in step_type:
            parameters.update(
                temperature_c=_temperature_c(step),
                time_s=step.get("time", step.get("duration")),
                working_pressure_pa=step.get(
                    "working_pressure", step.get("chamber_pressure")
                ),
            )

        activity["parameters"] = {
            key: value for key, value in parameters.items() if value is not None
        }
        if activity["parameters"] or "solution" in activity:
            activities.append(activity)

    if not activities:
        return None

    return {
        "sample_id": sample_id,
        "activities": activities,
        "archive_path": archive_path,
        "archive_data": archive_data,
    }


def _element_moles(component: dict[str, Any], element: str) -> float:
    """Moles of an element contributed by one solution component."""
    amount = component.get("amount_of_substance")
    if amount is None:
        return 0.0
    formula = str((component.get("pure_substance") or {}).get("molecular_formula", ""))
    # Count atoms of the element in the molecular formula (e.g. "Ba" -> 1).
    count = 0
    for symbol, num in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        if symbol == element:
            count += int(num) if num else 1
    return float(amount) * count


def _formula_element_count(formula: str, element: str) -> int:
    """Count atoms of ``element`` in a plain chemical formula."""
    return sum(
        int(number) if number else 1
        for symbol, number in re.findall(r"([A-Z][a-z]?)(\d*)", formula)
        if symbol == element
    )


def _solution_bisi_composition(data: dict[str, Any]) -> dict[str, Any] | None:
    """Calculate Bi molarity and atomic S:Bi/I:Bi ratios from solution solutes.

    NOMAD's ``calculated_volume`` and ``amount_of_substance`` values are in L
    and mol, respectively. Prefer the resolved ``solutes`` collection; fall
    back to fully resolved components when a solution archive lacks solutes.
    """
    volume_l = data.get("calculated_volume")
    if volume_l is None or float(volume_l) <= 0:
        return None

    solutes = data.get("solutes")
    source_components = (
        solutes
        if isinstance(solutes, list) and solutes
        else data.get("components", [])
    )
    totals = {element: 0.0 for element in ("Bi", "S", "I")}
    for component in source_components:
        if not isinstance(component, dict):
            continue
        formula = str(
            (component.get("pure_substance") or {}).get("molecular_formula", "")
        )
        amount = component.get("amount_of_substance")
        if not formula or amount is None:
            continue
        for element in totals:
            totals[element] += float(amount) * _formula_element_count(formula, element)

    bi_moles = totals["Bi"]
    if bi_moles <= 0:
        return None
    return {
        "bismuth_concentration_mol_l": bi_moles / float(volume_l),
        "s_to_bi_molar_ratio": totals["S"] / bi_moles,
        "i_to_bi_molar_ratio": totals["I"] / bi_moles,
        "solution_volume_l": float(volume_l),
        "bi_moles": bi_moles,
        "s_moles": totals["S"],
        "i_moles": totals["I"],
    }


def _solution_compositions(archive_paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Map NOMAD Solution archive names to calculated BiSI precursor chemistry."""
    compositions: dict[str, dict[str, Any]] = {}
    for archive_path in archive_paths:
        data = read_archive(archive_path).get("data", {})
        if "solution.general.Solution" not in str(data.get("m_def", "")):
            continue
        name = str(data.get("name", "")).strip()
        composition = _solution_bisi_composition(data)
        if name and composition:
            compositions[name] = composition
    return compositions


def _match_solution_composition(
    solution_label: str | None,
    compositions: dict[str, dict[str, Any]],
) -> tuple[str | None, dict[str, Any] | None]:
    """Match a process solution label to its exact/prefix NOMAD solution name."""
    if not solution_label:
        return None, None
    label = solution_label.strip()
    candidates = sorted(compositions, key=len, reverse=True)
    matched_name = next(
        (
            name
            for name in candidates
            if label == name or label.startswith(f"{name} ")
        ),
        None,
    )
    return (
        (matched_name, compositions[matched_name])
        if matched_name is not None
        else (None, None)
    )


def extract_cbc_ratios(archive_paths: list[Path]) -> dict[str, float]:
    """Map solution name to its Cu/(Ba+Cu) molar ratio from Solution archives."""
    ratios: dict[str, float] = {}
    for archive_path in archive_paths:
        data = read_archive(archive_path).get("data", {})
        if "solution.general.Solution" not in str(data.get("m_def", "")):
            continue
        name = str(data.get("name", "")).split()
        if not name:
            continue
        cu = ba = 0.0
        for component in data.get("components", []):
            if not isinstance(component, dict):
                continue
            cu += _element_moles(component, "Cu")
            ba += _element_moles(component, "Ba")
        if cu + ba > 0:
            ratios[name[0]] = cu / (cu + ba)
    return ratios


def _count_spin_cycles(steps: Any) -> int:
    """Count spin-coating cycles as the number of INLSpinCoatingStep steps.

    INLHotplateAnnealingStep (soft/hard bakes) is not counted.
    """
    if not isinstance(steps, list):
        return 1
    count = sum(
        1
        for step in steps
        if isinstance(step, dict)
        and "INLSpinCoatingStep" in str(step.get("m_def", ""))
    )
    return count or 1


def extract_process_metadata(archive_paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Per-sample solution ref, spin-cycle count, and spin datetime.

    Read from INLSpinCoating process records: top-level `solution` list, the
    `steps` list (cycles counted by _count_spin_cycles), and `datetime`.
    """
    info: dict[str, dict[str, Any]] = {}
    for archive_path in archive_paths:
        data = read_archive(archive_path).get("data", {})
        m_def = str(data.get("m_def", ""))
        if "INLSpinCoating" not in m_def or "Recipe" in m_def:
            continue
        sample_id = extract_sample_id_from_archive(archive_path, data)
        if not sample_id:
            continue
        steps = data.get("steps", [])
        n_cycles = _count_spin_cycles(steps)
        solution = data.get("solution", [])
        solution_name = None
        if isinstance(solution, list) and solution and isinstance(solution[0], dict):
            solution_name = str(solution[0].get("name", "")).split()[0] or None
        entry = info.setdefault(sample_id, {})
        entry.setdefault("solution_key", solution_name)
        entry["n_spin_cycles"] = n_cycles or 1
        entry.setdefault("spin_datetime", data.get("datetime"))
    return info


def extract_mo_coating(archive_paths: list[Path]) -> dict[str, bool]:
    """Flag Mo-coated films.

    Mo coating is recorded inconsistently across the database, so we check all
    three places: a Mo layer in the stack, an 'SLG-Mo' substrate name, and the
    substrate's `material` field (e.g. 'SLG/Mo').
    """
    # Map substrate name -> material (e.g. 'SLG' or 'SLG/Mo').
    substrate_material: dict[str, str] = {}
    for archive_path in archive_paths:
        data = read_archive(archive_path).get("data", {})
        if "INLSubstrate" in str(data.get("m_def", "")):
            name = str(data.get("name", ""))
            if name:
                substrate_material[name] = str(data.get("material", ""))

    coated: dict[str, bool] = {}
    for archive_path in archive_paths:
        data = read_archive(archive_path).get("data", {})
        m_def = str(data.get("m_def", ""))
        if "INLThinFilmStack" not in m_def or "Reference" in m_def:
            continue
        sample_id = str(data.get("name", "")).split()
        if not sample_id:
            continue
        layers = data.get("layers", [])
        layer_has_mo = any(
            isinstance(layer, dict) and "Mo" in str(layer.get("name", ""))
            for layer in layers
        )
        substrate = data.get("substrate") or {}
        substrate_name = str(substrate.get("name", "")) if isinstance(substrate, dict) else ""
        material = substrate_material.get(substrate_name, "")
        coated[sample_id[0]] = (
            layer_has_mo or "Mo" in substrate_name or "Mo" in material
        )
    return coated


def build_synthesis_database(archive_paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Combine processing archives into one synthesis record per sample."""
    paths = list(archive_paths)
    grouped: dict[str, dict[str, Any]] = {}
    for archive_path in paths:
        extracted = extract_processing_archive(archive_path)
        if extracted is None:
            continue
        record = grouped.setdefault(
            extracted["sample_id"], {"all_activities": [], "archives": []}
        )
        record["all_activities"].extend(extracted["activities"])
        record["archives"].append(extracted["archive_path"])

    synthesis_db: dict[str, dict[str, Any]] = {}
    for sample_id, grouped_record in sorted(grouped.items()):
        record: dict[str, Any] = {
            "sample_id": sample_id,
            "spin_coating": [],
            "soft_bake": None,
            "hard_bake": None,
            "selenization": None,
            "solution_used": None,
            "solution_used_name": None,
            "solution_volume_ml": None,
            "num_archives": len(grouped_record["archives"]),
            "has_annealing": False,
            "completeness": "incomplete",
        }
        bake_count = 0
        for activity in grouped_record["all_activities"]:
            step_type = activity["type"]
            parameters = activity["parameters"]
            if "SpinCoating" in step_type:
                solution = activity.get("solution") or {}
                record["spin_coating"].append(
                    {
                        "step_name": activity.get("name"),
                        "speed_rpm": parameters.get("speed_rpm"),
                        "duration_s": parameters.get("duration_s"),
                        "acceleration": parameters.get("acceleration"),
                        "solution_name": solution.get("reference"),
                        "solution_volume_ml": solution.get("volume_ml"),
                    }
                )
            elif "HotplateAnnealing" in step_type or "Annealing" in step_type:
                bake_key = "soft_bake" if bake_count == 0 else "hard_bake"
                if bake_count < 2:
                    record[bake_key] = parameters
                bake_count += 1
            elif "Selenization" in step_type:
                record["selenization"] = parameters

        record["has_annealing"] = bake_count > 0
        record["completeness"] = "complete" if bake_count > 0 else "incomplete"

        spin_solution_steps = [
            step for step in record["spin_coating"] if step.get("solution_name")
        ]
        main_solution_step = next(
            (
                step
                for step in reversed(spin_solution_steps)
                if "stock solution" in str(step.get("step_name", "")).casefold()
            ),
            spin_solution_steps[-1] if spin_solution_steps else None,
        )
        seed_solution_step = next(
            (
                step
                for step in spin_solution_steps
                if "seed" in str(step.get("step_name", "")).casefold()
            ),
            spin_solution_steps[0] if spin_solution_steps else None,
        )
        if main_solution_step:
            record["solution_used_name"] = main_solution_step["solution_name"]
            record["solution_volume_ml"] = main_solution_step.get("solution_volume_ml")
        if seed_solution_step:
            record["seed_solution_name"] = seed_solution_step["solution_name"]

        synthesis_db[sample_id] = record

    for archive_path in paths:
        for sample_id, parameters in extract_star_selenization_archive(
            archive_path
        ).items():
            if sample_id in synthesis_db:
                synthesis_db[sample_id]["selenization"] = parameters

    # Enrich records with process timing and precursor-composition descriptors.
    process_meta = extract_process_metadata(paths)
    se_datetimes = extract_selenization_datetimes(paths)
    solution_compositions = _solution_compositions(paths)
    for sample_id, record in synthesis_db.items():
        meta = process_meta.get(sample_id, {})
        record["n_spin_cycles"] = meta.get("n_spin_cycles", 1)
        record["spin_to_se_days"] = _days_between(
            meta.get("spin_datetime"), se_datetimes.get(sample_id)
        )
        main_name, main_chemistry = _match_solution_composition(
            record.get("solution_used_name"), solution_compositions
        )
        seed_name, seed_chemistry = _match_solution_composition(
            record.get("seed_solution_name"), solution_compositions
        )
        record["solution_chemistry_name"] = main_name
        if main_chemistry:
            record.update(main_chemistry)
        record["seed_solution_chemistry_name"] = seed_name
        if seed_chemistry:
            record.update(
                {
                    f"seed_{key}": value
                    for key, value in seed_chemistry.items()
                }
            )

    return synthesis_db


def _days_between(start: Any, end: Any) -> float | None:
    """Whole days between two ISO datetimes, or None if either is missing."""
    if not start or not end:
        return None
    try:
        delta = pd.to_datetime(end) - pd.to_datetime(start)
    except (ValueError, TypeError):
        return None
    return round(delta.total_seconds() / 86400.0, 2)


def build_synthesis_dataframe(
    synthesis_db: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Convert extracted records into the project synthesis-table schema."""
    rows = []
    for sample_id, record in sorted(synthesis_db.items()):
        # Skip false-positive IDs derived from archive filenames (contain a dot).
        if "." in sample_id:
            continue
        has_data = any(
            record.get(key)
            for key in ("spin_coating", "soft_bake", "hard_bake", "selenization")
        ) or record.get("solution_used_name")
        if not has_data:
            continue

        match = re.match(r"(\d+[A-Z]+)", sample_id)
        spin_steps = record.get("spin_coating") or []
        spin = spin_steps[0] if spin_steps else {}
        soft_bake = record.get("soft_bake") or {}
        hard_bake = record.get("hard_bake") or {}
        selenization = record.get("selenization") or {}
        rows.append(
            {
                "sample_id": sample_id,
                "series": match.group(1) if match else sample_id,
                "completeness": record.get("completeness"),
                "spin_speed_rpm": spin.get("speed_rpm"),
                "spin_duration_s": spin.get("duration_s"),
                "spin_acceleration": spin.get("acceleration"),
                "soft_bake_temp_c": soft_bake.get("temperature_c"),
                "soft_bake_duration_s": soft_bake.get("duration_s"),
                "soft_bake_duration_min": soft_bake.get("duration_min"),
                "hard_bake_temp_c": hard_bake.get("temperature_c"),
                "hard_bake_duration_s": hard_bake.get("duration_s"),
                "hard_bake_duration_min": hard_bake.get("duration_min"),
                "selenization_temp_c": selenization.get("temperature_c"),
                "selenization_time_s": selenization.get("time_s"),
                "selenization_pressure_pa": selenization.get("working_pressure_pa"),
                "se_pulse_on_ms": selenization.get("se_pulse_on_ms"),
                "se_pulse_off_ms": selenization.get("se_pulse_off_ms"),
                "se_pulse_count": selenization.get("se_pulse_count"),
                "solution_used_name": record.get("solution_used_name"),
                "solution_volume_ml": record.get("solution_volume_ml"),
                "solution_chemistry_name": record.get("solution_chemistry_name"),
                "bismuth_concentration_mol_l": record.get(
                    "bismuth_concentration_mol_l"
                ),
                "s_to_bi_molar_ratio": record.get("s_to_bi_molar_ratio"),
                "i_to_bi_molar_ratio": record.get("i_to_bi_molar_ratio"),
                "seed_solution_name": record.get("seed_solution_name"),
                "seed_solution_chemistry_name": record.get(
                    "seed_solution_chemistry_name"
                ),
                "seed_bismuth_concentration_mol_l": record.get(
                    "seed_bismuth_concentration_mol_l"
                ),
                "seed_s_to_bi_molar_ratio": record.get(
                    "seed_s_to_bi_molar_ratio"
                ),
                "seed_i_to_bi_molar_ratio": record.get(
                    "seed_i_to_bi_molar_ratio"
                ),
                "n_spin_cycles": record.get("n_spin_cycles", 1),
                "spin_to_se_days": record.get("spin_to_se_days"),
                "num_archives": record.get("num_archives", 0),
                "has_annealing": record.get("has_annealing", False),
            }
        )
    dataframe = pd.DataFrame(rows)
    if not dataframe.empty:
        # Pulse count is a whole number; keep it nullable-integer for clean CSVs.
        dataframe["se_pulse_count"] = dataframe["se_pulse_count"].astype("Int64")
        dataframe["n_spin_cycles"] = dataframe["n_spin_cycles"].astype("Int64")
    return dataframe


def extract_star_selenization_archive(
    archive_path: Path,
) -> dict[str, dict[str, Any]]:
    """Extract STAR selenization conditions keyed by sample IDs in its metadata."""
    archive_data = read_archive(archive_path).get("data", {})
    if not isinstance(archive_data, dict) or "STARSelenizationAnnealing" not in str(
        archive_data.get("m_def", "")
    ):
        return {}

    steps = archive_data.get("steps", [])
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return {}
    step = steps[0]
    temperature_k = step.get("substrate_temperature")

    # Selenium pulse parameters live in the step's selenium_environment block.
    selenium_env = step.get("selenium_environment")
    selenium_env = selenium_env if isinstance(selenium_env, dict) else {}
    time_on_s = selenium_env.get("time_on")
    time_off_s = selenium_env.get("time_off")
    total_on_s = selenium_env.get("total_se_on_time")
    duration_s = step.get("duration")
    pulse_count = None
    if time_on_s and total_on_s:
        pulse_count = int(round(float(total_on_s) / float(time_on_s)))
    elif time_on_s and time_off_s and duration_s:
        pulse_count = int(round(float(duration_s) / (float(time_on_s) + float(time_off_s))))

    parameters = {
        "temperature_c": (
            float(temperature_k) - 273.15 if temperature_k is not None else None
        ),
        "time_s": duration_s,
        "working_pressure_pa": step.get("chamber_pressure"),
        "se_pulse_on_ms": float(time_on_s) * 1000 if time_on_s is not None else None,
        "se_pulse_off_ms": float(time_off_s) * 1000 if time_off_s is not None else None,
        "se_pulse_count": pulse_count,
    }
    samples = archive_data.get("samples", [])
    sample_ids = {
        str(sample["name"]).split()[0]
        for sample in samples
        if isinstance(sample, dict) and sample.get("name")
    }
    return {sample_id: parameters.copy() for sample_id in sample_ids}


def extract_selenization_datetimes(archive_paths: list[Path]) -> dict[str, str]:
    """Map each sample to the datetime of its STAR selenization record."""
    datetimes: dict[str, str] = {}
    for archive_path in archive_paths:
        data = read_archive(archive_path).get("data", {})
        if not isinstance(data, dict) or "STARSelenizationAnnealing" not in str(
            data.get("m_def", "")
        ) or "Recipe" in str(data.get("m_def", "")):
            continue
        timestamp = data.get("datetime")
        if not timestamp:
            continue
        for sample in data.get("samples", []):
            if isinstance(sample, dict) and sample.get("name"):
                datetimes[str(sample["name"]).split()[0]] = timestamp
    return datetimes


def collect_sample_ids(root: Path) -> set[str]:
    """Collect canonical sample IDs from INLThinFilmStack archives.

    INLThinFilmStack entries are the real films; bare INLThinFilm layers and
    archive filenames are not samples. The sample_id is the leading token of the
    stack name (e.g. "sample01 BiSI" -> "sample01").
    """
    sample_ids: set[str] = set()
    for archive_path in iter_archive_files(root):
        archive_data = read_archive(archive_path).get("data", {})
        if not isinstance(archive_data, dict):
            continue
        m_def = str(archive_data.get("m_def", ""))
        if "INLThinFilmStack" not in m_def or "Reference" in m_def:
            continue
        name = str(archive_data.get("name", "")).split()
        if name and any(character.isdigit() for character in name[0]):
            sample_ids.add(name[0])
    return sample_ids


def load_synthesis_archives(
    root: Path, only_samples: set[str] | None = None
) -> dict[str, dict[str, Any]]:
    """Extract synthesis records from every archive under a local NOMAD export.

    When only_samples is None, it defaults to the INLThinFilmStack sample IDs so
    that bare INLThinFilm layers and archive-filename artifacts are excluded.
    """
    archive_paths = list(iter_archive_files(root))
    synthesis_db = build_synthesis_database(archive_paths)
    if only_samples is None:
        only_samples = collect_sample_ids(root)
    return {
        sample_id: record
        for sample_id, record in synthesis_db.items()
        if sample_id in only_samples
    }


def fetch_nomad_archives_to_staging(staging_dir: Path) -> list[Path]:
    """Download all entry archives from the configured BiSI uploads to staging.

    The saved *.archive.json files are laid out per upload_id so the existing
    local extraction path (load_synthesis_archives) can consume them unchanged.
    Returns the list of written archive paths.
    """
    from . import nomad_api

    staging_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for upload_id in nomad_api.load_upload_ids():
        written.extend(
            nomad_api.download_upload_archives(upload_id, staging_dir)
        )
    return written


def load_synthesis_from_nomad(staging_dir: Path) -> dict[str, dict[str, Any]]:
    """Fetch BiSI archives from the NOMAD API into staging, then extract them."""
    fetch_nomad_archives_to_staging(staging_dir)
    return load_synthesis_archives(staging_dir)
