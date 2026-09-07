"""データモデル（仕様 3）: Recipe / Sequence / AppConfig

すべて JSON で load / save。日本語をそのまま残すため ``ensure_ascii=False``。
Recipe は単体でも保存・再利用できる（仕様 3.3）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from bisim.paths import DEFAULT_FOLDERS, FOLDER_KEYS

# ---- 既定値（dbi_conf の現行値。CLI 版と同じ）----
MODEL_KEYS = ["N", "K0", "Q", "B0", "A"]      # 各 [R, G, B]
SIM_KEYS = ["AGING_TIME", "ACCEL_RATIO", "TMP_L", "TMP_H"]

DEFAULT_MODEL: dict[str, list[float]] = {
    "N":  [1.5, 1.3, 1.7],
    "K0": [500.0, 1000.0, 100.0],
    "Q":  [1000.0, 800.0, 600.0],
    "B0": [0.7, 0.8, 0.4],
    "A":  [0.0, 0.0, 0.0],
}
DEFAULT_SIM: dict[str, float] = {
    "AGING_TIME": 10.0,      # 現状 未使用（仕様 5-③, 9）
    "ACCEL_RATIO": 30000.0,
    "TMP_L": 25.0,
    "TMP_H": 60.0,
}

INIT_STRESS = ("none", "prev", "file")

SEQ_EXT = ".seq.json"
RECIPE_EXT = ".recipe.json"


def _fresh_model() -> dict[str, list[float]]:
    return {k: list(v) for k, v in DEFAULT_MODEL.items()}


def _fresh_sim() -> dict[str, float]:
    return dict(DEFAULT_SIM)


def _fresh_folders() -> dict[str, str]:
    return {k: str(v) for k, v in DEFAULT_FOLDERS.items()}


def _write_json(path, obj) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
@dataclass
class Recipe:
    """1つの処理ステップの定義（仕様 3.3）。"""

    recipe_name: str = "recipe"
    input_image: str = ""                 # ファイル名のみ
    heatmap: str = ""
    model_param: dict = field(default_factory=_fresh_model)    # インライン値
    model_param_csv: str = ""             # 参照CSVファイル名（CLI互換・任意）
    sim_param: dict = field(default_factory=_fresh_sim)
    sim_param_csv: str = ""
    init_stress: str = "none"             # none | prev | file
    init_stress_files: dict = field(default_factory=dict)      # {"r":name,...} for "file"

    @property
    def kind(self) -> str:
        ext = Path(self.input_image).suffix.lower()
        return {".mp4": "aging", ".png": "pq"}.get(ext, "unknown")

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.recipe_name.strip():
            problems.append("recipe_name が空")
        if self.init_stress not in INIT_STRESS:
            problems.append(f"init_stress が不正: {self.init_stress!r}")
        for k in MODEL_KEYS:
            v = self.model_param.get(k)
            if not (isinstance(v, list) and len(v) == 3):
                problems.append(f"model_param[{k}] は3要素リストであること")
        for k in SIM_KEYS:
            if k not in self.sim_param:
                problems.append(f"sim_param[{k}] が無い")
        if self.init_stress == "file":
            for c in ("r", "g", "b"):
                if not self.init_stress_files.get(c):
                    problems.append(f"init_stress_files[{c}] が無い")
        return problems

    def to_dict(self) -> dict:
        return {
            "recipe_name": self.recipe_name,
            "input_image": self.input_image,
            "heatmap": self.heatmap,
            "model_param": {k: list(v) for k, v in self.model_param.items()},
            "model_param_csv": self.model_param_csv,
            "sim_param": dict(self.sim_param),
            "sim_param_csv": self.sim_param_csv,
            "init_stress": self.init_stress,
            "init_stress_files": dict(self.init_stress_files),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        model = _fresh_model()
        for k, v in (d.get("model_param") or {}).items():
            if k in MODEL_KEYS and isinstance(v, (list, tuple)) and len(v) == 3:
                model[k] = [float(x) for x in v]
        sim = _fresh_sim()
        for k, v in (d.get("sim_param") or {}).items():
            if k in SIM_KEYS:
                sim[k] = float(v)
        init = d.get("init_stress", "none")
        if init not in INIT_STRESS:
            init = "none"
        return cls(
            recipe_name=str(d.get("recipe_name", "recipe")),
            input_image=str(d.get("input_image", "")),
            heatmap=str(d.get("heatmap", "")),
            model_param=model,
            model_param_csv=str(d.get("model_param_csv", "")),
            sim_param=sim,
            sim_param_csv=str(d.get("sim_param_csv", "")),
            init_stress=init,
            init_stress_files=dict(d.get("init_stress_files") or {}),
        )

    def save(self, path) -> None:
        _write_json(path, self.to_dict())

    @classmethod
    def load(cls, path) -> "Recipe":
        return cls.from_dict(_read_json(path))


# --------------------------------------------------------------------------- #
@dataclass
class Sequence:
    """どのレシピをどの順で実行するか（仕様 3.2）。＝実行シーケンスConfig。"""

    sequence_name: str = "sequence"
    folders: dict = field(default_factory=_fresh_folders)
    recipes: list = field(default_factory=list)   # list[Recipe]

    @staticmethod
    def recipe_number(index: int) -> str:
        """0始まりのインデックス → 出力名の NN（1始まり2桁）。"""
        return f"{index + 1:02d}"

    def index_of(self, recipe: "Recipe") -> int:
        return self.recipes.index(recipe)

    def to_dict(self) -> dict:
        return {
            "sequence_name": self.sequence_name,
            "folders": {k: str(self.folders.get(k, "")) for k in FOLDER_KEYS},
            "recipes": [r.to_dict() for r in self.recipes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Sequence":
        folders = _fresh_folders()
        for k, v in (d.get("folders") or {}).items():
            if k in FOLDER_KEYS:
                folders[k] = str(v)
        recipes = [Recipe.from_dict(r) for r in (d.get("recipes") or [])
                   if isinstance(r, dict)]
        return cls(
            sequence_name=str(d.get("sequence_name", "sequence")),
            folders=folders,
            recipes=recipes,
        )

    def save(self, path) -> None:
        _write_json(path, self.to_dict())

    @classmethod
    def load(cls, path) -> "Sequence":
        return cls.from_dict(_read_json(path))


# --------------------------------------------------------------------------- #
@dataclass
class AppConfig:
    """アプリ全体の設定（仕様 3.1）。実行シーケンスとは別ファイル。"""

    log_max_mb: float = 50.0
    language: str = "en"        # リリースは英語（仕様 2）

    def to_dict(self) -> dict:
        return {"log_max_mb": self.log_max_mb, "language": self.language}

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        cfg = cls()
        try:
            cfg.log_max_mb = float(d.get("log_max_mb", cfg.log_max_mb))
        except (TypeError, ValueError):
            pass
        lang = str(d.get("language", cfg.language))
        cfg.language = lang if lang in ("ja", "en") else cfg.language
        return cfg

    def save(self, path) -> None:
        _write_json(path, self.to_dict())

    @classmethod
    def load(cls, path) -> "AppConfig":
        return cls.from_dict(_read_json(path))

    @classmethod
    def load_or_default(cls, path) -> "AppConfig":
        p = Path(path)
        return cls.load(p) if p.exists() else cls()
