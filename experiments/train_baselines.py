"""Modellarni taqqoslash (FR-30 – FR-33).

Bitta buyruq bilan qayta ishga tushadi va bir xil natija beradi:
    python -m experiments.train_baselines --data data/Murojaatlar_yigish_shabloni.xlsx
"""

import argparse
import csv
import json
import time
from pathlib import Path
from statistics import mean, pstdev

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from app.nlp.classifier import MODEL_PATH, RuleBasedClassifier  # noqa: E402
from app.nlp.pipelines import build_naive_bayes, build_svm  # noqa: E402
from experiments.dataset import (  # noqa: E402
    SEED,
    Dataset,
    DatasetError,
    Sample,
    load_dataset,
    load_or_create_split,
)

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
SLANG_PATH = ROOT / "slang.json"
DEFAULT_DATA = ROOT.parent / "data" / "Murojaatlar_yigish_shabloni.xlsx"
TRANSFORMER_INPUT = ROOT.parent / "data" / "transformer_input.json"
CV_FOLDS = 5
_DIGITS = 6
_MODELS = ("rule-based", "naive-bayes", "svm")
_SUBSETS = {"cyrillic": lambda s: s.cyrillic, "typo": lambda s: s.typo}
_COLORS = LinearSegmentedColormap.from_list("uses", ["#f4f8fd", "#2a78d6", "#123a6b"])


class _RuleBased:
    def fit(self, _texts: list[str], _labels: list[str]) -> "_RuleBased":
        return self

    def predict(self, texts: list[str]) -> list[str]:
        classifier = RuleBasedClassifier()
        return [classifier.predict(text)[0][0] for text in texts]


def _build(name: str, labels: list[str]):
    if name == "rule-based":
        return _RuleBased()
    return build_naive_bayes() if name == "naive-bayes" else build_svm(labels)


def _fit(name: str, texts: list[str], labels: list[str]):
    return _build(name, labels).fit(texts, labels)


def _round(value: float) -> float:
    return round(float(value), _DIGITS)


def _scores(truth: list[str], predicted: list[str]) -> dict[str, float]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        truth, predicted, average="macro", zero_division=0
    )
    return {
        "accuracy": _round(accuracy_score(truth, predicted)),
        "macro_precision": _round(precision),
        "macro_recall": _round(recall),
        "macro_f1": _round(f1),
    }


def _holdout(truth: list[str], predicted: list[str], labels: list[str]) -> dict:
    report = classification_report(
        truth, predicted, labels=labels, output_dict=True, zero_division=0
    )
    per_category = {
        label: {key: _round(value) for key, value in report[label].items()} for label in labels
    }
    return _scores(truth, predicted) | {
        "per_category": per_category,
        "confusion_matrix": confusion_matrix(truth, predicted, labels=labels).tolist(),
    }


def _cross_validate(name: str, samples: list[Sample]) -> dict:
    labels = [sample.category for sample in samples]
    folds = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=SEED)
    results = []
    for train, test in folds.split(samples, labels):
        model = _fit(name, [samples[i].norm for i in train], [labels[i] for i in train])
        predicted = model.predict([samples[i].norm for i in test])
        results.append(_scores([labels[i] for i in test], [str(p) for p in predicted]))
    return {
        "folds": CV_FOLDS,
        "accuracy_mean": _round(mean(r["accuracy"] for r in results)),
        "macro_f1_mean": _round(mean(r["macro_f1"] for r in results)),
        "macro_f1_std": _round(pstdev(r["macro_f1"] for r in results)),
    }


def _robustness(normalized, raw, test: list[Sample]) -> dict:
    """Bir xil murojaatlar normallashtirish bilan va usiz baholanadi (FR-33)."""
    result = {}
    for subset, belongs in _SUBSETS.items():
        members = [sample for sample in test if belongs(sample)]
        entry: dict = {"n": len(members)}
        if members:
            truth = [sample.category for sample in members]
            with_norm = normalized.predict([sample.norm for sample in members])
            without = raw.predict([sample.raw for sample in members])
            entry["normalized"] = _scores(truth, [str(p) for p in with_norm])
            entry["raw"] = _scores(truth, [str(p) for p in without])
        result[subset] = entry
    return result


def _mean_prediction_ms(model, texts: list[str]) -> float:
    """Ilovadagidek bittalab bashorat qilinadi."""
    started = time.perf_counter()
    for text in texts:
        model.predict([text])
    return (time.perf_counter() - started) * 1000 / len(texts)


def _save_confusion_png(name: str, matrix: list[list[int]], labels: list[str], out: Path) -> None:
    figure, axes = plt.subplots(figsize=(8, 6.5), dpi=150)
    image = axes.imshow(matrix, cmap=_COLORS)
    ticks = range(len(labels))
    axes.set_xticks(ticks, labels, rotation=35, ha="right")
    axes.set_yticks(ticks, labels)
    axes.set_xlabel("Bashorat qilingan toifa")
    axes.set_ylabel("Haqiqiy toifa")
    axes.set_title(f"Xatolar matritsasi: {name}", loc="left")
    axes.spines[:].set_visible(False)
    highest = max(max(row) for row in matrix) or 1
    for row, values in enumerate(matrix):
        for column, value in enumerate(values):
            color = "white" if value > highest * 0.55 else "#0b0b0b"
            axes.text(column, row, value, ha="center", va="center", color=color)
    figure.colorbar(image, fraction=0.046, pad=0.04).outline.set_visible(False)
    figure.tight_layout()
    figure.savefig(out / f"confusion_{name}.png")
    plt.close(figure)


def _write_transformer_input(train: list[Sample], test: list[Sample], labels: list[str]) -> None:
    def row(sample: Sample) -> dict:
        return {
            "norm": sample.norm,
            "raw": sample.raw,
            "label": sample.category,
            "cyrillic": sample.cyrillic,
            "typo": sample.typo,
        }

    payload = {"labels": labels, "train": [row(s) for s in train], "test": [row(s) for s in test]}
    TRANSFORMER_INPUT.parent.mkdir(parents=True, exist_ok=True)
    TRANSFORMER_INPUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_comparison(metrics: dict, timing: dict, out: Path) -> None:
    transformer_path = out / "transformer.json"
    models = dict(metrics["models"])
    timings = dict(timing)
    if transformer_path.exists():
        transformer = json.loads(transformer_path.read_text(encoding="utf-8"))
        models["transformer"] = transformer
        timings["transformer"] = transformer.get("mean_prediction_ms_cpu")

    header = ["Model", "Accuracy", "Macro-P", "Macro-R", "Macro-F1", "CV F1", "CV std", "Vaqt, ms"]
    with (out / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        for name, model in models.items():
            holdout, cv = model["holdout"], model.get("cv") or {}
            writer.writerow(
                [
                    name,
                    holdout["accuracy"],
                    holdout["macro_precision"],
                    holdout["macro_recall"],
                    holdout["macro_f1"],
                    cv.get("macro_f1_mean", ""),
                    cv.get("macro_f1_std", ""),
                    "" if timings.get(name) is None else round(timings[name], 3),
                ]
            )


def _dataset_summary(dataset: Dataset, train: list[int], test: list[int]) -> dict:
    return {
        "sha256": dataset.sha256,
        "rows": dataset.total_rows,
        "skipped_rows": dataset.skipped_rows,
        "duplicates_removed": dataset.duplicates,
        "conflicting_labels_removed": dataset.conflicts,
        "samples": len(dataset.samples),
        "train": len(train),
        "test": len(test),
        "per_category": dataset.per_category,
        "below_target_150": dataset.below_target,
    }


def run(
    data: Path, out: Path, sheet: str | None = None, export_transformer: bool = True
) -> tuple[dict, dict, object]:
    slang = json.loads(SLANG_PATH.read_text(encoding="utf-8"))
    dataset = load_dataset(data, sheet, slang)
    out.mkdir(parents=True, exist_ok=True)
    train_ids, test_ids = load_or_create_split(dataset, out / "split.json")
    train = [dataset.samples[i] for i in train_ids]
    test = [dataset.samples[i] for i in test_ids]
    train_labels = [sample.category for sample in train]
    truth = [sample.category for sample in test]
    labels = sorted(set(truth) | set(train_labels))

    models, timing, svm = {}, {}, None
    for name in _MODELS:
        model = _fit(name, [sample.norm for sample in train], train_labels)
        raw_model = _fit(name, [sample.raw for sample in train], train_labels)
        predicted = [str(p) for p in model.predict([sample.norm for sample in test])]
        models[name] = {
            "holdout": _holdout(truth, predicted, labels),
            "cv": _cross_validate(name, dataset.samples),
            "robustness": _robustness(model, raw_model, test),
        }
        timing[name] = _mean_prediction_ms(model, [sample.norm for sample in test])
        _save_confusion_png(name, models[name]["holdout"]["confusion_matrix"], labels, out)
        if name == "svm":
            svm = model

    metrics = {
        "seed": SEED,
        "labels": labels,
        "dataset": _dataset_summary(dataset, train_ids, test_ids),
        "models": models,
    }
    (out / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    # Vaqt har safar farq qiladi, shuning uchun takrorlanuvchi natijadan alohida.
    (out / "timing.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")
    _write_comparison(metrics, timing, out)
    if export_transformer:
        _write_transformer_input(train, test, labels)
    return metrics, timing, svm


def register(metrics: dict, svm, out: Path) -> None:
    """Natijani ilovaga oʻtkazadi: k1 shu yerdan olinadi va SVM modeli almashtiriladi."""
    from app.db.models import ModelVersion
    from app.db.session import SessionLocal

    entries = {name: model["holdout"] for name, model in metrics["models"].items()}
    transformer_path = out / "transformer.json"
    if transformer_path.exists():
        entries["transformer"] = json.loads(transformer_path.read_text(encoding="utf-8"))["holdout"]

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(svm, MODEL_PATH)
    keys = ("accuracy", "macro_precision", "macro_recall", "macro_f1")
    with SessionLocal() as db:
        for name, holdout in entries.items():
            row = db.query(ModelVersion).filter_by(name=name).one_or_none()
            if row is None:
                row = ModelVersion(name=name, type=name)
                db.add(row)
            row.metrics_json = json.dumps({key: holdout[key] for key in keys})
            row.path = str(MODEL_PATH) if name == "svm" else None
        db.commit()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--sheet")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--register",
        action="store_true",
        help="natijani ilova bazasiga yozish va SVM ni almashtirish (faqat haqiqiy maʼlumotda)",
    )
    args = parser.parse_args(argv)
    if not args.data.exists():
        raise SystemExit(f"Fayl topilmadi: {args.data}")
    try:
        metrics, _, svm = run(args.data, args.out, args.sheet)
    except DatasetError as error:
        raise SystemExit(str(error)) from error

    summary = metrics["dataset"]
    print(f"Murojaatlar: {summary['samples']} (train {summary['train']}, test {summary['test']})")
    if summary["below_target_150"]:
        print(f"Diqqat, 150 tadan kam toifalar: {', '.join(summary['below_target_150'])}")
    for name, model in metrics["models"].items():
        print(f"{name}: macro-F1 = {model['holdout']['macro_f1']:.4f}")
    print(f"Natijalar: {args.out}")
    if args.register:
        register(metrics, svm, args.out)
        print("Natijalar ilovaga oʻtkazildi.")


if __name__ == "__main__":
    main()
