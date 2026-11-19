# tool — 作業実行スクリプトと実行条件

bisim（BI-sim）の評価などに使うスクリプト。**EXE には入っていない**ので、Python で実行する。
（2026-11-12 のフォルダ再編で、旧 `tools/` を `Burn-In_Simv2\tool\` に移した。2026-11-19 に理論確認テストを新コアの式に作り直した。
旧コアの式の版は Git のタグ `oldcore-baseline-261117` にある）

| スクリプト | 内容 |
|---|---|
| `make_rgbcircle_test.py` | 理論確認テスト（3色円）の入力一式とシーケンス `rgbcircle.seq.json` を作る（パネル設定は標準ファイル、DBV_NIT=2000・DPK_ON=0） |
| `rgbcircle_theory.py` | 理論値を計算し、`--compare` で bisim の出力と比べる（stat・deg・deg2・評価画像）。新コアの式とパネル設定ファイルの読み込みを、コアとは別に実装（固定温度・DPK_ON=0 に対応） |
| `rgbcircle_excel.py` | 理論値を Excel の数式で計算し、bisim の出力と比べるブックを作る（Excel があれば再計算まで行う）。サブモデルの表の補間も数式で計算 |
| `make_scale_test.py` | ⑤累積時間マップの表示スケール切替を確かめるサンプル `bisim2\eval_test\scaletest\` を作る（白で Aging → 3色円で Aging → 白で評価。期待される見え方の画像つき） |
| `overlay_rgb_circles.py` | 動画に3色円を重ねる（試作用） |
| `_seqpaths.py` | 上の3つが共通で使う「フォルダの決め方」 |
| `phaseF/` | フェーズF（新コアの組み込み）の確認用スクリプト。結合試験（松井さんの動作確認 11 ケースの再現）など。`phaseF/README.md` |

---

## 実行条件

### 1. tool の実行のしかた

- **`Burn-In_Simv2` の一番上のフォルダで**、`bisim2\.venv` の Python で実行する
  ```
  cd C:\Users\h84431495\LLM\Burn-In_Simv2
  bisim2\.venv\Scripts\python tool\rgbcircle_theory.py ...
  ```
- コマンドに書く相対パス（`--seq bisim2\dist\BI-sim\...` など）は、コマンドを打ったフォルダから見た場所になる。
  `Burn-In_Simv2` の一番上で実行すれば、このページの例がそのまま使える
- **スクリプトは「自分の1つ上のフォルダの `bisim2\`」を bisim 本体の場所として使う**（各スクリプトの `REPO`）。
  `bisim` のコード（ファイル名の規則など）もそこから読み込む。**`tool\` と `bisim2\` は同じフォルダの下に並べておく**
  （別PCで tool を使う場合も、`<どこか>\tool\` と `<どこか>\bisim2\` の並びにする）

### 2. フォルダの位置関係（ビルドしたときの構成を崩さない）

```
Burn-In_Simv2\
  tool\                             ← このスクリプト
  bisim2\                           ← 開発環境の bisim（python -m bisim）の基準フォルダ
    .venv\                          ← Python 環境（tool もこれで実行）
    bisim\  source\  installer\
    eval_test\rgbcircle\            ← 開発環境用のテストデータ（Git 管理外）
    dist\BI-sim\                    ← EXE の基準フォルダ（bisim2\installer\build_exe.ps1 が作る）
      BI-sim.exe
      eval_test\rgbcircle\          ← EXE 用のテストデータ（ここにコピーして使う）
```

- `installer\build_exe.ps1` は EXE を `bisim2\dist\BI-sim\` に作る。tool はこの位置関係を前提に
  `--app-dir bisim2\dist\BI-sim` で EXE の基準フォルダを指定する。**EXE のフォルダを別の場所へ移した場合は、
  `--app-dir` にその場所を指定する**
- **注意：`build_exe.ps1` はビルドのたびに `dist\BI-sim\` を丸ごと消して作り直す。**
  EXE 用に置いたテストデータと結果も消えるので、ビルド後にコピーし直す（結果は先に退避しておく）

### 3. シーケンスに書くフォルダ（相対パス）の基準

- シーケンス（`*.seq.json`）の `folders` に書く**相対パスは、BI-sim.exe のフォルダから見たパス**
  （開発環境の `python -m bisim` では `bisim2\` から見たパス）。絶対パスもそのまま使える
- 例：`"input_image": "eval_test/rgbcircle/input"`
  - 開発環境 → `Burn-In_Simv2\bisim2\eval_test\rgbcircle\input`
  - EXE → `Burn-In_Simv2\bisim2\dist\BI-sim\eval_test\rgbcircle\input`
- つまり、**基準フォルダの下に `eval_test\rgbcircle\` を同じ構成で置けば、パスを書き換えずに開ける**
- シーケンスに書かれていないフォルダ（BC設定・モデル・Sim）は、その bisim の既定フォルダになる
- bisim の画面（①フォルダ設定）で変えて保存すると、そのシーケンスは絶対パスで保存される

### 4. tool がフォルダを決める順番（`_seqpaths.py`）

1. コマンドで直接指定したフォルダ（`--input-dir` / `--bisim-out`）
2. シーケンスに書かれたフォルダ（相対パスは `--app-dir` が基準。指定しなければ `bisim2\`）
3. 2 が見つからなければ、シーケンスファイルの横の `input` / `output`
   （別PCからシーケンスと結果をフォルダごと持ち帰った場合など）

---

## 使い方（理論確認テスト）

以下はすべて `Burn-In_Simv2` の一番上で実行する。

### 開発環境（python -m bisim）で確認する

```
bisim2\.venv\Scripts\python tool\make_rgbcircle_test.py          # bisim2\eval_test\rgbcircle\ を作る（作り直すときだけ）
cd bisim2 & .venv\Scripts\python -m bisim & cd ..                # 「シーケンスを開く…」→ eval_test\rgbcircle\rgbcircle.seq.json → 全ステップ実行
bisim2\.venv\Scripts\python tool\rgbcircle_theory.py --compare   # 理論値と比較 → bisim2\eval_test\rgbcircle\theory\rgbcircle_compare.md
bisim2\.venv\Scripts\python tool\rgbcircle_excel.py              # Excel で検算 → bisim2\eval_test\rgbcircle\理論値_Excel検算.xlsx
```

### EXE（BI-sim.exe）で確認する

```
（ビルド後）bisim2\eval_test\rgbcircle を bisim2\dist\BI-sim\eval_test\rgbcircle にフォルダごとコピー
bisim2\dist\BI-sim\BI-sim.exe                                    # 「シーケンスを開く…」→ bisim2\dist\BI-sim\eval_test\rgbcircle\rgbcircle.seq.json → 全ステップ実行

bisim2\.venv\Scripts\python tool\rgbcircle_theory.py --app-dir bisim2\dist\BI-sim ^
    --seq bisim2\dist\BI-sim\eval_test\rgbcircle\rgbcircle.seq.json --compare
bisim2\.venv\Scripts\python tool\rgbcircle_excel.py --app-dir bisim2\dist\BI-sim ^
    --seq bisim2\dist\BI-sim\eval_test\rgbcircle\rgbcircle.seq.json
```

### 別PCの結果を持ち帰って確認する

別PCの `eval_test\rgbcircle\` をフォルダごと（例：`bisim2\eval_test_other-PC\rgbcircle\`）コピーし、`--seq` だけ指定する。
シーケンスに書かれたフォルダがこのPCで見つからないので、シーケンスの横の `input` / `output` が使われる。

```
bisim2\.venv\Scripts\python tool\rgbcircle_theory.py --seq bisim2\eval_test_other-PC\rgbcircle\rgbcircle.seq.json --compare --out <結果を置くフォルダ>
bisim2\.venv\Scripts\python tool\rgbcircle_excel.py  --seq bisim2\eval_test_other-PC\rgbcircle\rgbcircle.seq.json --out <xlsx>
```

結果の出力先は、指定しなければシーケンスの横（`theory\` と `理論値_Excel検算.xlsx`）。
持ち帰ったフォルダに別PCで作った結果が入っていて残したい場合は、`--out` で別の場所を指定する。

パネル設定ファイル（bcsetting・degparam_sm）は、シーケンスの `panel` のファイル名と `folders` の BC設定・モデルのフォルダから決める
（書かれていなければ bisim の標準フォルダ `bisim2\source\dbi_conf`）。`--bcset`・`--sm` で直接指定もできる。
別PCの EXE で実行した結果を比べるとき、そのPCでパネル設定を変えていたら、同じファイルを `--bcset`・`--sm` で指定する。
