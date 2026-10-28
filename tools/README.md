# tools — 評価用スクリプトと実行条件

bisim（BI-sim）の評価に使うスクリプト。**EXE には入っていない**ので、リポジトリから Python で実行する。

| スクリプト | 内容 |
|---|---|
| `make_rgbcircle_test.py` | 理論確認テスト（3色円）の入力一式とシーケンス `rgbcircle.seq.json` を作る |
| `rgbcircle_theory.py` | 理論値を計算し、`--compare` で bisim の出力と比べる |
| `rgbcircle_excel.py` | 理論値を Excel の数式で計算し、bisim の出力と比べるブックを作る（Excel があれば再計算まで行う） |
| `make_scale_test.py` | ⑤累積時間マップの表示スケール切替を確かめるサンプル `eval_test/scaletest/` を作る（白で Aging → 3色円で Aging → 白で評価。期待される見え方の画像つき） |
| `overlay_rgb_circles.py` | 動画に3色円を重ねる（試作用） |
| `_seqpaths.py` | 上の3つが共通で使う「フォルダの決め方」 |

---

## 実行条件

### 1. tools の実行のしかた

- **リポジトリの一番上のフォルダで**、リポジトリの `.venv` の Python で実行する
  ```
  cd <リポジトリ>
  .venv\Scripts\python tools\rgbcircle_theory.py ...
  ```
- コマンドに書く相対パス（`--seq dist\BI-sim\...` など）は、コマンドを打ったフォルダから見た場所になる。
  リポジトリの一番上で実行すれば、このページの例がそのまま使える

### 2. tools と BI-sim.exe の位置関係（ビルドしたときの構成を崩さない）

```
<リポジトリ>\                    ← 開発環境の bisim（python -m bisim）の基準フォルダ
  tools\                          ← tools のスクリプト
  eval_test\rgbcircle\            ← 開発環境用のテストデータ（Git 管理外）
  dist\BI-sim\                    ← EXE の基準フォルダ（installer\build_exe.ps1 が作る）
    BI-sim.exe
    eval_test\rgbcircle\          ← EXE 用のテストデータ（ここにコピーして使う）
```

- `installer\build_exe.ps1` は EXE を `<リポジトリ>\dist\BI-sim\` に作る。tools はこの位置関係を前提に
  `--app-dir dist\BI-sim` で EXE の基準フォルダを指定する。**EXE のフォルダを別の場所へ移した場合は、
  `--app-dir` にその場所を指定する**
- **注意：`build_exe.ps1` はビルドのたびに `dist\BI-sim\` を丸ごと消して作り直す。**
  EXE 用に置いたテストデータと結果も消えるので、ビルド後にコピーし直す（結果は先に退避しておく）

### 3. シーケンスに書くフォルダ（相対パス）の基準

- シーケンス（`*.seq.json`）の `folders` に書く**相対パスは、BI-sim.exe のフォルダから見たパス**
  （開発環境の `python -m bisim` ではリポジトリの一番上から見たパス）。絶対パスもそのまま使える
- 例：`"input_image": "eval_test/rgbcircle/input"`
  - 開発環境 → `<リポジトリ>\eval_test\rgbcircle\input`
  - EXE → `<リポジトリ>\dist\BI-sim\eval_test\rgbcircle\input`
- つまり、**基準フォルダの下に `eval_test\rgbcircle\` を同じ構成で置けば、パスを書き換えずに開ける**
- シーケンスに書かれていないフォルダ（BC設定・モデル・Sim）は、その bisim の既定フォルダになる
- bisim の画面（①フォルダ設定）で変えて保存すると、そのシーケンスは絶対パスで保存される

### 4. tools がフォルダを決める順番（`_seqpaths.py`）

1. コマンドで直接指定したフォルダ（`--input-dir` / `--bisim-out`）
2. シーケンスに書かれたフォルダ（相対パスは `--app-dir` が基準。指定しなければリポジトリの一番上）
3. 2 が見つからなければ、シーケンスファイルの横の `input` / `output`
   （別PCからシーケンスと結果をフォルダごと持ち帰った場合など）

---

## 使い方（理論確認テスト）

### 開発環境（python -m bisim）で確認する

```
.venv\Scripts\python tools\make_rgbcircle_test.py          # eval_test\rgbcircle\ を作る（作り直すときだけ）
python -m bisim                                            # 「シーケンスを開く…」→ eval_test\rgbcircle\rgbcircle.seq.json → 全ステップ実行
.venv\Scripts\python tools\rgbcircle_theory.py --compare   # 理論値と比較 → eval_test\rgbcircle\theory\rgbcircle_compare.md
.venv\Scripts\python tools\rgbcircle_excel.py              # Excel で検算 → eval_test\rgbcircle\理論値_Excel検算.xlsx
```

### EXE（BI-sim.exe）で確認する

```
（ビルド後）eval_test\rgbcircle を dist\BI-sim\eval_test\rgbcircle にフォルダごとコピー
dist\BI-sim\BI-sim.exe                                     # 「シーケンスを開く…」→ dist\BI-sim\eval_test\rgbcircle\rgbcircle.seq.json → 全ステップ実行

.venv\Scripts\python tools\rgbcircle_theory.py --app-dir dist\BI-sim ^
    --seq dist\BI-sim\eval_test\rgbcircle\rgbcircle.seq.json --compare
.venv\Scripts\python tools\rgbcircle_excel.py --app-dir dist\BI-sim ^
    --seq dist\BI-sim\eval_test\rgbcircle\rgbcircle.seq.json
```

### 別PCの結果を持ち帰って確認する

別PCの `eval_test\rgbcircle\` をフォルダごと（例：`eval_test_other-PC\rgbcircle\`）コピーし、`--seq` だけ指定する。
シーケンスに書かれたフォルダがこのPCで見つからないので、シーケンスの横の `input` / `output` が使われる。

```
.venv\Scripts\python tools\rgbcircle_theory.py --seq eval_test_other-PC\rgbcircle\rgbcircle.seq.json --compare --out <結果を置くフォルダ>
.venv\Scripts\python tools\rgbcircle_excel.py  --seq eval_test_other-PC\rgbcircle\rgbcircle.seq.json --out <xlsx>
```

結果の出力先は、指定しなければシーケンスの横（`theory\` と `理論値_Excel検算.xlsx`）。
持ち帰ったフォルダに別PCで作った結果が入っていて残したい場合は、`--out` で別の場所を指定する。
