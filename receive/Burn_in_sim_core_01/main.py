""" 劣化シミュレータ
    パネル表示の調整情報(BC settings(Band設定，GI_Lut等))とパネルの劣化特性(Degradation Master / Sub Model)を前提情報とし，
    入力画像(input image)と入力画像により発生する熱分布情報(heat map image)に対して，
    パネル点灯条件，Sim実行条件(Sim condition setting)の設定値の元でパネルの焼き付きを計算します．
    焼き付き後の色毎の劣化率(残存率)，累積ストレス時間，入力画像(動画含む)の劣化後画像を出力します．
    劣化計算は以下の入力情報を使って行います。
    入力情報が多いので，幾つかの情報をまとめてたファイルを引数として読み込み処理します
    Input:
     1.Input images (Movie or Static image)
     2.HeatMap images (Movie or Static image)
     3.BC settings
       3-01. BC_BAND_NUM :   Band数
       3-02. APL_DPK :       DPKモード時，変数=DVB_NIT_DPKで定義するPeak輝度となるAPL値．
       3-03. DBV_NIT_DPK :   DPKモード時，APL=APL_DPKで出力したいPeak輝度値（Band表中パネル仕様として定義）
       3-04. DBV_NIT_BC :    各Bandの1%Window想定時(APL1%)のPeak輝度
       3-05. CURR_BC_R :     各BandにおけるPeak輝度時の電流値，Band間で規格化 (何れかのBandの於ける値を"1"として規格化(同色間で規格化))
       3-06. CURR_BC_G :     各BandにおけるPeak輝度時の電流値，Band間で規格化 (何れかのBandの於ける値を"1"として規格化(同色間で規格化))
       3-07. CURR_BC_B :     各BandにおけるPeak輝度時の電流値，Band間で規格化 (何れかのBandの於ける値を"1"として規格化(同色間で規格化))
       3-08. CURR_RATIO :    Peak輝度電流のRGB電流比(R+G+B=1として定義，Band間のpeak電流規格化時に"1"としたBandのRGB電流から定義)
       3-09. GI_LUT_WRD_GRY: GI_LUT (GrayLev.- I Lut)のLevel方向(諧調方向)のData数(word数)
       3-10. GI_LUT_GRY :    GI_LUT (GrayLev.- I Lut)のLevel方向(諧調方向)のData値
       3-11. (Key名なしData): GI_LUT (Band毎のRGB電流値，各Band，各色のPeak電流で規格化, RGB x Band数分の列)
     4.Degradation Model parameters -Master Model
       4-00. N :             加速係数 x RGB
       4-01. K0 :            τに近い変数 x RGB (K = τo * (DBV_MAX * 1/duty_max)^n, (DBV_MAX, duty_maxは劣化特性の標準条件としたいBandでの設定値))
       4-02. Q :             τの温度依存パラメータ x RGB
       4-03. B0 :            β x RGB
       4-04. A :             βの温度依存パラメータ x RGB
     5.Degradation Model parameters -Sub Model
       5-00. DEG_2D_WRD_DEG: 劣化率(残存率)2D-Lutの劣化率軸(Degradation)のData数(word数)
       5-01. DEG_2D_DEG_R:   劣化率(残存率)2D-Lutの劣化率軸(Degradation)のData値(初期値は必ず"1.0", 降順配列となる)
       5-02. DEG_2D_DEG_G:   劣化率(残存率)2D-Lutの劣化率軸(Degradation)のData値(初期値は必ず"1.0", 降順配列となる)
       5-03. DEG_2D_DEG_B:   劣化率(残存率)2D-Lutの劣化率軸(Degradation)のData値(初期値は必ず"1.0", 降順配列となる)
       5-04. DEG_2D_WRD_I:   劣化率(残存率)2D-Lutの電流軸(I)のData数(word数)
       5-05. DEG_2D_DEG_R:   劣化率(残存率)2D-Lutの電流軸(I)のData値(各Band，各色ごとにPeak電流=1で規格化，最終値は必ず1.0, 昇順配列)
       5-06. DEG_2D_DEG_G:   劣化率(残存率)2D-Lutの電流軸(I)のData値(各Band，各色ごとにPeak電流=1で規格化，最終値は必ず1.0, 昇順配列)
       5-07. DEG_2D_DEG_B:   劣化率(残存率)2D-Lutの電流軸(I)のData値(各Band，各色ごとにPeak電流=1で規格化，最終値は必ず1.0, 昇順配列)
       5-08. (Key名なしData): Deg2D_LUT (列方向に2D_Lut x RGB，行方向にBand数分配置)
     6.Sim condition setting
       6-00. AGING_TIME :    焼き付き実行時間．但しこの劣化Simulator中では未使用，本処理の呼び出し側で使用 (本処理の実行終了を管理)
       6-01. ACCEL_RATIO :   Aging時間加速係数，劣化計算1回更新あたりの想定Aging時間を tsample(sec.)*ACCEL_RATIOで考慮 (tsample: 1frame期間(動画時), 1sec.(静止画時))
       6-02. TMP_L :         heat map画像(0~255)の255時の温度想定値 (低温側下限値)(中間値は線形補間で温度算出)
       6-03. TMP_H :         heat map画像(0~255)の255時の温度想定値 (高温側上限値)(中間値は線形補間で温度算出)
       6-04. DBV_NIT :       パネルのDBV設定値（輝度値で設定，この想定輝度の元劣化計算を実施）
       6-05. DPK_ON :        DPKモード設定，1でON，（0(非Active時)の場合，HBM(DPK非Active時のMax Band)より高いDBV_NITを設定しても，強制的にHBMのDBV値に変更）
       6-06. GADJ :          電流調整パラメータ，GI_LUTで定義された電流値を調整 (xGADJ倍する)，(効率ばらつき補正等の用途を想定，調整値はRGB個別に定義）
    Remark :
        (Remark) OpenCVでの画像処理だと画素色の並びがBGRの順番 (備忘)
        (Remark) 動画と静止画ではH,Vの順序に注意 (動画：(w,h) 静止画: (h,w)) (備忘)
        (Remark) 温度分布「画像」から”温度”分布への変換（スケーリング）(0-255 -> XX℃ ~ ZZ℃)
        (Remark) 入力画像の想定はRGB
    History :
        2026.07.31 暫定版新規作成              M.Matsui
        2026.11.10 機能追加し正式release       M.Matsui
"""

import os.path
import cv2
import numpy as np
import sys
import load_com_info as com_info

######################################## Files  ############################################
FILE_OUT_STAT = "stat"     # Output as $(idx)_$(FILE_OUT_STAT)_{R,G,B}.csv
FILE_OUT_DEG  = "deg"      # Output as $(idx)_$(FILE_OUT_DEG)_{R,G,B}.csv
FILE_OUT_IMG  = "out_img"  # Output as $(idx)_$(FILE_OUT_IMG).{mp4,png}

######################################## Directory ############################################
path_input_img_file     = "./dbi_common"
path_input_htmap_file   = "./dbi_common"
path_bcset_file         = "./dbi_conf"
path_degparam_mm_file   = "./dbi_conf"
path_degparam_sm_file   = "./dbi_conf"
path_simconf_file       = "./dbi_input"
path_output             = "./dbi_output"

############################################## Main code ##############################################
def main():
    try :
        if len(sys.argv) == 13 :
            input_img_file   = str(sys.argv[1])  # filenameで指定(拡張子含む)
            input_htmap_file = str(sys.argv[2])  # filenameで指定(拡張子含む)
            bcset_file       = str(sys.argv[3])  # filenameで指定(拡張子含む)
            degparam_mm_file = str(sys.argv[4])  # filenameで指定(拡張子含む) (RGBまとめて1ファイル)
            degparam_sm_file = str(sys.argv[5])  # filenameで指定(拡張子含む) (BC x I x deg x RGB)
            simconf_file     = str(sys.argv[6])  # filenameで指定(拡張子含む)
            stat_r_ini_file  = str(sys.argv[7])  # filenameで指定(拡張子含む)
            stat_g_ini_file  = str(sys.argv[8])  # filenameで指定(拡張子含む)
            stat_b_ini_file  = str(sys.argv[9])  # filenameで指定(拡張子含む)
            ini_en           = str(sys.argv[10])
            oe               = str(sys.argv[11])
            idx              = str(sys.argv[12])
        else :
            raise Exception
        if (not (int(ini_en) >= 0)) or (not (int(idx) >= 0)):
            raise Exception

        rtn = burn_in (
            path_img     = path_input_img_file + "/" + input_img_file,
            path_htmap   = path_input_htmap_file + "/" + input_htmap_file,
            bcset        = path_bcset_file + "/" + bcset_file,
            degparam_mm  = path_degparam_mm_file + "/" + degparam_mm_file,
            degparam_sm = path_degparam_sm_file + "/" + degparam_sm_file,
            simconf      = path_simconf_file + "/" + simconf_file,
            stat_ini_r   = path_output + "/" + stat_r_ini_file,
            stat_ini_g   = path_output + "/" + stat_g_ini_file,
            stat_ini_b   = path_output + "/" + stat_b_ini_file,
            ini_en       = int(ini_en),
            #oe          = oe,
            idx          = int(idx)
           )

    except :
        print(f'IndexError')
        rtn = -1
    return rtn

def deg_2d_interp (iemit, deg, deg2d_axis_i, deg2d_axis_deg, deg_2d, deg2_interp_o) :
    """ Deg2D Lut内の線形補間処理

    パネル状態(発光電流(iemit),劣化率(deg))の情報に基づき，2D-Lutに対する電流及び劣化方向の補間処理を行う
    1st step: 劣化率方向に線形補間 ⇒ 2nd step: 電流方向に線形補間

    Args:
        iemit(np.ndarray):              発光電流Map(画像と同サイズ(h,w), dtype=float)
        deg(np.ndarray):                劣化率Map(画像と同サイズ(h,w), dtype=float)
        deg2d_axis_i(np.ndarray):       2D_Lutの電流軸のData値
        deg2d_axis_deg(np.ndarray):     2D_Lutの劣化軸のData値
        deg_2d(np.ndarray):             2D_Lut size = (len(deg2d_axis_i), len(deg2d_axis_deg))
        deg2_interp_o:                  2D_Lut出力値(補間済) (画像と同サイズ(h,w), dtype=float)
    Returns:
        int:                            0:正常終了，-1:異常終了
    """
    try:
        height = iemit.shape[0] ; width = iemit.shape[1]

        idx_i_upp = np.full((height, width), 0.0, dtype=np.int16)
        idx_deg_lwr = np.full((height, width), 1.0, dtype=np.int16)

        deg2_i_upp_deg_lwr = np.full((height, width), 1.0, dtype=float)
        deg2_i_upp_deg_upp = np.full((height, width), 1.0, dtype=float)
        deg2_i_lwr_deg_lwr = np.full((height, width), 1.0, dtype=float)
        deg2_i_lwr_deg_upp = np.full((height, width), 1.0, dtype=float)

        deg_upp = np.full((height, width), 1.0, dtype=float)
        deg_lwr = np.full((height, width), 1.0, dtype=float)
        i_upp = np.full((height, width), 0.0, dtype=float)
        i_lwr = np.full((height, width), 0.0, dtype=float)

        deg2_ilwr_interp = np.full((height, width), 1.0, dtype=float)
        deg2_iupp_interp = np.full((height, width), 1.0, dtype=float)

        # 2D-Lut Address 検索 - Axis-i
        arr_asc = deg2d_axis_i
        idx_i_upp[:] = np.searchsorted(arr_asc, iemit)
        idx_i_upp[idx_i_upp == 0] = 1
        idx_i_upp[idx_i_upp == len(arr_asc)] = len(arr_asc) - 1

        # 2D-Lut Address 検索 - Axis-deg (degは降順表記の為，符号反転により昇順に変更)
        arr_desc = deg2d_axis_deg
        idx_deg_lwr[:] = np.searchsorted(-1.0 * arr_desc, -1.0 * deg)
        idx_deg_lwr[idx_deg_lwr == 0] = 1
        idx_deg_lwr[idx_deg_lwr == len(arr_desc)] = len(arr_desc) - 1

        # 線形補間用の劣化率(deg2)抽出 (電流，残存劣化率ともに upp: 高値, lwr: 低値 (Addressの高低ではない))
        deg2_i_upp_deg_lwr[:] = deg_2d[idx_i_upp, idx_deg_lwr]
        deg2_i_upp_deg_upp[:] = deg_2d[idx_i_upp, idx_deg_lwr - 1]
        deg2_i_lwr_deg_lwr[:] = deg_2d[idx_i_upp - 1, idx_deg_lwr]
        deg2_i_lwr_deg_upp[:] = deg_2d[idx_i_upp - 1, idx_deg_lwr - 1]

        # 線形補間用の(2D-Lut定義済)i,deg抽出 (電流，残存劣化率ともに upp: 高値, lwr: 低値 (Addressの高低ではない))
        deg_upp[:] = deg2d_axis_deg[idx_deg_lwr - 1]
        deg_lwr[:] = deg2d_axis_deg[idx_deg_lwr]
        i_upp[:] = deg2d_axis_i[idx_i_upp]
        i_lwr[:] = deg2d_axis_i[idx_i_upp - 1]

        # 線形補間：劣化率方向
        deg2_ilwr_interp[:] = deg2_i_lwr_deg_lwr + (deg2_i_lwr_deg_upp - deg2_i_lwr_deg_lwr) * ((deg - deg_lwr) / (deg_upp - deg_lwr))
        deg2_iupp_interp[:] = deg2_i_upp_deg_lwr + (deg2_i_upp_deg_upp - deg2_i_upp_deg_lwr) * ((deg - deg_lwr) / (deg_upp - deg_lwr))
        deg2_ilwr_interp[deg2_ilwr_interp < 0.0] = 0.0  # clip >=0.0
        deg2_iupp_interp[deg2_iupp_interp < 0.0] = 0.0  # clip >=0.0
        # 線形補間：電流方向
        deg2_interp_o[:] = deg2_ilwr_interp + (deg2_iupp_interp - deg2_ilwr_interp) * ((iemit - i_lwr) / (i_upp - i_lwr))
        deg2_interp_o[deg2_interp_o < 0.0] = 0.0    # clip >=0.0

    except :
        rtn_code = -1
    else :
        rtn_code = 0
    finally :
        del idx_i_upp, idx_deg_lwr
        del deg2_i_upp_deg_lwr, deg2_i_upp_deg_upp, deg2_i_lwr_deg_lwr, deg2_i_lwr_deg_upp
        del deg_upp, deg_lwr, i_upp, i_lwr
        del deg2_ilwr_interp, deg2_iupp_interp

    return rtn_code

def burn_in_core (
        tsample, img, ht,
        bcset_dict, degparam_mm_dict, degparam_sm_dict=None,
        simconf_dict=None,
        stat_r=None, stat_g=None, stat_b=None,
        gui_lut_extract_r=None, gui_lut_extract_g=None, gui_lut_extract_b=None,
        curr_bc_extract_r=None, curr_bc_extract_g=None, curr_bc_extract_b=None,
        dbv_nit_bc_extract=None, duty_bc_extract=None,
        deg_2d_bc_extract_r=None, deg_2d_bc_extract_g=None, deg_2d_bc_extract_b=None,
        dbv_nit_eff=None
) :
    """ 累積時間から劣化率を計算し、その結果に基づき入力画像を劣化画像に更新します。同時に累積時間の更新を行います.

    累積ストレスから劣化率を計算(deg1)
    GI_LutのBand間補間を行い，duty, GADJを反映した発光電流を算出．累積ストレスから計算した劣化率(deg1)と合わせて，2D-LutのBand間補間を実施,deg2を算出．
    deg1*deg2により，各画素の点灯時の電流に於ける劣化率(残存率)を算出．この結果を元に劣化画像を生成．
    併せて発光電流とAging時間(tsample*ACCEL_RATIO)から，ストレス量の更新を行う．．

    Args:
        tsample(float):                             単位Aging時間(sec.) 動画時は1Frame期間(1/fps), 静止画時は1.0(sec)
        img(np.ndarray):                            入力画像Data，((動画：(w,h,c) 静止画: (h,w,c)) c: col = (b,g,r))
        ht(np.ndarray):                             Heat Map画像，((動画：(w,h,c) 静止画: (h,w,c)) c: col = (b,g,r))
        bcset_dict(dict([syr, Any])):               詳細は概要に記載
        degparam_mm_dict(dict([syr, Any])):         詳細は概要に記載
        degparam_sm_dict(dict([syr, Any])):         詳細は概要に記載
        simconf_dict(dict([syr, Any])):             詳細は概要に記載
        stat_r,g,b(np.ndarray):                     ストレス累積Data
        gui_lut_extract_r,g,b(list[np.ndarray]) :   線形補間に用いるGI_LUTのList. [BC0, BC1, BC2] (BC0はDPK=ON時に参照)
        curr_bc_extract_r,g,b(list[float]) :        線形補間に用いるBandのPeak電流のList. [BC0, BC1, BC2] (BC0はDPK=1(ON)時に参照)
        dbv_nit_bc_extract(list[float]) :           線形補間に用いるBandのPea輝度のList. [BC0, BC1, BC2, BC0のAPL_DPK時の輝度(DBV_NIT_DPKから選択)] (BC0はDPK=ON時に参照)
        duty_bc_extract(list[float]) :              線形補間に用いるBandのDutyのList.　[BC1, BC2]　(BC0はBC1と同Dutyの為不要)
        deg_2d_bc_extract_r,g,b(list[np.ndarray]):  線形補間に用いるBandのDeg2D_LutのList [BC1, BC2] (DPKで内容変化．DPK=1:BC0,BC1 Lut, DPK=0:BC1,BC2 LutのDataが存在）
        dbv_nit_eff:                                Clip処理後のDBV_NIT設定値

    Returns:
        int:                                        0:正常終了，-1:異常終了

    Side Effects:
        引数で渡されたstat_r, stat_g, stat_bの中身が直接更新されます（インプレイス処理）
        引数で渡されたimgの中身が直接更新されます（インプレイス処理）
    """
    try :
        N_r = degparam_mm_dict["N_r"]
        K0_r = degparam_mm_dict["K0_r"]  # τo * (DBV_MAX * 1/duty_max)^n
        Q_r = degparam_mm_dict["Q_r"]
        B0_r = degparam_mm_dict["B0_r"]
        A_r = degparam_mm_dict["A_r"]

        N_g = degparam_mm_dict["N_g"]
        K0_g = degparam_mm_dict["K0_g"]  # τo * (DBV_MAX * 1/duty_max)^n
        Q_g = degparam_mm_dict["Q_g"]
        B0_g = degparam_mm_dict["B0_g"]
        A_g = degparam_mm_dict["A_g"]

        N_b = degparam_mm_dict["N_b"]
        K0_b = degparam_mm_dict["K0_b"]  # τo * (DBV_MAX * 1/duty_max)^n
        Q_b = degparam_mm_dict["Q_b"]
        B0_b = degparam_mm_dict["B0_b"]
        A_b = degparam_mm_dict["A_b"]

        TMP_L = simconf_dict["TMP_L"] + 273.0
        TMP_H = simconf_dict["TMP_H"] + 273.0

        ACCEL_RATIO = simconf_dict["ACCEL_RATIO"]

        GADJ_R = simconf_dict["GADJ_R"] # 電流調整用パラメータ，指定係数に応じて画素電流値が変化 ipix= ipix x GADJ
        GADJ_G = simconf_dict["GADJ_G"]
        GADJ_B = simconf_dict["GADJ_B"]

        height, width = img.shape[:2]

        # APL値計算
        curr_r_apl = GADJ_R * bcset_dict["CURR_RATIO_R"]
        curr_g_apl = GADJ_G * bcset_dict["CURR_RATIO_G"]
        curr_b_apl = GADJ_B * bcset_dict["CURR_RATIO_B"]
        curr_ratio_r = curr_r_apl / (curr_r_apl + curr_g_apl + curr_b_apl)
        curr_ratio_g = curr_g_apl / (curr_r_apl + curr_g_apl + curr_b_apl)
        curr_ratio_b = curr_b_apl / (curr_r_apl + curr_g_apl + curr_b_apl)

        apl_img = curr_ratio_b * np.mean((img[:,:,0] /255) ** 2.2) + curr_ratio_g * np.mean((img[:,:,1] /255) ** 2.2) + curr_ratio_r * np.mean((img[:,:,2] /255) ** 2.2)

        # 劣化率Map (正しくは輝度残存率)
        deg_r = np.full((height, width), 1.0, dtype=float)
        deg_g = np.full((height, width), 1.0, dtype=float)
        deg_b = np.full((height, width), 1.0, dtype=float)

        # 輝度Map(中間計算用に使用)
        lum_r = np.full((height, width), 0.0, dtype=float)
        lum_g = np.full((height, width), 0.0, dtype=float)
        lum_b = np.full((height, width), 0.0, dtype=float)

        # 電流補間用Map (gi_lut)
        lut_upp_r = np.full((height, width), 0.0, dtype=float)
        lut_upp_g = np.full((height, width), 0.0, dtype=float)
        lut_upp_b = np.full((height, width), 0.0, dtype=float)

        lut_lwr_r_adj = np.full((height, width), 0.0, dtype=float)
        lut_lwr_g_adj = np.full((height, width), 0.0, dtype=float)
        lut_lwr_b_adj = np.full((height, width), 0.0, dtype=float)

        # (補間後) 電流Map
        ipix_r = np.full((height, width), 0.0, dtype=float)
        ipix_g = np.full((height, width), 0.0, dtype=float)
        ipix_b = np.full((height, width), 0.0, dtype=float)

        # (補間後) 発光電流Map
        iemit = np.full((height, width), 0.0, dtype=float)      # (Band間)電流規格化: 無
        curr_emit = np.full((height, width), 0.0, dtype=float)  # (Band間)電流規格化: 有

        # 劣化率(残存劣化率)2D-Lut Map: upper Band
        deg2_interp_bc1_r = np.full((height, width), 1.0, dtype=float)
        deg2_interp_bc1_g = np.full((height, width), 1.0, dtype=float)
        deg2_interp_bc1_b = np.full((height, width), 1.0, dtype=float)

        # 劣化率(残存劣化率)2D-Lut Map: lower Band
        deg2_interp_bc2_r = np.full((height, width), 1.0, dtype=float)
        deg2_interp_bc2_g = np.full((height, width), 1.0, dtype=float)
        deg2_interp_bc2_b = np.full((height, width), 1.0, dtype=float)

        # 劣化率(残存劣化率) 補間後2D-Lut Map
        deg2_interp_r = np.full((height, width), 1.0, dtype=float)
        deg2_interp_g = np.full((height, width), 1.0, dtype=float)
        deg2_interp_b = np.full((height, width), 1.0, dtype=float)

        # 温度Map(中間計算用に使用)
        temp = np.full((height, width), TMP_L, dtype=float)

        # 現在の劣化率を累積時間から計算（劣化率更新）
        deg_b[:] = np.exp(-1.0 * (stat_b[:] ** (B0_b + A_b * temp[:])))
        deg_g[:] = np.exp(-1.0 * (stat_g[:] ** (B0_g + A_g * temp[:])))
        deg_r[:] = np.exp(-1.0 * (stat_r[:] ** (B0_r + A_r * temp[:])))

        #　線形補間用Data -------------------------------------------------------------------------------------------
        # gi_lut : BC0, BC1, BC2 (BC0はDPKモード用)
        gi_lut0_r = gui_lut_extract_r[0] ; gi_lut1_r = gui_lut_extract_r[1] ; gi_lut2_r = gui_lut_extract_r[2]
        gi_lut0_g = gui_lut_extract_g[0] ; gi_lut1_g = gui_lut_extract_g[1] ; gi_lut2_g = gui_lut_extract_g[2]
        gi_lut0_b = gui_lut_extract_b[0] ; gi_lut1_b = gui_lut_extract_b[1] ; gi_lut2_b = gui_lut_extract_b[2]

        # Peak電流 : BC0, BC1, BC2 (BC0はDPKモード用)
        curr_bc0_r = curr_bc_extract_r[0] ; curr_bc1_r = curr_bc_extract_r[1] ; curr_bc2_r = curr_bc_extract_r[2]
        curr_bc0_g = curr_bc_extract_g[0] ; curr_bc1_g = curr_bc_extract_g[1] ; curr_bc2_g = curr_bc_extract_g[2]
        curr_bc0_b = curr_bc_extract_b[0] ; curr_bc1_b = curr_bc_extract_b[1] ; curr_bc2_b = curr_bc_extract_b[2]

        # 輝度(DBV_NIT) : BC0, BC1, BC2 (BC0はDPKモード用:APL~1%時, _dpkの値はDPKモード用:指定のAPL値(APL_DPK(bcsettingで定義))での輝度)
        dbv_nit_bc0 = dbv_nit_bc_extract[0] ; dbv_nit_bc1 = dbv_nit_bc_extract[1] ; dbv_nit_bc2 = dbv_nit_bc_extract[2]
        dbv_nit_dpk = dbv_nit_bc_extract[3]

        # Duty : BC1, BC2 (BC0はBC1同じ値の為不要)
        duty_bc1 = duty_bc_extract[0] ; duty_bc2 = duty_bc_extract[1]

        # 劣化率(残存率)の2D-Lut : BC1, BC2 (DPKモード時はBC0用LutをBC1，BC1用のLutをBC2として，呼び出し元の関数が提供)
        deg_2d_bc1_r = deg_2d_bc_extract_r[0] ; deg_2d_bc2_r = deg_2d_bc_extract_r[1]
        deg_2d_bc1_g = deg_2d_bc_extract_g[0] ; deg_2d_bc2_g = deg_2d_bc_extract_g[1]
        deg_2d_bc1_b = deg_2d_bc_extract_b[0] ; deg_2d_bc2_b = deg_2d_bc_extract_b[1]

        #　線形補間　電流(gi_lut) -------------------------------------------------------------------------------------------
        # DPKモード時，目的のAPL値(APL_DPK)で輝度値がDBV_NIT_DPKに一致するようにAPL調整用パラメータ:apl_adjを定義
        apl_dpk = bcset_dict["APL_DPK"]
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            apl_adj = ((dbv_nit_bc0 - dbv_nit_bc1) * (1.0 - apl_dpk) + dbv_nit_bc1) / dbv_nit_dpk
        else :
            apl_adj = 1.0

        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            lut_upp_r[:] = gi_lut0_r[img[:, :, 2]]
            lut_upp_g[:] = gi_lut0_g[img[:, :, 1]]
            lut_upp_b[:] = gi_lut0_b[img[:, :, 0]]

            lut_lwr_r_adj[:] = gi_lut1_r[img[:, :, 2]] * curr_bc1_r / curr_bc0_r    # lower側の電流基準をupper側に揃える
            lut_lwr_g_adj[:] = gi_lut1_g[img[:, :, 1]] * curr_bc1_g / curr_bc0_g
            lut_lwr_b_adj[:] = gi_lut1_b[img[:, :, 0]] * curr_bc1_b / curr_bc0_b

            ipix_r[:] = lut_lwr_r_adj + (lut_upp_r - lut_lwr_r_adj) * (1.0 - (apl_img * apl_adj))
            ipix_g[:] = lut_lwr_g_adj + (lut_upp_g - lut_lwr_g_adj) * (1.0 - (apl_img * apl_adj))
            ipix_b[:] = lut_lwr_b_adj + (lut_upp_b - lut_lwr_b_adj) * (1.0 - (apl_img * apl_adj))
        else :
            lut_upp_r[:] = gi_lut1_r[img[:, :, 2]]
            lut_upp_g[:] = gi_lut1_g[img[:, :, 1]]
            lut_upp_b[:] = gi_lut1_b[img[:, :, 0]]

            lut_lwr_r_adj[:] = gi_lut2_r[img[:, :, 2]] * curr_bc2_r / curr_bc1_r
            lut_lwr_g_adj[:] = gi_lut2_g[img[:, :, 1]] * curr_bc2_g / curr_bc1_g
            lut_lwr_b_adj[:] = gi_lut2_b[img[:, :, 0]] * curr_bc2_b / curr_bc1_b

            ipix_r[:] = lut_lwr_r_adj + (lut_upp_r - lut_lwr_r_adj) * ((dbv_nit_eff - dbv_nit_bc2)/(dbv_nit_bc1 - dbv_nit_bc2))
            ipix_g[:] = lut_lwr_g_adj + (lut_upp_g - lut_lwr_g_adj) * ((dbv_nit_eff - dbv_nit_bc2)/(dbv_nit_bc1 - dbv_nit_bc2))
            ipix_b[:] = lut_lwr_b_adj + (lut_upp_b - lut_lwr_b_adj) * ((dbv_nit_eff - dbv_nit_bc2)/(dbv_nit_bc1 - dbv_nit_bc2))

        #　線形補間　Duty ----------------------------------------------------------------------------------------------------------
        duty_interp = duty_bc2 + (duty_bc1 - duty_bc2)  * ((dbv_nit_eff - dbv_nit_bc2)/(dbv_nit_bc1 - dbv_nit_bc2))

        #　線形補間　劣化率(残存率) 2D-Lut -------------------------------------------------------------------------------------------
        # 非DPKモード時(通常動作時)の2D-Lut値のBAND間補間用パラメータ：発光電流量でBAND間補間
        lemit_nit_bc1 = dbv_nit_bc1 / duty_bc1 ; lemit_nit_bc2 = dbv_nit_bc2 / duty_bc2
        lemit_nit_eff = dbv_nit_eff / duty_interp

        # Deg 2d interpolation for Red ---------------
        iemit[:] = ipix_r[:] / duty_interp * GADJ_R
        # BC1
        rtn = deg_2d_interp(iemit, deg_r, degparam_sm_dict["DEG_2D_I_R"], degparam_sm_dict["DEG_2D_DEG_R"], deg_2d_bc1_r, deg2_interp_bc1_r)
        if rtn != 0 : raise Exception
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            iemit[:] *= curr_bc0_r / curr_bc1_r
        else :
            iemit[:] *= curr_bc1_r / curr_bc2_r

        # BC2
        rtn = deg_2d_interp(iemit, deg_r, degparam_sm_dict["DEG_2D_I_R"], degparam_sm_dict["DEG_2D_DEG_R"], deg_2d_bc2_r, deg2_interp_bc2_r)
        if rtn != 0: raise Exception

        # Band間補間
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            deg2_interp_r[:] = deg2_interp_bc2_r + (deg2_interp_bc1_r - deg2_interp_bc2_r) * (1.0 - (apl_img * apl_adj))
        else :
            deg2_interp_r[:] = deg2_interp_bc2_r + (deg2_interp_bc1_r - deg2_interp_bc2_r) * ((lemit_nit_eff - lemit_nit_bc2)/(lemit_nit_bc1 -lemit_nit_bc2))
        deg2_interp_r[deg2_interp_r < 0.0] = 0.0

        # Deg 2d interpolation for Green ---------------
        iemit[:] = ipix_g[:] / duty_interp * GADJ_G
        # BC1
        rtn = deg_2d_interp(iemit, deg_g, degparam_sm_dict["DEG_2D_I_G"], degparam_sm_dict["DEG_2D_DEG_G"], deg_2d_bc1_g, deg2_interp_bc1_g)
        if rtn != 0 : raise Exception
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            iemit[:] *= curr_bc0_g / curr_bc1_g
        else :
            iemit[:] *= curr_bc1_g / curr_bc2_g

        # BC2
        rtn = deg_2d_interp(iemit, deg_g, degparam_sm_dict["DEG_2D_I_G"], degparam_sm_dict["DEG_2D_DEG_G"], deg_2d_bc2_g, deg2_interp_bc2_g)
        if rtn != 0: raise Exception

        # Band間補間
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            deg2_interp_g[:] = deg2_interp_bc2_g + (deg2_interp_bc1_g - deg2_interp_bc2_g) * (1.0 - (apl_img * apl_adj))
        else :
            deg2_interp_g[:] = deg2_interp_bc2_g + (deg2_interp_bc1_g - deg2_interp_bc2_g) * ((lemit_nit_eff - lemit_nit_bc2)/(lemit_nit_bc1 -lemit_nit_bc2))
        deg2_interp_g[deg2_interp_g < 0.0] = 0.0

        # Deg 2d interpolation for Blue ---------------
        iemit[:] = ipix_b[:] / duty_interp * GADJ_B
        # BC1
        rtn = deg_2d_interp(iemit, deg_b, degparam_sm_dict["DEG_2D_I_B"], degparam_sm_dict["DEG_2D_DEG_B"], deg_2d_bc1_b, deg2_interp_bc1_b)
        if rtn != 0 : raise Exception
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            iemit[:] *= curr_bc0_b/curr_bc1_b
        else :
            iemit[:] *= curr_bc1_b / curr_bc2_b

        # BC2
        rtn = deg_2d_interp(iemit, deg_b, degparam_sm_dict["DEG_2D_I_B"], degparam_sm_dict["DEG_2D_DEG_B"], deg_2d_bc2_b, deg2_interp_bc2_b)
        if rtn != 0: raise Exception

        # Band間補間
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            deg2_interp_b[:] = deg2_interp_bc2_b + (deg2_interp_bc1_b - deg2_interp_bc2_b) * (1.0 - (apl_img * apl_adj))
        else :
            deg2_interp_b[:] = deg2_interp_bc2_b + (deg2_interp_bc1_b - deg2_interp_bc2_b) * ((lemit_nit_eff - lemit_nit_bc2)/(lemit_nit_bc1 -lemit_nit_bc2))
        deg2_interp_b[deg2_interp_b < 0.0] = 0.0

        # 劣化画像の生成
        lum_b[:] = (img[:, :, 0] / 255) ** 2.2 * deg_b * deg2_interp_b
        lum_g[:] = (img[:, :, 1] / 255) ** 2.2 * deg_g * deg2_interp_g
        lum_r[:] = (img[:, :, 2] / 255) ** 2.2 * deg_r * deg2_interp_r

        img[:, :, 0] = (255 * (lum_b[:] ** (1 / 2.2))).astype(np.uint8)
        img[:, :, 1] = (255 * (lum_g[:] ** (1 / 2.2))).astype(np.uint8)
        img[:, :, 2] = (255 * (lum_r[:] ** (1 / 2.2))).astype(np.uint8)

        temp[:] = (ht[:, :, 0] / 255) * (TMP_H - TMP_L) + TMP_L

        # Totalストレス時間の累積
        # 電流はupper Band側の基準に揃えられているのでupper BandのCurr値を選択（DPKモード時はupper bandはBC0，通常はBC1）
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= dbv_nit_bc1):
            curr_norm_coef_r = curr_bc0_r ; curr_norm_coef_g = curr_bc0_g ; curr_norm_coef_b = curr_bc0_b
        else :
            curr_norm_coef_r = curr_bc1_r ; curr_norm_coef_g = curr_bc1_g ; curr_norm_coef_b = curr_bc1_b

        # 発光電流をBAND間共通の規格化で再定義(=curr_emit), ストレス加算
        curr_emit[:] = ipix_r[:] / duty_interp * GADJ_R * curr_norm_coef_r
        stat_r[:] += tsample * duty_interp * ACCEL_RATIO * (curr_emit ** N_r) / (K0_r * np.exp(Q_r / temp)) * (B0_r + A_r * temp) / B0_r

        curr_emit[:] = ipix_g[:] / duty_interp * GADJ_G * curr_norm_coef_g
        stat_g[:] += tsample * duty_interp  * ACCEL_RATIO * (curr_emit ** N_g) / (K0_g * np.exp(Q_g / temp)) * (B0_g + A_g * temp) / B0_g

        curr_emit[:] = ipix_b[:] / duty_interp * GADJ_B * curr_norm_coef_b
        stat_b[:] += tsample * duty_interp  * ACCEL_RATIO * (curr_emit ** N_b) / (K0_b * np.exp(Q_b / temp)) * (B0_b + A_b * temp) / B0_b

    except :
        rtn_code = -1
    else :
        rtn_code = 0
    finally :
        del deg_r, deg_g, deg_b
        del lum_r, lum_g, lum_b
    return rtn_code

def burn_in_band_extract (bc_dict, degparam_sm_dict, simconf_dict) :
    """ Band間補間用Dataの抽出 (burn_in()内の "Target DBV check" ～ "Deg 2D_Lut extraction" の処理を関数として切り出したもの)

    2026-11-12 追加(bisim側): burn_in()と同一の処理．burn_in()は変更せずにそのまま残している．
    呼び出し側でフレームループを回す場合(GUI版 bisim等)に，burn_in_core()に渡すBand間補間用Dataを
    1回だけ作成する目的で使用する．入力は設定値(BC settings, Sub Model, Sim condition)のみで，画像には依存しない．

    Args:
        bc_dict(dict([str, Any])):              load_bcset()の出力
        degparam_sm_dict(dict([str, Any])):     load_degparam_sm()の出力
        simconf_dict(dict([str, Any])):         load_simconf()の出力

    Returns:
        int:                                    0:正常終了，-1:異常終了
        dict([str, Any]):                       burn_in_core()の同名引数に渡すData
                                                (gui_lut_extract_r,g,b / curr_bc_extract_r,g,b / dbv_nit_bc_extract / duty_bc_extract /
                                                 deg_2d_bc_extract_r,g,b / dbv_nit_eff)
        str:                                    log (burn_in()が出力するlogの該当部分と同じ内容)
    """
    band_dict = {}
    log = ""
    try :
        log += f'---- Target DBV check ----' + "\n"

        # DBV_NIT Clip(上限・下限値Clip), 有効DBV値(dvb_nit_eff) 生成
        idx_HBM = len(bc_dict["DBV_NIT_DPK"])   # 通常(非DPKモード)のMax Band調査(=HBM)
        if (simconf_dict["DPK_ON"] == 1) and (simconf_dict["DBV_NIT"] >= bc_dict["DBV_NIT_DPK"][0]) :
            dbv_nit_eff = bc_dict["DBV_NIT_DPK"][0] # 上限Clip (DPKモード時)
            log += f'DPK Mode: ON, DBV_NIT={str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        elif (simconf_dict["DPK_ON"] == 0) and (simconf_dict["DBV_NIT"] > bc_dict["DBV_NIT_BC"][idx_HBM]) :
            dbv_nit_eff = bc_dict["DBV_NIT_BC"][idx_HBM] # 上限Clip (非DPKモード時)
            log += f'DPK Mode: OFF, DBV_NIT={str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        elif simconf_dict["DBV_NIT"] < bc_dict["DBV_NIT_BC"][-1] :   # 下限Clip
            dbv_nit_eff = bc_dict["DBV_NIT_BC"][-1]
            log += f'DBV_NIT={str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        else :
            dbv_nit_eff = simconf_dict["DBV_NIT"]
            log += f'{str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        log += f'---- Band Data Extraction ----' + "\n"

        # BC番号(BAND番号)チェック(idx_bc_upp, idx_bc_lwr, upp: 高輝度側 Band)
        arr_desc = np.array(bc_dict["DBV_NIT_BC"][idx_HBM:]) #DBVは降順配列の為，符号反転により昇順に変更
        idx_bc_lwr = np.searchsorted( -1.0 * arr_desc, -1.0 * dbv_nit_eff)
        if idx_bc_lwr == 0 : idx_bc_lwr = 1 + idx_HBM
        elif idx_bc_lwr == len(arr_desc) : idx_bc_lwr = len(arr_desc) - 1 + idx_HBM
        else : idx_bc_lwr += idx_HBM

        idx_bc_upp = idx_bc_lwr - 1

        # Band間補間用データ抽出　：　電流(gi_lut) --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，gi_lut0, gu_lut1, gu_lut2 を抽出 (upp -> lut1, lwr -> lut2)
        # BC0
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            idx_bc0 = 0
            gi_lut0_r = bc_dict["GI_LUT_GRY_BC_R"][:,0]
            gi_lut0_g = bc_dict["GI_LUT_GRY_BC_G"][:,0]
            gi_lut0_b = bc_dict["GI_LUT_GRY_BC_B"][:,0]
        else :
            idx_bc0 = 1
            gi_lut0_r = bc_dict["GI_LUT_GRY_BC_R"][:,1]
            gi_lut0_g = bc_dict["GI_LUT_GRY_BC_G"][:,1]
            gi_lut0_b = bc_dict["GI_LUT_GRY_BC_B"][:,1]
        # BC1
        gi_lut1_r = bc_dict["GI_LUT_GRY_BC_R"][:, int(idx_bc_upp)]
        gi_lut1_g = bc_dict["GI_LUT_GRY_BC_G"][:, int(idx_bc_upp)]
        gi_lut1_b = bc_dict["GI_LUT_GRY_BC_B"][:, int(idx_bc_upp)]
        # BC2
        gi_lut2_r = bc_dict["GI_LUT_GRY_BC_R"][:, int(idx_bc_lwr)]
        gi_lut2_g = bc_dict["GI_LUT_GRY_BC_G"][:, int(idx_bc_lwr)]
        gi_lut2_b = bc_dict["GI_LUT_GRY_BC_B"][:, int(idx_bc_lwr)]

        # gui_lut_extract = [gi_lut0, gu_lut1, gu_lut2]
        gui_lut_extract_r = [gi_lut0_r, gi_lut1_r, gi_lut2_r]
        gui_lut_extract_g = [gi_lut0_g, gi_lut1_g, gi_lut2_g]
        gui_lut_extract_b = [gi_lut0_b, gi_lut1_b, gi_lut2_b]

        log += f'Extracted Band [BC0]: Band{str(idx_bc0)}, [BC1]: Band{str(idx_bc_upp)}, [BC2]: Band{str(idx_bc_lwr)}' + "\n"
        log += f'GI_LUT extraction finished. Peak current extraction started.' + "\n"

        # Band間補間用データ抽出　：　Peak電流 --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，curr_bc0, curr_bc1, curr_bc2を抽出
        # BC0
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            curr_bc0_r = bc_dict["CURR_BC_R"][0]
            curr_bc0_g = bc_dict["CURR_BC_G"][0]
            curr_bc0_b = bc_dict["CURR_BC_B"][0]
        else :
            curr_bc0_r = bc_dict["CURR_BC_R"][1]
            curr_bc0_g = bc_dict["CURR_BC_G"][1]
            curr_bc0_b = bc_dict["CURR_BC_B"][1]
        # BC1
        curr_bc1_r = bc_dict["CURR_BC_R"][int(idx_bc_upp)]
        curr_bc1_g = bc_dict["CURR_BC_G"][int(idx_bc_upp)]
        curr_bc1_b = bc_dict["CURR_BC_B"][int(idx_bc_upp)]
        # BC2
        curr_bc2_r = bc_dict["CURR_BC_R"][int(idx_bc_lwr)]
        curr_bc2_g = bc_dict["CURR_BC_G"][int(idx_bc_lwr)]
        curr_bc2_b = bc_dict["CURR_BC_B"][int(idx_bc_lwr)]

        # curr_bc_extract = [curr_bc0, curr_bc1, curr_bc2]
        curr_bc_extract_r = [curr_bc0_r, curr_bc1_r, curr_bc2_r]
        curr_bc_extract_g = [curr_bc0_g, curr_bc1_g, curr_bc2_g]
        curr_bc_extract_b = [curr_bc0_b, curr_bc1_b, curr_bc2_b]

        log += f' Extracted Peak Current_R (BC0,1,2): [{", ".join(str(i) for i in curr_bc_extract_r)}]' + "\n"
        log += f' Extracted Peak Current_G (BC0,1,2): [{", ".join(str(i) for i in curr_bc_extract_g)}]' + "\n"
        log += f' Extracted Peak Current_B (BC0,1,2): [{", ".join(str(i) for i in curr_bc_extract_b)}]' + "\n"
        log += f'Peak current extraction finished. Peak lum. extraction started.' + "\n"

        # Band間補間用データ抽出　：　Peak輝度 --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，dvb_nit_bc0, dvb_nit_bc1, dvb_nit_bc2, dbv_nit_dpkを抽出
        # BC0
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            dbv_nit_bc0 = bc_dict["DBV_NIT_BC"][0]
            dbv_nit_dpk = bc_dict["DBV_NIT_DPK"][0]
        else :
            dbv_nit_bc0 = bc_dict["DBV_NIT_BC"][1]
            dbv_nit_dpk = bc_dict["DBV_NIT_DPK"][1]
        # BC1,2
        dbv_nit_bc1 = bc_dict["DBV_NIT_BC"][int(idx_bc_upp)]
        dbv_nit_bc2 = bc_dict["DBV_NIT_BC"][int(idx_bc_lwr)]

        # dvb_nit_bc_extract = [dvb_nit_bc0, dvb_nit_bc1, dvb_nit_bc2, dbv_nit_dpk]
        dbv_nit_bc_extract = [dbv_nit_bc0, dbv_nit_bc1, dbv_nit_bc2, dbv_nit_dpk]

        log += f' Extracted Peak Lum. (BC0,1,2,BC0 at APL{str(bc_dict["APL_DPK"])}): [{", ".join(str(i) for i in dbv_nit_bc_extract)}]' + "\n"
        log += f'Peak lum. extraction finished. Duty extraction started.' + "\n"

        # Band間補間用データ抽出　：　Duty --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，duty_bc1, duty_bc2を抽出
        # BC1,2 (BC0はBC1と常に同じDutyの為不要)
        duty_bc1 = bc_dict["DUTY_BC"][int(idx_bc_upp)]
        duty_bc2 = bc_dict["DUTY_BC"][int(idx_bc_lwr)]

        # duty_bc_extract = [duty_bc1, duty_bc2]
        duty_bc_extract = [duty_bc1, duty_bc2]

        log += f' Extracted Duty (BC1,2): [{", ".join(str(i) for i in duty_bc_extract)}]' + "\n"
        log += f'Duty extraction finished. Deg 2D_Lut extraction started.' + "\n"

        # Band間補間用データ抽出　：　劣化率(残存率) 2D-Lut ------------------------------------------------
        # bc_upp/lwrのidxを参考に，deg_2d_bc1, deg_2d_bc2を抽出
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            idx_bc1 = 0
            deg_2d_bc1_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][0,:,:] # DPKモード時BC0をBC1として出力 (APL1)
            deg_2d_bc1_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][0,:,:]
            deg_2d_bc1_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][0,:,:]
            idx_bc2 = idx_HBM
            deg_2d_bc2_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][idx_HBM,:,:]
            deg_2d_bc2_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][idx_HBM,:,:]
            deg_2d_bc2_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][idx_HBM,:,:]

        elif (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_BC"][2]) :
            idx_bc1 = 1
            deg_2d_bc1_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][1,:,:] # DPKモード時BC0をBC1として出力 (APL2)
            deg_2d_bc1_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][1,:,:]
            deg_2d_bc1_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][1,:,:]
            idx_bc2 = idx_HBM
            deg_2d_bc2_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][idx_HBM,:,:]
            deg_2d_bc2_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][idx_HBM,:,:]
            deg_2d_bc2_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][idx_HBM,:,:]

        else :
            idx_bc1 = int(idx_bc_upp)
            deg_2d_bc1_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][int(idx_bc_upp),:,:] # 非DPKモード(通常)時はBC1を出力
            deg_2d_bc1_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][int(idx_bc_upp),:,:]
            deg_2d_bc1_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][int(idx_bc_upp),:,:]
            idx_bc2 = int(idx_bc_lwr)
            deg_2d_bc2_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][int(idx_bc_lwr),:,:]
            deg_2d_bc2_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][int(idx_bc_lwr),:,:]
            deg_2d_bc2_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][int(idx_bc_lwr),:,:]

        # deg_2d_bc_extract = [deg_2d_bc1, deg_2d_bc2]
        deg_2d_bc_extract_r = [deg_2d_bc1_r, deg_2d_bc2_r]
        deg_2d_bc_extract_g = [deg_2d_bc1_g, deg_2d_bc2_g]
        deg_2d_bc_extract_b = [deg_2d_bc1_b, deg_2d_bc2_b]

        log += f' Extracted Deg 2D_LUT of BC1: Band{str(idx_bc1)}' + "\n"
        log += f' Extracted Deg 2D_LUT of BC2: Band{str(idx_bc2)}' + "\n"
        log += f'Deg 2D_Lut extraction finished.' + "\n"

        # burn_in_core()の引数名に合わせて格納 (burn_in_core(..., **band_dict) で渡せる)
        band_dict = {
            "gui_lut_extract_r": gui_lut_extract_r, "gui_lut_extract_g": gui_lut_extract_g, "gui_lut_extract_b": gui_lut_extract_b,
            "curr_bc_extract_r": curr_bc_extract_r, "curr_bc_extract_g": curr_bc_extract_g, "curr_bc_extract_b": curr_bc_extract_b,
            "dbv_nit_bc_extract": dbv_nit_bc_extract, "duty_bc_extract": duty_bc_extract,
            "deg_2d_bc_extract_r": deg_2d_bc_extract_r, "deg_2d_bc_extract_g": deg_2d_bc_extract_g, "deg_2d_bc_extract_b": deg_2d_bc_extract_b,
            "dbv_nit_eff": dbv_nit_eff,
        }
    except :
        rtn_code = -1
        log += f'Band data extraction error' + "\n"
    else :
        rtn_code = 0

    return rtn_code, band_dict, log

############################################## Main Body ##############################################
def burn_in (
        path_img, path_htmap,
        bcset,
        degparam_mm, degparam_sm=None, simconf=None,
        stat_ini_r=None, stat_ini_g=None, stat_ini_b=None,
        ini_en=0, oe=1, idx=0
    ) :
    """ 映像入力情報の形式(動画.mp4, 静止画.png)を読み取り、引数で与えられた劣化パラメータとSim条件に基づき劣化映像を作成，併せて劣化情報(劣化率，ストレス累積時間)を出力します.

    入力情報が多いので，幾つかの情報をまとめてたファイルを引数として読み込み処理します
    出力ファイル名は固定名ですが、引数:idxによりファイル名にprefixとしてidx番号を付与できます
    引数としてstat_r,g,bのファイルを指定することで，途中の劣化状態から計算を始めることが出来ます
    ただし、この機能はini_en=1とすることで有効になります（ファイル指定だけでは機能しません）
    計算状況はlogファイルとして出力します
    引数；oeの設定で生成した劣化映像（動画，静止画）の出力を有効・無効化出来ます(ただし劣化情報はoe設定に依らず出力)　⇒　oeは不要と決定のため未実装

    Args:
        path_img(str):      入力画像/動画ファイルのPath
        path_htmap(str):    Heat Map画像/動画ファイルのPath
        bcset(str):         BC settingsファイルのPath
        degparam_mm(str):   Degradation parameter -Master Model ファイルのPath
        degparam_sm(str):   Degradation parameter -Sub Model ファイルのPath
        simconf(str):       Sim条件設定ファイルのPath
        stat_ini_r(str):    計算開始時に参照する累積ストレスファイルのPath
        stat_ini_g(str):    計算開始時に参照する累積ストレスファイルのPath
        stat_ini_b(str):    計算開始時に参照する累積ストレスファイルのPath
        ini_en(int):        参照した累積ストレスファイルの使用enable設定（1: 使用(途中の劣化状態から再計算)，≠1: 累積ファイル非参照(初期状態から計算)
        oe(int):            未実装
        idx(int):           結果出力ファイルのSuffix (idx_(出力ファイル名)のファイル名で出力)

    Returns:
        int:                0:正常終了，-1:異常終了

    Side Effects:
        以下のファイルが path_outputで設定したディレクトリに出力されます.出力時，各ファイルにはidxで設定したSuffixが付与されます．．
        idx_stat_r.csv, idx_stat_g.csv, idx_stat_b.csv
        idx_deg_r.csv,  idx_deg_g.csv,  idx_deg_b.csv
        idx_out_img.png | idx_out_img.mp4 (静止画時:.png, 動画時:.mp4 )
        idx_log.txt
    """
    try :
        log = ""
        # File Load 設定値読み込み
        rtn_code_bcset, bc_dict = com_info.load_bcset(bcset)
        rtn_code_degparam_mm, degparam_mm_dict = com_info.load_degparam_mm(degparam_mm)
        rtn_code_degparam_sm, degparam_sm_dict = com_info.load_degparam_sm(degparam_sm)
        rtn_code_simconf, simconf_dict = com_info.load_simconf(simconf)
        # 2026-11-12 追加(bisim側): degparam_sm の読み込み失敗も検出し，失敗したファイルをlogに出力
        if rtn_code_bcset != 0 or rtn_code_degparam_mm != 0 or rtn_code_degparam_sm != 0 or rtn_code_simconf != 0 :
            log += f'{"File Load error"}' + "\n"
            if rtn_code_bcset != 0 :       log += f' BC setting file: {str(bcset)}' + "\n"
            if rtn_code_degparam_mm != 0 : log += f' Degradation parameter -Master Model: {str(degparam_mm)}' + "\n"
            if rtn_code_degparam_sm != 0 : log += f' Degradation parameter -Sub Model: {str(degparam_sm)}' + "\n"
            if rtn_code_simconf != 0 :     log += f' Sim condition setting file: {str(simconf)}' + "\n"
            raise Exception
        # 2026-11-12 追加(bisim側): Sub ModelのBand数がBC settingのBand数(BC_BAND_NUM)と一致するか確認
        sm_band_num = degparam_sm_dict["DEG_2D_BC_IxDEG_R"].shape[0]
        if sm_band_num != bc_dict["BC_BAND_NUM"] :
            log += f'{"File Load error"}' + "\n"
            log += f' Band number mismatch: Sub Model={str(sm_band_num)}, BC setting(BC_BAND_NUM)={str(bc_dict["BC_BAND_NUM"])}' + "\n"
            raise Exception

        B0_r = degparam_mm_dict["B0_r"]
        B0_g = degparam_mm_dict["B0_g"]
        B0_b = degparam_mm_dict["B0_b"]

        log += f'---- Load files ----' + "\n"
        log += f'BC setting file: {str(bcset)}' + "\n"
        log += f'Degradation parameter -Master Model: {str(degparam_mm)}' + "\n"
        log += f'Degradation parameter -Sub Model: {str(degparam_sm)}' + "\n"
        log += f'Sim condition setting file: {str(simconf)}' + "\n"
        log += f'ini_en: {str(ini_en)}' + "\n"

        log += f'---- Target DBV check ----' + "\n"

        # DBV_NIT Clip(上限・下限値Clip), 有効DBV値(dvb_nit_eff) 生成
        idx_HBM = len(bc_dict["DBV_NIT_DPK"])   # 通常(非DPKモード)のMax Band調査(=HBM)
        if (simconf_dict["DPK_ON"] == 1) and (simconf_dict["DBV_NIT"] >= bc_dict["DBV_NIT_DPK"][0]) :
            dbv_nit_eff = bc_dict["DBV_NIT_DPK"][0] # 上限Clip (DPKモード時)
            log += f'DPK Mode: ON, DBV_NIT={str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        elif (simconf_dict["DPK_ON"] == 0) and (simconf_dict["DBV_NIT"] > bc_dict["DBV_NIT_BC"][idx_HBM]) :
            dbv_nit_eff = bc_dict["DBV_NIT_BC"][idx_HBM] # 上限Clip (非DPKモード時)
            log += f'DPK Mode: OFF, DBV_NIT={str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        elif simconf_dict["DBV_NIT"] < bc_dict["DBV_NIT_BC"][-1] :   # 下限Clip
            dbv_nit_eff = bc_dict["DBV_NIT_BC"][-1]
            log += f'DBV_NIT={str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        else :
            dbv_nit_eff = simconf_dict["DBV_NIT"]
            log += f'{str(simconf_dict["DBV_NIT"])} -> DBV_NIT_EFF={str(dbv_nit_eff)}' + "\n"

        log += f'---- Band Data Extraction ----' + "\n"

        # BC番号(BAND番号)チェック(idx_bc_upp, idx_bc_lwr, upp: 高輝度側 Band)
        arr_desc = np.array(bc_dict["DBV_NIT_BC"][idx_HBM:]) #DBVは降順配列の為，符号反転により昇順に変更
        idx_bc_lwr = np.searchsorted( -1.0 * arr_desc, -1.0 * dbv_nit_eff)
        if idx_bc_lwr == 0 : idx_bc_lwr = 1 + idx_HBM
        elif idx_bc_lwr == len(arr_desc) : idx_bc_lwr = len(arr_desc) - 1 + idx_HBM
        else : idx_bc_lwr += idx_HBM

        idx_bc_upp = idx_bc_lwr - 1

        # Band間補間用データ抽出　：　電流(gi_lut) --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，gi_lut0, gu_lut1, gu_lut2 を抽出 (upp -> lut1, lwr -> lut2)
        # BC0
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            idx_bc0 = 0
            gi_lut0_r = bc_dict["GI_LUT_GRY_BC_R"][:,0]
            gi_lut0_g = bc_dict["GI_LUT_GRY_BC_G"][:,0]
            gi_lut0_b = bc_dict["GI_LUT_GRY_BC_B"][:,0]
        else :
            idx_bc0 = 1
            gi_lut0_r = bc_dict["GI_LUT_GRY_BC_R"][:,1]
            gi_lut0_g = bc_dict["GI_LUT_GRY_BC_G"][:,1]
            gi_lut0_b = bc_dict["GI_LUT_GRY_BC_B"][:,1]
        # BC1
        gi_lut1_r = bc_dict["GI_LUT_GRY_BC_R"][:, int(idx_bc_upp)]
        gi_lut1_g = bc_dict["GI_LUT_GRY_BC_G"][:, int(idx_bc_upp)]
        gi_lut1_b = bc_dict["GI_LUT_GRY_BC_B"][:, int(idx_bc_upp)]
        # BC2
        gi_lut2_r = bc_dict["GI_LUT_GRY_BC_R"][:, int(idx_bc_lwr)]
        gi_lut2_g = bc_dict["GI_LUT_GRY_BC_G"][:, int(idx_bc_lwr)]
        gi_lut2_b = bc_dict["GI_LUT_GRY_BC_B"][:, int(idx_bc_lwr)]

        # gui_lut_extract = [gi_lut0, gu_lut1, gu_lut2]
        gui_lut_extract_r = [gi_lut0_r, gi_lut1_r, gi_lut2_r]
        gui_lut_extract_g = [gi_lut0_g, gi_lut1_g, gi_lut2_g]
        gui_lut_extract_b = [gi_lut0_b, gi_lut1_b, gi_lut2_b]

        log += f'Extracted Band [BC0]: Band{str(idx_bc0)}, [BC1]: Band{str(idx_bc_upp)}, [BC2]: Band{str(idx_bc_lwr)}' + "\n"
        log += f'GI_LUT extraction finished. Peak current extraction started.' + "\n"

        # Band間補間用データ抽出　：　Peak電流 --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，curr_bc0, curr_bc1, curr_bc2を抽出
        # BC0
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            curr_bc0_r = bc_dict["CURR_BC_R"][0]
            curr_bc0_g = bc_dict["CURR_BC_G"][0]
            curr_bc0_b = bc_dict["CURR_BC_B"][0]
        else :
            curr_bc0_r = bc_dict["CURR_BC_R"][1]
            curr_bc0_g = bc_dict["CURR_BC_G"][1]
            curr_bc0_b = bc_dict["CURR_BC_B"][1]
        # BC1
        curr_bc1_r = bc_dict["CURR_BC_R"][int(idx_bc_upp)]
        curr_bc1_g = bc_dict["CURR_BC_G"][int(idx_bc_upp)]
        curr_bc1_b = bc_dict["CURR_BC_B"][int(idx_bc_upp)]
        # BC2
        curr_bc2_r = bc_dict["CURR_BC_R"][int(idx_bc_lwr)]
        curr_bc2_g = bc_dict["CURR_BC_G"][int(idx_bc_lwr)]
        curr_bc2_b = bc_dict["CURR_BC_B"][int(idx_bc_lwr)]

        # curr_bc_extract = [curr_bc0, curr_bc1, curr_bc2]
        curr_bc_extract_r = [curr_bc0_r, curr_bc1_r, curr_bc2_r]
        curr_bc_extract_g = [curr_bc0_g, curr_bc1_g, curr_bc2_g]
        curr_bc_extract_b = [curr_bc0_b, curr_bc1_b, curr_bc2_b]

        log += f' Extracted Peak Current_R (BC0,1,2): [{", ".join(str(i) for i in curr_bc_extract_r)}]' + "\n"
        log += f' Extracted Peak Current_G (BC0,1,2): [{", ".join(str(i) for i in curr_bc_extract_g)}]' + "\n"
        log += f' Extracted Peak Current_B (BC0,1,2): [{", ".join(str(i) for i in curr_bc_extract_b)}]' + "\n"
        log += f'Peak current extraction finished. Peak lum. extraction started.' + "\n"

        # Band間補間用データ抽出　：　Peak輝度 --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，dvb_nit_bc0, dvb_nit_bc1, dvb_nit_bc2, dbv_nit_dpkを抽出
        # BC0
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            dbv_nit_bc0 = bc_dict["DBV_NIT_BC"][0]
            dbv_nit_dpk = bc_dict["DBV_NIT_DPK"][0]
        else :
            dbv_nit_bc0 = bc_dict["DBV_NIT_BC"][1]
            dbv_nit_dpk = bc_dict["DBV_NIT_DPK"][1]
        # BC1,2
        dbv_nit_bc1 = bc_dict["DBV_NIT_BC"][int(idx_bc_upp)]
        dbv_nit_bc2 = bc_dict["DBV_NIT_BC"][int(idx_bc_lwr)]

        # dvb_nit_bc_extract = [dvb_nit_bc0, dvb_nit_bc1, dvb_nit_bc2, dbv_nit_dpk]
        dbv_nit_bc_extract = [dbv_nit_bc0, dbv_nit_bc1, dbv_nit_bc2, dbv_nit_dpk]

        log += f' Extracted Peak Lum. (BC0,1,2,BC0 at APL{str(bc_dict["APL_DPK"])}): [{", ".join(str(i) for i in dbv_nit_bc_extract)}]' + "\n"
        log += f'Peak lum. extraction finished. Duty extraction started.' + "\n"

        # Band間補間用データ抽出　：　Duty --------------------------------------------------------------
        # bc_upp/lwrのidxを参考に，duty_bc1, duty_bc2を抽出
        # BC1,2 (BC0はBC1と常に同じDutyの為不要)
        duty_bc1 = bc_dict["DUTY_BC"][int(idx_bc_upp)]
        duty_bc2 = bc_dict["DUTY_BC"][int(idx_bc_lwr)]

        # duty_bc_extract = [duty_bc1, duty_bc2]
        duty_bc_extract = [duty_bc1, duty_bc2]

        log += f' Extracted Duty (BC1,2): [{", ".join(str(i) for i in duty_bc_extract)}]' + "\n"
        log += f'Duty extraction finished. Deg 2D_Lut extraction started.' + "\n"

        # Band間補間用データ抽出　：　劣化率(残存率) 2D-Lut ------------------------------------------------
        # bc_upp/lwrのidxを参考に，deg_2d_bc1, deg_2d_bc2を抽出
        if (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_DPK"][1]) :
            idx_bc1 = 0
            deg_2d_bc1_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][0,:,:] # DPKモード時BC0をBC1として出力 (APL1)
            deg_2d_bc1_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][0,:,:]
            deg_2d_bc1_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][0,:,:]
            idx_bc2 = idx_HBM
            deg_2d_bc2_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][idx_HBM,:,:]
            deg_2d_bc2_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][idx_HBM,:,:]
            deg_2d_bc2_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][idx_HBM,:,:]

        elif (simconf_dict["DPK_ON"] == 1) and (dbv_nit_eff >= bc_dict["DBV_NIT_BC"][2]) :
            idx_bc1 = 1
            deg_2d_bc1_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][1,:,:] # DPKモード時BC0をBC1として出力 (APL2)
            deg_2d_bc1_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][1,:,:]
            deg_2d_bc1_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][1,:,:]
            idx_bc2 = idx_HBM
            deg_2d_bc2_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][idx_HBM,:,:]
            deg_2d_bc2_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][idx_HBM,:,:]
            deg_2d_bc2_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][idx_HBM,:,:]

        else :
            idx_bc1 = int(idx_bc_upp)
            deg_2d_bc1_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][int(idx_bc_upp),:,:] # 非DPKモード(通常)時はBC1を出力
            deg_2d_bc1_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][int(idx_bc_upp),:,:]
            deg_2d_bc1_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][int(idx_bc_upp),:,:]
            idx_bc2 = int(idx_bc_lwr)
            deg_2d_bc2_r = degparam_sm_dict["DEG_2D_BC_IxDEG_R"][int(idx_bc_lwr),:,:]
            deg_2d_bc2_g = degparam_sm_dict["DEG_2D_BC_IxDEG_G"][int(idx_bc_lwr),:,:]
            deg_2d_bc2_b = degparam_sm_dict["DEG_2D_BC_IxDEG_B"][int(idx_bc_lwr),:,:]

        # deg_2d_bc_extract = [deg_2d_bc1, deg_2d_bc2]
        deg_2d_bc_extract_r = [deg_2d_bc1_r, deg_2d_bc2_r]
        deg_2d_bc_extract_g = [deg_2d_bc1_g, deg_2d_bc2_g]
        deg_2d_bc_extract_b = [deg_2d_bc1_b, deg_2d_bc2_b]

        log += f' Extracted Deg 2D_LUT of BC1: Band{str(idx_bc1)}' + "\n"
        log += f' Extracted Deg 2D_LUT of BC2: Band{str(idx_bc2)}' + "\n"
        log += f'Deg 2D_Lut extraction finished. Input image data is checking..' + "\n"

        # 入力ファイル形式チェック
        root, suffix = os.path.splitext(path_img)
        if suffix == ".mp4" :
            process_type = "mov"
            # 動画ファイル読み込み
            cap_img = cv2.VideoCapture(path_img)
            cap_ht = cv2.VideoCapture(path_htmap)
            # サイズ，フレーム確認
            width = int(cap_img.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap_img.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap_img.get(cv2.CAP_PROP_FPS)
            frame_num = int(cap_img.get(cv2.CAP_PROP_FRAME_COUNT))
            trsh = float(1.0/fps)
        elif suffix == ".png" :
            process_type = "img"
            # 静止画像読み込み
            img = cv2.imread(path_img)
            ht = cv2.imread(path_htmap)
            # サイズ確認
            height, width = img.shape[:2]
            trsh = 1.0
        else :  raise Exception

        log += f'---- Basic Info of Input Img ----' + "\n"
        log += f'Load files: {str(path_img)}' + "\n"
        log += f'Load files: {str(path_htmap)}' + "\n"
        log += f'width:{str(width)}, height:{str(height)}' + "\n"
        log += f'process type: {str(process_type)}' + "\n"
        if process_type == "mov":
            log += f'fps: {str(fps)}' + "\n"
            log += f'Aging period per frame(sec.): {str(trsh * float(simconf_dict["ACCEL_RATIO"]))}' + "\n"
        else :
            log += f'Aging period(sec.): {str(trsh * float(simconf_dict["ACCEL_RATIO"]))}' + "\n"
        log += f'-- start processing --' + "\n"

        # 累積時間Map生成
        if ini_en == 1 :
            if os.path.exists(stat_ini_r) and os.path.exists(stat_ini_g) and os.path.exists(stat_ini_b) :
                stat_r = np.loadtxt(stat_ini_r, delimiter=",", dtype=float)
                stat_g = np.loadtxt(stat_ini_g, delimiter=",", dtype=float)
                stat_b = np.loadtxt(stat_ini_b, delimiter=",", dtype=float)
                log += f'Previously accumulated stress data is used to start the simulation.' + "\n"
            else :
                raise Exception
        else :
            stat_r = np.full((height, width),0.0, dtype = float)
            stat_g = np.full((height, width),0.0, dtype = float)
            stat_b = np.full((height, width),0.0, dtype = float)
            log += f'Start the simulation from an initial stress condition (accumulated stress = 0).' + "\n"

        # 焼き付き画像生成
        if process_type == "mov" :
            # Output設定
            path_output_file = path_output + "/" + str(idx) + "_" + FILE_OUT_IMG + ".mp4"
            fmt = cv2.VideoWriter.fourcc(*"mp4v")
            out = cv2.VideoWriter(path_output_file, fmt, fps, (width, height))
            try:
                for i in range(frame_num):
                    ret_img, img = cap_img.read()
                    ret_ht, ht = cap_ht.read()
                    if not ret_img or not ret_ht : raise Exception

                    # Remark : この関数実行によりimg, stat_r,g,bの中身は直接書き換わります
                    rtn_code_br_img_update  = burn_in_core (
                        tsample=trsh, img = img, ht = ht,
                        bcset_dict = bc_dict, degparam_mm_dict = degparam_mm_dict, degparam_sm_dict=degparam_sm_dict,
                        simconf_dict = simconf_dict,
                        stat_r=stat_r[:],stat_g=stat_g[:],stat_b=stat_b[:],
                        gui_lut_extract_r = gui_lut_extract_r, gui_lut_extract_g = gui_lut_extract_g, gui_lut_extract_b = gui_lut_extract_b,
                        curr_bc_extract_r = curr_bc_extract_r, curr_bc_extract_g = curr_bc_extract_g, curr_bc_extract_b = curr_bc_extract_b,
                        dbv_nit_bc_extract = dbv_nit_bc_extract, duty_bc_extract = duty_bc_extract,
                        deg_2d_bc_extract_r = deg_2d_bc_extract_r, deg_2d_bc_extract_g = deg_2d_bc_extract_g, deg_2d_bc_extract_b = deg_2d_bc_extract_b,
                        dbv_nit_eff = dbv_nit_eff
                    )

                    if rtn_code_br_img_update != 0 : raise Exception

                    out.write(img)
            except : rtn_code = -1
            else : rtn_code = 0
            finally :
                cap_img.release()
                cap_ht.release()
                out.release()
        else :
            # Output設定
            path_output_file = path_output + "/" + str(idx) + "_"  + FILE_OUT_IMG + ".png"
            try :
                # Remark : この関数実行によりimg, stat_r,g,bの中身は直接書き換わります
                rtn_code_br_img_update = burn_in_core(
                    tsample=trsh, img = img, ht = ht,
                    bcset_dict=bc_dict, degparam_mm_dict=degparam_mm_dict, degparam_sm_dict=degparam_sm_dict,
                    simconf_dict=simconf_dict,
                    stat_r=stat_r[:], stat_g=stat_g[:], stat_b=stat_b[:],
                    gui_lut_extract_r=gui_lut_extract_r, gui_lut_extract_g=gui_lut_extract_g, gui_lut_extract_b=gui_lut_extract_b,
                    curr_bc_extract_r=curr_bc_extract_r, curr_bc_extract_g=curr_bc_extract_g, curr_bc_extract_b=curr_bc_extract_b,
                    dbv_nit_bc_extract=dbv_nit_bc_extract, duty_bc_extract=duty_bc_extract,
                    deg_2d_bc_extract_r=deg_2d_bc_extract_r, deg_2d_bc_extract_g=deg_2d_bc_extract_g, deg_2d_bc_extract_b=deg_2d_bc_extract_b,
                    dbv_nit_eff=dbv_nit_eff
                )

                if rtn_code_br_img_update != 0 : raise Exception

                cv2.imwrite(path_output_file, img)
            except : rtn_code = -1
            else : rtn_code = 0
            finally :
                del img
    except : rtn_code = -1 ; log += f'Abnormal End' + "\n"
    else :
        rtn_code = 0
        log += f'Degradation calc. finished. Update the degradation ratio and the accumulated stress.' + "\n"
        # 劣化率更新
        deg_b = np.exp(-1.0 * (stat_b[:] ** B0_b))
        deg_g = np.exp(-1.0 * (stat_g[:] ** B0_g))
        deg_r = np.exp(-1.0 * (stat_r[:] ** B0_r))

        log += f'Output files. Suffix No.: {str(idx)}' + "\n"
        # 劣化情報(累積時間，劣化率)出力
        path_output_file_deg_b  = path_output + "/" + str(idx) + "_"  + FILE_OUT_DEG +"_b" + ".csv"
        path_output_file_deg_g  = path_output + "/" + str(idx) + "_"  + FILE_OUT_DEG +"_g" + ".csv"
        path_output_file_deg_r  = path_output + "/" + str(idx) + "_"  + FILE_OUT_DEG +"_r" + ".csv"
        path_output_file_stat_b = path_output + "/" + str(idx) + "_"  + FILE_OUT_STAT +"_b" + ".csv"
        path_output_file_stat_g = path_output + "/" + str(idx) + "_"  + FILE_OUT_STAT +"_g" + ".csv"
        path_output_file_stat_r = path_output + "/" + str(idx) + "_"  + FILE_OUT_STAT +"_r" + ".csv"

        np.savetxt(path_output_file_deg_b,  deg_b,     delimiter=",")
        np.savetxt(path_output_file_deg_g,  deg_g,     delimiter=",")
        np.savetxt(path_output_file_deg_r,  deg_r,     delimiter=",")
        np.savetxt(path_output_file_stat_b, stat_b[:], delimiter=",")
        np.savetxt(path_output_file_stat_g, stat_g[:], delimiter=",")
        np.savetxt(path_output_file_stat_r, stat_r[:], delimiter=",")

        log += f'Normal End' + "\n"

    finally :  # Logファイル出力
        path_output_file_log = path_output + "/" + str(idx) + "_log.txt"
        with open(path_output_file_log, 'w') as fw:
            fw.write(log)

    return rtn_code

if __name__ == "__main__":
    rtn_out = main()
    if rtn_out == 0:
        print(f'-- Normal End --')
    else :
        print(f'-- Abnormal End -- rtn={str(rtn_out)}')
    sys.exit(rtn_out)

