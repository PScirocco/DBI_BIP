# 旧コア（2026-11-17 まで bisim が使っていた劣化コア）

フェーズF で新コア（松井さん `Burn_in_sim_core_01`、`receive/` で受領）に差し替えたときに、旧コアをここに移した（2026-11-18）。
**bisim からは使わない（実行もしない）。** 比較・参照のために残している。Git のタグ `oldcore-baseline-261117` でも元の配置のまま取り出せる。

| ファイル | 元の場所 |
|---|---|
| `main.py`・`load_com_info.py` | `source/` |
| `eval_exec.bat`（旧コアのコマンドライン実行例） | `source/` |
| `dbi_input/bcsetting.csv`（旧形式。旧コアでは未使用） | `source/dbi_input/` |
| `dbi_conf/simconf.csv`・`dbi_conf/degparam_mm.csv` | `source/dbi_conf/`（mm は新コアの標準ファイルと同じ内容） |

旧コアでの基準データは `bisim2/eval_test/_baseline_oldcore_261117/`（Git 管理外）。
