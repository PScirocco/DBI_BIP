"""シーケンスを画面なしで実行（GUI の SimWorker と同じく run_sequence → write_recipe_outputs）。
使い方: python run_seq_headless.py <bisim2のパス> <seq.json> <出力フォルダ>"""
import sys, time
from pathlib import Path
app = Path(sys.argv[1]); sys.path.insert(0, str(app))
from bisim import engine
from bisim.model import Sequence
seq = Sequence.load(sys.argv[2])
seq.folders["output"] = str(Path(sys.argv[3]).resolve())
model = engine.CoreModel()
t0 = time.time()
def done(res):
    engine.write_recipe_outputs(result=res, folders=seq.folders, sequence_name=seq.sequence_name,
                                model=model, model_param=seq.recipes[int(res.nn) - 1].model_param)
    print(f"  {res.nn}_{res.recipe_name}: frames={res.frames_done if hasattr(res,'frames_done') else '-'} "
          f"aging={engine.format_aging(res.aging_seconds)} 累積={engine.format_aging(res.cumulative_aging_seconds)} "
          f"({time.time()-t0:.0f}s)", flush=True)
res = engine.run_sequence(sequence=seq, model=model, step_done_cb=done)
print("stopped" if any(r.stopped for r in res) else "完了", f"{time.time()-t0:.0f}s")
