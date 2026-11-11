"""Maʼlumotlar toʻplamini yuklash, tozalash va boʻlish (FR-30)."""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook
from sklearn.model_selection import train_test_split

from app.kb_import import SHEET_NAME as KB_SHEET
from app.kb_import import canonical_category, is_true, normalize_label
from app.nlp.masking import mask_pii
from app.nlp.normalizer import normalize

SEED = 42
TEST_SIZE = 0.2
MIN_PER_CATEGORY = 5
TARGET_PER_CATEGORY = 150

_TEXT_COLUMNS = {"murojaat", "murojaat matni", "talaba murojaati", "savol", "matn"}
_CATEGORY_COLUMNS = {"toifa", "kategoriya"}
_TYPO_COLUMNS = {"imlo xatosi", "imlo xato"}
_HEADER_SCAN_ROWS = 10
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


class DatasetError(ValueError):
    pass


@dataclass(frozen=True)
class Sample:
    raw: str  # maskalangan, lekin normallashtirilmagan
    norm: str
    category: str
    cyrillic: bool
    typo: bool


@dataclass
class Dataset:
    samples: list[Sample]
    sha256: str
    total_rows: int
    skipped_rows: list[int] = field(default_factory=list)
    duplicates: int = 0
    conflicts: int = 0

    @property
    def per_category(self) -> dict[str, int]:
        return dict(sorted(Counter(s.category for s in self.samples).items()))

    @property
    def below_target(self) -> list[str]:
        return [c for c, n in self.per_category.items() if n < TARGET_PER_CATEGORY]


def _find_columns(rows: list[tuple]) -> tuple[int, dict[str, int]] | None:
    for index, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        labels = [normalize_label(cell) for cell in row]
        columns = {}
        for name, aliases in (
            ("text", _TEXT_COLUMNS),
            ("category", _CATEGORY_COLUMNS),
            ("typo", _TYPO_COLUMNS),
        ):
            position = next((i for i, label in enumerate(labels) if label in aliases), None)
            if position is not None:
                columns[name] = position
        if "text" in columns and "category" in columns:
            return index, columns
    return None


def _locate_table(path: Path, sheet: str | None) -> tuple[list[tuple], int, dict[str, int]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    if sheet is not None and sheet not in workbook.sheetnames:
        raise DatasetError(f"“{sheet}” varagʻi topilmadi: {workbook.sheetnames}")
    for name in [sheet] if sheet else [n for n in workbook.sheetnames if n != KB_SHEET]:
        rows = list(workbook[name].iter_rows(values_only=True))
        found = _find_columns(rows)
        if found:
            return rows, *found
    raise DatasetError(
        "Murojaat matni va toifa ustunlari topilmadi. Mavjud varaqlar: "
        f"{workbook.sheetnames}. Ustun nomlari: “Murojaat” va “Toifa”."
    )


def _cell(row: tuple, position: int | None) -> object:
    return row[position] if position is not None and position < len(row) else None


def _remove_duplicates(samples: list[Sample]) -> tuple[list[Sample], int, int]:
    """Takrorlar normallashgan matn boʻyicha aniqlanadi, aks holda test sizib ketadi."""
    labels_by_text: dict[str, set[str]] = {}
    for sample in samples:
        labels_by_text.setdefault(sample.norm, set()).add(sample.category)

    kept, seen, conflicts, duplicates = [], set(), 0, 0
    for sample in samples:
        if len(labels_by_text[sample.norm]) > 1:
            conflicts += 1
        elif sample.norm in seen:
            duplicates += 1
        else:
            seen.add(sample.norm)
            kept.append(sample)
    return kept, duplicates, conflicts


def load_dataset(
    path: Path, sheet: str | None = None, slang: dict[str, str] | None = None
) -> Dataset:
    rows, header, columns = _locate_table(path, sheet)
    samples, skipped, total = [], [], 0
    for number, row in enumerate(rows[header + 1 :], start=header + 2):
        text = _cell(row, columns["text"])
        category_value = _cell(row, columns["category"])
        if text is None and category_value is None:
            continue
        total += 1
        category = canonical_category(category_value)
        text = "" if text is None else str(text).strip()
        if not (text and category):
            skipped.append(number)
            continue
        masked = mask_pii(text)
        samples.append(
            Sample(
                raw=masked,
                norm=normalize(masked, slang),
                category=category,
                cyrillic=_CYRILLIC.search(text) is not None,
                typo=is_true(_cell(row, columns.get("typo"))),
            )
        )

    kept, duplicates, conflicts = _remove_duplicates(samples)
    dataset = Dataset(
        samples=kept,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        total_rows=total,
        skipped_rows=skipped,
        duplicates=duplicates,
        conflicts=conflicts,
    )
    too_small = {c: n for c, n in dataset.per_category.items() if n < MIN_PER_CATEGORY}
    if len(dataset.per_category) < 2 or too_small:
        raise DatasetError(
            f"Kamida 2 ta toifa va har birida {MIN_PER_CATEGORY} ta murojaat kerak: "
            f"{dataset.per_category}"
        )
    return dataset


def load_or_create_split(dataset: Dataset, path: Path) -> tuple[list[int], list[int]]:
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["sha256"] == dataset.sha256 and saved["seed"] == SEED:
            return saved["train"], saved["test"]

    indices = list(range(len(dataset.samples)))
    train, test = train_test_split(
        indices,
        test_size=TEST_SIZE,
        random_state=SEED,
        stratify=[sample.category for sample in dataset.samples],
    )
    payload = {"sha256": dataset.sha256, "seed": SEED, "train": sorted(train), "test": sorted(test)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload["train"], payload["test"]
