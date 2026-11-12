@echo off
cd /d %~dp0

python ./main.py mov_001_480x270.mp4 mov_ht_001_480x270.mp4 bcsetting.csv degparam_mm.csv 0 simconf.csv 0 0 0 0 0 1
python ./main.py eval_img.png eval_img_ht.png bcsetting.csv degparam_mm.csv 0 simconf.csv 1_stat_r.csv 1_stat_g.csv 1_stat_b.csv 1 0 2

python ./main.py mov_001_480x270.mp4 mov_ht_001_480x270.mp4 bcsetting.csv degparam_mm.csv 0 simconf.csv 1_stat_r.csv 1_stat_g.csv 1_stat_b.csv 1 0 3
python ./main.py eval_img.png eval_img_ht.png bcsetting.csv degparam_mm.csv 0 simconf.csv 3_stat_r.csv 3_stat_g.csv 3_stat_b.csv 1 0 4

:: pause
