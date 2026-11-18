"""データモデル（仕様 3）: Recipe / Sequence / AppConfig

すべて JSON で load / save。日本語をそのまま残すため ``ensure_ascii=False``。
Recipe は単体でも保存・再利用できる（仕様 3.3）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from bisim.paths import APP_DIR, DEFAULT_FOLDERS, FOLDER_KEYS, STD_BCSET, STD_DEGPARAM_SM

# ---- 既定値（dbi_conf の現行値。CLI 版と同じ）----
MODEL_KEYS = ["N", "K0", "Q", "B0", "A"]      # 各 [R, G, B]
# Sim 条件（simconf.csv 相当。ステップごとに設定する）。DBV_NIT・DPK_ON・GADJ は新コア（フェーズF）で追加
SIM_KEYS = ["AGING_TIME", "ACCEL_RATIO", "TMP_L", "TMP_H", "DBV_NIT", "DPK_ON", "GADJ"]
SIM_RGB_KEYS = ("GADJ",)       # 値が [R, G, B] の3つ
SIM_INT_KEYS = ("DPK_ON",)     # 整数（0/1）

DEFAULT_MODEL: dict[str, list[float]] = {
    "N":  [1.5, 1.3, 1.7],
    "K0": [500.0, 1000.0, 100.0],
    "Q":  [1000.0, 800.0, 600.0],
    "B0": [0.7, 0.8, 0.4],
    "A":  [0.0, 0.0, 0.0],
}
DEFAULT_SIM: dict = {
    # 目標 Aging 時間 [秒]（仕様 5-③）。超過なら打切り、不足なら動画を周回連結して埋める。
    # 既定 0 ＝無制限（＝従来どおり動画を1周回のみ処理。明示的に設定するまでは無効）
    "AGING_TIME": 0.0,
    "ACCEL_RATIO": 30000.0,
    "TMP_L": 25.0,
    "TMP_H": 60.0,
    # 新コアの表示条件（2026-11-17 決定の既定値）。PQ評価のステップでも使う
    "DBV_NIT": 2000.0,         # パネルの輝度設定（DBV を輝度[nit]で指定）
    "DPK_ON": 0,               # DPK モード 1=ON / 0=OFF
    "GADJ": [1.0, 1.0, 1.0],   # 電流調整（GI_LUT の電流を何倍にするか。R/G/B）
}


def parse_sim_value(key: str, value):
    """Sim 条件1項目の値を正しい型にする（``GADJ``＝3つの float、``DPK_ON``＝0/1、他＝float）。

    変換できなければ ``ValueError``。
    """
    if key in SIM_RGB_KEYS:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError(f"{key} は R/G/B の3つの値: {value!r}")
        return [float(x) for x in value]
    if key in SIM_INT_KEYS:
        v = int(float(value))
        if v not in (0, 1):
            raise ValueError(f"{key} は 0 か 1: {value!r}")
        return v
    return float(value)


def parse_model_param(d) -> dict:
    """mm（マスターモデル）の辞書を読み込む。欠け・不正な項目は既定値で補う。"""
    model = _fresh_model()
    for k, v in (d or {}).items():
        if k in MODEL_KEYS and isinstance(v, (list, tuple)) and len(v) == 3:
            model[k] = [float(x) for x in v]
    return model

INIT_STRESS = ("none", "prev", "file")
# ステップ種別（手動選択）: aging＝ストレスを貯める / eval＝貯めない（劣化後の見え方だけ作る）
STEP_TYPES = ("aging", "eval")
HEATMAP_MODES = ("file", "fixed")     # fixed = ヒートマップなし・パネル全面を固定温度

CHECKPOINT_ROOT = "_stops"     # 出力フォルダ配下の停止チェックポイント置き場

SEQ_EXT = ".seq.json"
RECIPE_EXT = ".recipe.json"


def _fresh_model() -> dict[str, list[float]]:
    return {k: list(v) for k, v in DEFAULT_MODEL.items()}


def _fresh_sim() -> dict:
    return {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_SIM.items()}


def _fresh_folders() -> dict[str, str]:
    return {k: str(v) for k, v in DEFAULT_FOLDERS.items()}


def _write_json(path, obj) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
@dataclass
class StopState:
    """1ステップの停止状態（仕様 7）。実データ（stat/deg CSV・途中動画）は

    ``<output>/_stops/<dir>/`` に素のファイル名で置き、``Sequence.stops`` が
    これを参照する（別ファイルのサイドカーは廃止）。``numpy`` を持たないので
    ``model`` に置ける（``engine`` → ``model`` の一方向 import を保つ）。
    """

    recipe_name: str = ""
    frames_done: int = 0            # 停止までに処理した絶対フレーム数
    frames_total: int = 0
    aging_seconds: float = 0.0      # 停止までの加速込み Aging 時間
    is_movie: bool = False
    timestamp: str = ""             # YYMMDD-HHMM（保存時刻。表示用）
    dir: str = ""                   # 出力フォルダからの相対（例 "_stops/SEQ_01_aging01"）

    def to_dict(self) -> dict:
        return {
            "recipe_name": self.recipe_name,
            "frames_done": self.frames_done,
            "frames_total": self.frames_total,
            "aging_seconds": self.aging_seconds,
            "is_movie": self.is_movie,
            "timestamp": self.timestamp,
            "dir": self.dir,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StopState":
        return cls(
            recipe_name=str(d.get("recipe_name", "")),
            frames_done=int(d.get("frames_done", 0)),
            frames_total=int(d.get("frames_total", 0)),
            aging_seconds=float(d.get("aging_seconds", 0.0)),
            is_movie=bool(d.get("is_movie", False)),
            timestamp=str(d.get("timestamp", "")),
            dir=str(d.get("dir", "")),
        )


def default_step_type(input_image: str) -> str:
    """種別が未指定のときの既定（旧仕様の拡張子判定と同じ）: .png→eval、それ以外→aging。"""
    return "eval" if Path(input_image or "").suffix.lower() == ".png" else "aging"


# --------------------------------------------------------------------------- #
@dataclass
class Recipe:
    """1つの処理ステップの定義（仕様 3.3）。"""

    recipe_name: str = "recipe"
    input_image: str = ""                 # ファイル名のみ
    heatmap: str = ""
    heatmap_mode: str = "file"            # file | fixed（ヒートマップなし・固定温度）
    fixed_temp_c: float = 25.0            # heatmap_mode="fixed" のときのパネル全面温度[℃]
    # マスターモデルのパラメータ（mm）はフェーズF からシーケンスのパネル設定（PanelConfig）に移した
    # （mm・sm は機種ごと。2026-11-18 決定）。旧 JSON の model_param は Sequence.from_dict が移す
    sim_param: dict = field(default_factory=_fresh_sim)
    sim_param_csv: str = ""
    init_stress: str = "none"             # none | prev | file
    init_stress_files: dict = field(default_factory=dict)      # {"r":name,...} for "file"
    # ステップ種別（"aging" | "eval"）。入力が動画か静止画かとは独立に手動で選ぶ。
    # 空のまま作ると入力ファイルの拡張子から決める（.png→eval、それ以外→aging）。
    # 種別の欄が無い旧 JSON も同じ規則で読み込むので、従来のシーケンスは同じ動作になる。
    step_type: str = ""
    # サブモデル（degparam_sm.csv）をこのステップだけ差し替える（任意。①のモデルフォルダのファイル名）。
    # 空＝シーケンスのパネル設定の sm。表示（deg2）だけに効き、stat には影響しない（2026-11-18 決定）
    sm_override: str = ""

    def __post_init__(self) -> None:
        if self.step_type not in STEP_TYPES:
            self.step_type = default_step_type(self.input_image)

    @property
    def kind(self) -> str:
        """ステップ種別（``step_type`` と同じ。UI 表示・判定用の別名）。"""
        return self.step_type

    @property
    def is_eval(self) -> bool:
        return self.step_type == "eval"

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.recipe_name.strip():
            problems.append("recipe_name が空")
        if self.init_stress not in INIT_STRESS:
            problems.append(f"init_stress が不正: {self.init_stress!r}")
        if self.heatmap_mode not in HEATMAP_MODES:
            problems.append(f"heatmap_mode が不正: {self.heatmap_mode!r}")
        if self.step_type not in STEP_TYPES:
            problems.append(f"step_type が不正: {self.step_type!r}")
        for k in SIM_KEYS:
            if k not in self.sim_param:
                problems.append(f"sim_param[{k}] が無い")
                continue
            try:
                parse_sim_value(k, self.sim_param[k])
            except (TypeError, ValueError):
                problems.append(f"sim_param[{k}] が不正: {self.sim_param[k]!r}")
        if self.init_stress == "file":
            for c in ("r", "g", "b"):
                if not self.init_stress_files.get(c):
                    problems.append(f"init_stress_files[{c}] が無い")
        return problems

    def to_dict(self) -> dict:
        return {
            "recipe_name": self.recipe_name,
            "step_type": self.step_type,
            "input_image": self.input_image,
            "heatmap": self.heatmap,
            "heatmap_mode": self.heatmap_mode,
            "fixed_temp_c": self.fixed_temp_c,
            "sim_param": {k: (list(v) if isinstance(v, (list, tuple)) else v)
                          for k, v in self.sim_param.items()},
            "sim_param_csv": self.sim_param_csv,
            "sm_override": self.sm_override,
            "init_stress": self.init_stress,
            "init_stress_files": dict(self.init_stress_files),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        sim = _fresh_sim()
        for k, v in (d.get("sim_param") or {}).items():
            if k in SIM_KEYS:
                try:
                    sim[k] = parse_sim_value(k, v)
                except (TypeError, ValueError):
                    pass                         # 不正な値は既定値のまま
        init = d.get("init_stress", "none")
        if init not in INIT_STRESS:
            init = "none"
        ht_mode = d.get("heatmap_mode", "file")
        if ht_mode not in HEATMAP_MODES:
            ht_mode = "file"
        try:
            fixed_temp_c = float(d.get("fixed_temp_c", 25.0))
        except (TypeError, ValueError):
            fixed_temp_c = 25.0
        step_type = d.get("step_type", "")
        if step_type not in STEP_TYPES:
            step_type = ""                   # 旧 JSON：拡張子から決める（__post_init__）
        return cls(
            recipe_name=str(d.get("recipe_name", "recipe")),
            step_type=step_type,
            input_image=str(d.get("input_image", "")),
            heatmap=str(d.get("heatmap", "")),
            heatmap_mode=ht_mode,
            fixed_temp_c=fixed_temp_c,
            sim_param=sim,
            sim_param_csv=str(d.get("sim_param_csv", "")),
            sm_override=str(d.get("sm_override", "") or ""),
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
class PanelConfig:
    """パネル設定（フェーズF）。シーケンスに1組（2026-11-17・11-18 決定）。

    - 機種（劣化モデル）：マスターモデルの数値 ``model_param``（mm）、サブモデル ``degparam_sm``
    - 個体（BC設定）：``bcsetting``
    ファイルはファイル名だけを持ち、フォルダは ①の「BC設定」（bcsetting）・「モデル」（sm）。
    """

    bcsetting: str = STD_BCSET.name
    degparam_sm: str = STD_DEGPARAM_SM.name
    model_param: dict = field(default_factory=_fresh_model)
    model_param_csv: str = ""             # mm を読み込んだ／保存した CSV のファイル名（表示用）

    def to_dict(self) -> dict:
        return {
            "bcsetting": self.bcsetting,
            "degparam_sm": self.degparam_sm,
            "model_param": {k: list(v) for k, v in self.model_param.items()},
            "model_param_csv": self.model_param_csv,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PanelConfig":
        return cls(
            bcsetting=str(d.get("bcsetting") or STD_BCSET.name),
            degparam_sm=str(d.get("degparam_sm") or STD_DEGPARAM_SM.name),
            model_param=parse_model_param(d.get("model_param")),
            model_param_csv=str(d.get("model_param_csv", "")),
        )


# --------------------------------------------------------------------------- #
@dataclass
class Sequence:
    """どのレシピをどの順で実行するか（仕様 3.2）。＝実行シーケンスConfig。"""

    sequence_name: str = "sequence"
    folders: dict = field(default_factory=_fresh_folders)
    recipes: list = field(default_factory=list)   # list[Recipe]
    stops: dict = field(default_factory=dict)     # NN文字列 -> StopState（停止状態を内包）
    panel: PanelConfig = field(default_factory=PanelConfig)
    # 読み込み時の注意（旧形式からの移行など）。保存しない。画面側がログに出す
    load_warnings: list = field(default_factory=list, compare=False, repr=False)

    @staticmethod
    def recipe_number(index: int) -> str:
        """0始まりのインデックス → 出力名の NN（1始まり2桁）。"""
        return f"{index + 1:02d}"

    def index_of(self, recipe: "Recipe") -> int:
        return self.recipes.index(recipe)

    # ---- パネル設定のファイル ----
    def bcset_path(self) -> Path:
        return Path(self.folders["bcset"]) / self.panel.bcsetting

    def sm_path(self, index: "int | None" = None) -> Path:
        """サブモデルのパス。``index`` のステップに差し替え（``sm_override``）があればそちら。"""
        name = self.panel.degparam_sm
        if index is not None and 0 <= index < len(self.recipes) and self.recipes[index].sm_override:
            name = self.recipes[index].sm_override
        return Path(self.folders["model"]) / name

    def use_standard_panel_folders_if_missing(self) -> list:
        """パネル設定のファイルがフォルダに無く、名前が標準ファイルと同じなら、標準のフォルダに切り替える。

        別PCの ``bisim_app.json`` に古い既定フォルダが残っている場合などの救済。戻り値は変えた内容（ログ用）。
        """
        msgs = []
        for key, name, std in (("bcset", self.panel.bcsetting, STD_BCSET),
                               ("model", self.panel.degparam_sm, STD_DEGPARAM_SM)):
            folder = Path(self.folders.get(key, ""))
            if (folder / name).is_file() or name != std.name or not std.is_file():
                continue
            self.folders[key] = str(std.parent)
            msgs.append(f"{name} が {folder} に無いため、標準のフォルダ {std.parent} にしました")
        return msgs

    def to_dict(self) -> dict:
        d = {
            "sequence_name": self.sequence_name,
            "folders": {k: str(self.folders.get(k, "")) for k in FOLDER_KEYS},
            "panel": self.panel.to_dict(),
            "recipes": [r.to_dict() for r in self.recipes],
        }
        if self.stops:
            d["stops"] = {nn: st.to_dict() for nn, st in sorted(self.stops.items())}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Sequence":
        folders = _fresh_folders()
        for k, v in (d.get("folders") or {}).items():
            if k in FOLDER_KEYS:
                folders[k] = str(v)
        raw_recipes = [r for r in (d.get("recipes") or []) if isinstance(r, dict)]
        recipes = [Recipe.from_dict(r) for r in raw_recipes]
        stops = {str(nn): StopState.from_dict(sd)
                 for nn, sd in (d.get("stops") or {}).items()
                 if isinstance(sd, dict)}
        warnings: list = []
        if isinstance(d.get("panel"), dict):
            panel = PanelConfig.from_dict(d["panel"])
        else:
            panel, warnings = cls._migrate_panel(raw_recipes, folders)
        return cls(
            sequence_name=str(d.get("sequence_name", "sequence")),
            folders=folders,
            recipes=recipes,
            stops=stops,
            panel=panel,
            load_warnings=warnings,
        )

    @staticmethod
    def _migrate_panel(raw_recipes: list, folders: dict) -> tuple:
        """パネル設定の無い旧 JSON（フェーズF より前）を読み込む（2026-11-17 決定）。

        - bcsetting・sm は標準ファイル。BC設定・モデルのフォルダも標準のフォルダにする
          （旧形式の bcsetting.csv が置かれたフォルダを指していることがあるため）
        - mm はステップの ``model_param`` から。ステップごとに違えば1番目を採用して警告
        """
        panel = PanelConfig()
        warnings = ["旧形式のシーケンス：パネル設定に標準ファイルを割り当てました"
                    f"（{STD_BCSET.name}・{STD_DEGPARAM_SM.name}、フォルダ {STD_BCSET.parent}）"]
        folders["bcset"] = str(STD_BCSET.parent)
        folders["model"] = str(STD_DEGPARAM_SM.parent)
        mms = [parse_model_param(r.get("model_param")) for r in raw_recipes]
        if mms:
            panel.model_param = mms[0]
            panel.model_param_csv = str(raw_recipes[0].get("model_param_csv", "") or "")
            differ = [i + 1 for i, m in enumerate(mms) if m != mms[0]]
            if differ:
                warnings.append(
                    "ステップごとにモデルパラメータ（mm）が違っていたため、1番目のステップの値を採用しました"
                    f"（違っていたステップ：{', '.join(f'{n:02d}' for n in differ)}）")
        return panel, warnings

    def save(self, path) -> None:
        _write_json(path, self.to_dict())

    @classmethod
    def load(cls, path) -> "Sequence":
        seq = cls.from_dict(_read_json(path))
        seq.resolve_relative_folders(APP_DIR)
        seq.load_warnings.extend(seq.use_standard_panel_folders_if_missing())
        return seq

    def resolve_relative_folders(self, base) -> None:
        """``folders`` の相対パスを、``base`` 基準の絶対パスにする（既定は ``APP_DIR``）。

        ``APP_DIR`` は EXE では bisim.exe のフォルダ、開発時はリポジトリ直下。
        シーケンスファイルには ``"eval_test/rgbcircle/input"`` のような相対パスも書けるので、
        別PCでも bisim.exe のフォルダの下に同じ構成でデータを置けば、パスを書き換えずに使える
        （例：tool/make_rgbcircle_test.py が作るシーケンス）。絶対パスはそのまま。
        JSON に無いフォルダは、そのPC（EXE）の既定フォルダになる（``from_dict``）。
        保存時は絶対パスで書き出す。
        """
        for k, v in list(self.folders.items()):
            if v and not Path(v).is_absolute():
                self.folders[k] = str((Path(base) / v).resolve())


# --------------------------------------------------------------------------- #
@dataclass
class AppConfig:
    """アプリ全体の設定（仕様 3.1）。実行シーケンスとは別ファイル。"""

    log_max_mb: float = 50.0
    language: str = "en"        # リリースは英語（仕様 2）
    default_folders: dict = field(default_factory=dict)   # 直近使用した6フォルダ（新規シーケンスの初期値）

    def to_dict(self) -> dict:
        d = {"log_max_mb": self.log_max_mb, "language": self.language}
        if self.default_folders:
            d["default_folders"] = {k: str(v) for k, v in self.default_folders.items()
                                    if k in FOLDER_KEYS}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        cfg = cls()
        try:
            cfg.log_max_mb = float(d.get("log_max_mb", cfg.log_max_mb))
        except (TypeError, ValueError):
            pass
        lang = str(d.get("language", cfg.language))
        cfg.language = lang if lang in ("ja", "en") else cfg.language
        cfg.default_folders = {k: str(v) for k, v in (d.get("default_folders") or {}).items()
                               if k in FOLDER_KEYS}
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
