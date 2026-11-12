@echo off
cd /d %~dp0

python ./main.py eval_img1.png eval_img_ht1.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_2000_aging.csv 0 0 0 0 0 1
python ./main.py eval_img2.png eval_img_ht2.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_2000_test.csv 1_stat_r.csv 1_stat_g.csv 1_stat_b.csv 1 0 2
python ./main.py eval_img2.png eval_img_ht2.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_200_test.csv 1_stat_r.csv 1_stat_g.csv 1_stat_b.csv 1 0 3

python ./main.py eval_img1.png eval_img_ht1.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_1000_aging.csv 0 0 0 0 0 4
python ./main.py eval_img2.png eval_img_ht2.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_2000_test.csv 4_stat_r.csv 4_stat_g.csv 4_stat_b.csv 1 0 5

python ./main.py eval_img3.png eval_img_ht3.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_6500_aging.csv 0 0 0 0 0 6
python ./main.py eval_img4.png eval_img_ht4.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_6500_test.csv 6_stat_r.csv 6_stat_g.csv 6_stat_b.csv 1 0 7

python ./main.py eval_img3.png eval_img_ht3.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_6500_aging_dpk0.csv 0 0 0 0 0 8
python ./main.py eval_img4.png eval_img_ht4.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_6500_test_dpk0.csv 8_stat_r.csv 8_stat_g.csv 8_stat_b.csv 1 0 9

python ./main.py eval_img1.png eval_img_ht1.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_2000_aging_tmp60.csv 0 0 0 0 0 10
python ./main.py eval_img2.png eval_img_ht2.png bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_2000_test_tmp60.csv 10_stat_r.csv 10_stat_g.csv 10_stat_b.csv 1 0 11

:: pause
