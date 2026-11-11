import json

import pytest
from openpyxl import Workbook

from app.nlp import classifier
from experiments import train_baselines
from experiments.dataset import DatasetError, load_dataset, load_or_create_split
from experiments.train_baselines import run

TEMPLATES = {
    "Stipendiya": ("stipendiya", "stipendiyam", "grant puli", "plastik karta"),
    "Yotoqxona": ("yotoqxona", "yotoqxonaga", "xona", "ttj joyi"),
    "Hujjatlar va arizalar": ("maʼlumotnoma", "ariza", "diplom", "hujjat"),
}
CYRILLIC = {"Stipendiya": "стипендия", "Yotoqxona": "ётоқхона", "Hujjatlar va arizalar": "ариза"}
HEADER = ["Murojaat", "Toifa", "Imlo xatosi"]


def rows(per_word=8):
    result = []
    for category, words in TEMPLATES.items():
        for word in words:
            for number in range(per_word):
                result.append([f"{word} haqida {number} savol bor", category, "Yoʻq"])
        for number in range(per_word):
            result.append([f"{CYRILLIC[category]} ҳақида {number} савол", category, "Yoʻq"])
        for number in range(per_word):
            result.append([f"{words[0]}a haqda {number} savl", category, "Ha"])
    return result


def workbook(path, table, sheet="Murojaatlar", title=False):
    book = Workbook()
    worksheet = book.active
    worksheet.title = sheet
    if title:
        worksheet.append(["Shablon sarlavhasi"])
    worksheet.append(HEADER)
    for row in table:
        worksheet.append(row)
    book.save(path)
    return path


@pytest.fixture
def data(tmp_path):
    return workbook(tmp_path / "data.xlsx", rows())


@pytest.fixture(autouse=True)
def no_real_export(monkeypatch, tmp_path):
    monkeypatch.setattr(train_baselines, "TRANSFORMER_INPUT", tmp_path / "input.json")


def test_loads_and_flags(data):
    dataset = load_dataset(data)
    sample = next(s for s in dataset.samples if s.cyrillic)
    assert sample.norm.isascii() or "ʻ" in sample.norm
    assert any(s.typo for s in dataset.samples)
    assert set(dataset.per_category) == set(TEMPLATES)


def test_header_may_be_below_title(tmp_path):
    assert load_dataset(workbook(tmp_path / "d.xlsx", rows(), title=True)).samples


def test_personal_data_is_masked_on_load(tmp_path):
    table = rows() + [["Stipendiya +998901234567 qachon, ismim Aziza", "Stipendiya", ""]]
    dataset = load_dataset(workbook(tmp_path / "d.xlsx", table))
    joined = " ".join(s.raw + s.norm for s in dataset.samples).lower()
    assert "901234567" not in joined
    assert "aziza" not in joined


def test_duplicates_collapse_across_script_and_spelling(tmp_path):
    table = rows() + [["Ariza beraman", "Hujjatlar va arizalar", ""]] * 2
    table += [["Ариза бераман", "Hujjatlar va arizalar", ""]]
    dataset = load_dataset(workbook(tmp_path / "d.xlsx", table))
    assert sum(s.norm == "ariza beraman" for s in dataset.samples) == 1
    assert dataset.duplicates == 2


def test_conflicting_labels_are_dropped(tmp_path):
    table = rows() + [["bir xil matn", "Stipendiya", ""], ["bir xil matn", "Yotoqxona", ""]]
    dataset = load_dataset(workbook(tmp_path / "d.xlsx", table))
    assert not any(s.norm == "bir xil matn" for s in dataset.samples)
    assert dataset.conflicts == 2


def test_bad_rows_are_reported(tmp_path):
    table = rows() + [["matn", "Nomaʼlum toifa", ""], ["", "Stipendiya", ""]]
    dataset = load_dataset(workbook(tmp_path / "d.xlsx", table))
    assert len(dataset.skipped_rows) == 2


def test_missing_columns_explained(tmp_path):
    book = Workbook()
    book.active.append(["A", "B"])
    book.save(tmp_path / "d.xlsx")
    with pytest.raises(DatasetError, match="Toifa"):
        load_dataset(tmp_path / "d.xlsx")


def test_too_few_samples_refused(tmp_path):
    table = [[f"matn {n}", "Stipendiya", ""] for n in range(20)]
    table += [["bitta", "Yotoqxona", ""]]
    with pytest.raises(DatasetError, match="Kamida"):
        load_dataset(workbook(tmp_path / "d.xlsx", table))


def test_knowledge_base_sheet_is_not_used(tmp_path):
    path = workbook(tmp_path / "d.xlsx", rows(), sheet="Bilimlar bazasi")
    with pytest.raises(DatasetError):
        load_dataset(path)


def test_split_is_stratified_saved_and_reused(data, tmp_path):
    dataset = load_dataset(data)
    path = tmp_path / "split.json"
    train, test = load_or_create_split(dataset, path)
    assert not set(train) & set(test)
    assert len(test) == pytest.approx(len(dataset.samples) * 0.2, abs=1)
    counts = [sum(dataset.samples[i].category == c for i in test) for c in TEMPLATES]
    assert max(counts) - min(counts) <= 1

    saved = json.loads(path.read_text())
    saved["test"] = saved["test"][:-1]
    path.write_text(json.dumps(saved))
    assert load_or_create_split(dataset, path)[1] == saved["test"]


def test_split_recreated_when_data_changes(data, tmp_path):
    dataset = load_dataset(data)
    path = tmp_path / "split.json"
    load_or_create_split(dataset, path)
    saved = json.loads(path.read_text())
    saved["sha256"] = "boshqa"
    saved["test"] = [0]
    path.write_text(json.dumps(saved))
    assert load_or_create_split(dataset, path)[1] != [0]


def test_run_produces_every_required_output(data, tmp_path):
    out = tmp_path / "results"
    metrics, timing, _ = run(data, out)
    assert set(metrics["models"]) == {"rule-based", "naive-bayes", "svm"}
    for name, model in metrics["models"].items():
        holdout = model["holdout"]
        assert {"accuracy", "macro_precision", "macro_recall", "macro_f1"} <= set(holdout)
        assert set(holdout["per_category"]) == set(TEMPLATES)
        assert len(holdout["confusion_matrix"]) == 3
        assert model["cv"]["folds"] == 5
        assert (out / f"confusion_{name}.png").stat().st_size > 1000
        assert timing[name] > 0
    for file in ("metrics.json", "timing.json", "split.json", "comparison.csv"):
        assert (out / file).exists()
    assert metrics["dataset"]["below_target_150"]
    assert "svm" in (out / "comparison.csv").read_text(encoding="utf-8-sig")


def test_run_is_reproducible(data, tmp_path):
    run(data, tmp_path / "a")
    run(data, tmp_path / "b")
    first = (tmp_path / "a" / "metrics.json").read_bytes()
    assert first == (tmp_path / "b" / "metrics.json").read_bytes()


def test_normalization_helps_cyrillic_rules(data, tmp_path):
    metrics, _, _ = run(data, tmp_path / "r")
    cyrillic = metrics["models"]["rule-based"]["robustness"]["cyrillic"]
    assert cyrillic["n"] > 0
    assert cyrillic["normalized"]["accuracy"] > cyrillic["raw"]["accuracy"]


def test_missing_typo_flags_report_zero(tmp_path):
    table = [row[:2] + [""] for row in rows()]
    metrics, _, _ = run(workbook(tmp_path / "d.xlsx", table), tmp_path / "r")
    typo = metrics["models"]["svm"]["robustness"]["typo"]
    assert typo == {"n": 0}


def test_transformer_input_has_no_raw_personal_data(tmp_path):
    table = rows() + [[f"Stipendiya +99890123456{n} savol", "Stipendiya", ""] for n in range(5)]
    run(workbook(tmp_path / "d.xlsx", table), tmp_path / "r")
    text = train_baselines.TRANSFORMER_INPUT.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert "99890123456" not in text
    assert payload["test"][0].keys() == {"norm", "raw", "label", "cyrillic", "typo"}


def test_transformer_results_join_comparison(data, tmp_path):
    out = tmp_path / "r"
    out.mkdir()
    holdout = {"accuracy": 1, "macro_precision": 1, "macro_recall": 1, "macro_f1": 0.99}
    (out / "transformer.json").write_text(
        json.dumps({"holdout": holdout, "cv": None, "mean_prediction_ms_cpu": 123.4}),
        encoding="utf-8",
    )
    run(data, out)
    text = (out / "comparison.csv").read_text(encoding="utf-8-sig")
    assert "transformer,1,1,1,0.99,,,123.4" in text


def test_main_without_register_touches_nothing(data, tmp_path, monkeypatch, capsys):
    model_path = tmp_path / "svm.joblib"
    monkeypatch.setattr(train_baselines, "MODEL_PATH", model_path)
    train_baselines.main(["--data", str(data), "--out", str(tmp_path / "r")])
    assert not model_path.exists()
    assert "macro-F1" in capsys.readouterr().out


def test_main_reports_missing_file(tmp_path):
    with pytest.raises(SystemExit, match="topilmadi"):
        train_baselines.main(["--data", str(tmp_path / "yoq.xlsx")])


def test_main_reports_bad_dataset(tmp_path):
    table = [[f"matn {n}", "Stipendiya", ""] for n in range(20)]
    path = workbook(tmp_path / "d.xlsx", table)
    with pytest.raises(SystemExit, match="Kamida"):
        train_baselines.main(["--data", str(path), "--out", str(tmp_path / "r")])


def test_register_stores_k1_and_model(data, tmp_path, monkeypatch, db_session):
    import app.db.session as session_module
    from app.db.models import ModelVersion
    from app.metrics.indicators import model_k1

    model_path = tmp_path / "svm.joblib"
    monkeypatch.setattr(train_baselines, "MODEL_PATH", model_path)
    monkeypatch.setattr(classifier, "MODEL_PATH", model_path)
    monkeypatch.setattr(session_module, "SessionLocal", lambda: _NoClose(db_session))

    out = tmp_path / "r"
    metrics, _, svm = run(data, out)
    train_baselines.register(metrics, svm, out)
    train_baselines.register(metrics, svm, out)

    assert db_session.query(ModelVersion).count() == 3
    assert model_k1(db_session, "svm") == metrics["models"]["svm"]["holdout"]["macro_f1"]
    assert classifier.get_classifier("svm").predict("stipendiya haqida")[0][0] == "Stipendiya"


class _NoClose:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *_):
        return False


def test_transformer_classifier_adapter(tmp_path, monkeypatch):
    pytest.importorskip("transformers")
    pytest.importorskip("torch")
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizer

    vocab = tmp_path / "vocab.txt"
    vocab.write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "stipendiya"]))
    labels = {0: "Stipendiya", 1: "Yotoqxona"}
    config = BertConfig(
        vocab_size=5,
        hidden_size=8,
        num_hidden_layers=1,
        num_attention_heads=1,
        intermediate_size=8,
        id2label=labels,
        label2id={v: k for k, v in labels.items()},
    )
    path = tmp_path / "transformer"
    BertForSequenceClassification(config).save_pretrained(path)
    BertTokenizer(str(vocab)).save_pretrained(path)

    monkeypatch.setattr(classifier, "TRANSFORMER_PATH", path)
    assert classifier.TRANSFORMER in classifier.available_models()
    ranked = classifier.get_classifier(classifier.TRANSFORMER).predict("stipendiya")
    assert {name for name, _ in ranked} == set(labels.values())
    assert sum(score for _, score in ranked) == pytest.approx(1)
    assert ranked[0][1] >= ranked[1][1]


def test_transformer_unavailable_without_files(tmp_path, monkeypatch):
    monkeypatch.setattr(classifier, "TRANSFORMER_PATH", tmp_path / "yoq")
    assert classifier.TRANSFORMER not in classifier.available_models()
