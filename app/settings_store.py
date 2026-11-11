"""Admin oʻzgartiradigan sozlamalar va jargon lugʻati."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Setting, SlangTerm
from app.nlp.classifier import RULE_BASED, SVM


@dataclass
class RuntimeSettings:
    tau: float = 0.60
    sigma: float = 0.30
    active_model: str = RULE_BASED
    ab_enabled: bool = False
    ab_model_a: str = RULE_BASED
    ab_model_b: str = SVM


def load_settings(db: Session) -> RuntimeSettings:
    stored = {row.key: row.value for row in db.scalars(select(Setting))}
    defaults = RuntimeSettings()
    return RuntimeSettings(
        tau=float(stored.get("tau", defaults.tau)),
        sigma=float(stored.get("sigma", defaults.sigma)),
        active_model=stored.get("active_model", defaults.active_model),
        ab_enabled=stored.get("ab_enabled", str(defaults.ab_enabled)) == "True",
        ab_model_a=stored.get("ab_model_a", defaults.ab_model_a),
        ab_model_b=stored.get("ab_model_b", defaults.ab_model_b),
    )


def save_settings(db: Session, values: RuntimeSettings) -> None:
    for key, value in vars(values).items():
        db.merge(Setting(key=key, value=str(value)))
    db.commit()


def load_slang(db: Session) -> dict[str, str]:
    return {row.term: row.replacement for row in db.scalars(select(SlangTerm))}
