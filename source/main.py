""" 劣化シミュレータの概略ソフト（コンセプト説明用）
    全体仕様のイメージを説明するためのソフトです。仕様は暫定なので変更可能です。
    以下の入力情報を使って劣化計算を行います。
    入力情報が多いので，幾つかの情報をまとめてたファイルを引数として読み込み処理します
    入力情報の項目は暫定で今後更新される可能性があります
    Input:
     1.Input images (Movie or Static image)
     2.HeatMap images (Movie or Static image)
     3.BC settings
       3-0. DMP_GAIN (Remark necessary?)
       3-1. DBV_NIT_Curr
       3-2. DBV_NIT_BC_U
       3-3. DBV_NIT_BC_L
       3-4. DUTY_Curr
       3-5. DUTY_BC_U
       3-6. DUTY_BC_L
     4.Degradation Model parameters -Master Model
       4-0. N     //加速係数 x RGB
       4-1. K0    //τに近い変数 x RGB
       4-2. Q     //τの温度依存パラメータ x RGB
       4-3. B0    //β x RGB
       4-4. A     //βの温度依存パラメータ x RGB
     5.Degradation Model parameters -Sub Model
       (2D-Lut x BC setting file)  -> [BC,Lev,DegM] x RGB
     6.Sim condition setting
       6-0. AGING_TIME
       6-1. ACCEL_RATIO
       6-2. TMP_H
       6-3. TMP_L
    Remark :
        (Remark) OpenCVでの画像処理だと画素色の並びがBGRの順番 (備忘)
        (Remark) 動画と静止画ではH,Vの順序に注意 (動画：(w,h) 静止画: (h,w)) (備忘)
        (Remark) 温度分布「画像」から”温度”分布への変換（スケーリング）(0-255 -> XX℃ ~ ZZ℃)
        (Remark) 入力画像の想定はRGB or RGGB?
    History :
        2026.07.31 新規作成     M.Matsui
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
path_bcset_file         = "./dbi_input"
path_degparam_MM_file   = "./dbi_conf"
path_degparam_SM_file   = "./dbi_conf"
path_simconf_file       = "./dbi_conf"
path_output             = "./dbi_output"

############################################## Main code ##############################################
def main():
    input_img_file   = str(sys.argv[1])  # filenameで指定(拡張子含む)
    input_htmap_file = str(sys.argv[2])  # filenameで指定(拡張子含む)
    bcset_file       = str(sys.argv[3])  # filenameで指定(拡張子含む)
    degparam_MM_file = str(sys.argv[4])  # filenameで指定(拡張子含む) (RGBまとめて1ファイル)
    degparam_SM_file = str(sys.argv[5])  # filenameで指定(拡張子含む) (BC x Lev x deg x RGB)
    simconf_file     = str(sys.argv[6])  # filenameで指定(拡張子含む)
    stat_r_ini_file  = str(sys.argv[7])  # filenameで指定(拡張子含む)
    stat_g_ini_file  = str(sys.argv[8])  # filenameで指定(拡張子含む)
    stat_b_ini_file  = str(sys.argv[9])  # filenameで指定(拡張子含む)
    ini_en           = str(sys.argv[10])
    oe               =  str(sys.argv[11])
    idx              = str(sys.argv[12])

    rtn = temp_burn_in (
        path_img     = path_input_img_file + "/" + input_img_file,
        path_htmap   = path_input_htmap_file + "/" + input_htmap_file,
        bcset        = path_bcset_file + "/" + bcset_file,
        degparam_mm  = path_degparam_MM_file + "/" + degparam_MM_file,
        #degparam_sm = path_degparam_SM_file + "/" + degparam_SM_file,
        simconf      = path_simconf_file + "/" + simconf_file,
        stat_ini_r   = path_output + "/" + stat_r_ini_file,
        stat_ini_g   = path_output + "/" + stat_g_ini_file,
        stat_ini_b   = path_output + "/" + stat_b_ini_file,
        ini_en       = int(ini_en),
        #oe          = oe,
        idx          = int(idx)
       )

    return rtn

def temp_update_stat_and_burn_img (tsample, img, ht, bcset_dict, degparam_mm_dict, degparam_sm=None, simconf_dict=None, stat_r=None, stat_g=None, stat_b=None) :
    """ 累積時間から劣化率を計算し、その結果に基づき入力画像を劣化画像に更新します。同時に累積時間の更新を行います
        - モデルは暫定です。モデル式が一部未実装の他、現状のモデル式自体にも式に不備あり。あくまで参考版
        - 処理は１画素毎に行います。Block単位での処理は未対応です
    Args:
        :param tsample:
        :param img:
        :param ht:
        :param bcset_dict:
        :param degparam_mm_dict:
        :param degparam_sm:
        :param simconf_dict:
        :param stat_r:
        :param stat_g:
        :param stat_b:
    Returns:
        :return: rtn_code:
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

        height, width = img.shape[:2]

        # 劣化率Map (正しくは輝度残存率)
        deg_r = np.full((height, width), 1.0, dtype=float)
        deg_g = np.full((height, width), 1.0, dtype=float)
        deg_b = np.full((height, width), 1.0, dtype=float)

        # 輝度Map(中間計算用に使用)
        lum_r = np.full((height, width), 0.0, dtype=float)
        lum_g = np.full((height, width), 0.0, dtype=float)
        lum_b = np.full((height, width), 0.0, dtype=float)

        # 温度Map(中間計算用に使用)
        temp = np.full((height, width), TMP_L, dtype=float)

        # 現在の劣化率を累積時間から計算（劣化率更新）
        deg_b[:] = np.exp(-1.0 * (stat_b[:] ** (B0_b + A_b * temp[:])))
        deg_g[:] = np.exp(-1.0 * (stat_g[:] ** (B0_g + A_g * temp[:])))
        deg_r[:] = np.exp(-1.0 * (stat_r[:] ** (B0_r + A_r * temp[:])))

        # 劣化画像の生成
        lum_b[:] = (img[:, :, 0] / 255) ** 2.2 * deg_b
        lum_g[:] = (img[:, :, 1] / 255) ** 2.2 * deg_g
        lum_r[:] = (img[:, :, 2] / 255) ** 2.2 * deg_r

        img[:, :, 0] = (255 * (lum_b[:] ** (1 / 2.2))).astype(np.uint8)
        img[:, :, 1] = (255 * (lum_g[:] ** (1 / 2.2))).astype(np.uint8)
        img[:, :, 2] = (255 * (lum_r[:] ** (1 / 2.2))).astype(np.uint8)

        temp[:] = (ht[:, :, 0] / 255) * (TMP_H - TMP_L) + TMP_L

        # Totalストレス時間の累積
        stat_b[:] += tsample * ACCEL_RATIO * (lum_b[:] ** N_b) / (K0_b * np.exp(Q_b / temp[:]))
        stat_g[:] += tsample * ACCEL_RATIO * (lum_g[:] ** N_g) / (K0_g * np.exp(Q_g / temp[:]))
        stat_r[:] += tsample * ACCEL_RATIO * (lum_r[:] ** N_r) / (K0_r * np.exp(Q_r / temp[:]))
    except :
        rtn_code = -1
    else :
        rtn_code = 0
    finally :
        del deg_r, deg_g, deg_b
        del lum_r, lum_g, lum_b
    return rtn_code

############################################## Main Body ##############################################
def temp_burn_in (
        path_img, path_htmap,
        bcset,
        degparam_mm, degparam_sm=None, simconf=None,
        stat_ini_r=None, stat_ini_g=None, stat_ini_b=None,
        ini_en=0, oe=1, idx=0
    ) :
    """ 映像入力情報の形式(動画.mp4, 静止画.png)を読み取り、引数で与えられた劣化パラメータとSim条件に基づき
        劣化映像を作成，併せて劣化情報(劣化率，ストレス累積時間)を出力します
        - 入力情報が多いので，幾つかの情報をまとめてたファイルを引数として読み込み処理します
        - 出力ファイル名は固定名ですが、引数:idxによりファイル名にprefixとしてidx番号を付与できます
        - 引数としてstat_r,g,bのファイルを指定することで，途中の劣化状態から計算を始めることが出来ます
          ただし、この機能はini_en=1とすることで有効になります（ファイル指定だけでは機能しません）
        - 引数；oeの設定で生成した劣化映像（動画，静止画）の出力を有効・無効化出来ます
          ただし劣化情報はoe設定に依らず出力します　(現在未実装，常に出力)
        - 劣化モデルは暫定で未完成です
        - 例外処理は暫定で不十分です
    Args:
        :param path_img:
        :param path_htmap:
        :param bcset:
        :param degparam_mm:
        :param degparam_sm:
        :param simconf:
        :param stat_ini_r:
        :param stat_ini_g:
        :param stat_ini_b:
        :param ini_en:
        :param oe:
        :param idx:
    Returns:
        :return rtn_code:
    """
    try :
        # File Load 設定値読み込み
        rtn_code_bcset, bc_dict = com_info.load_bcset(bcset)
        rtn_code_degparam_mm, degparam_mm_dict = com_info.load_degparam_mm(degparam_mm)
        rtn_code_simconf, simconf_dict = com_info.load_simconf(simconf)
        if rtn_code_bcset !=0 or rtn_code_degparam_mm != 0 or rtn_code_simconf :
            raise Exception

        B0_r = degparam_mm_dict["B0_r"]
        A_r  = degparam_mm_dict["A_r"]
        B0_g = degparam_mm_dict["B0_g"]
        A_g  = degparam_mm_dict["A_g"]
        B0_b = degparam_mm_dict["B0_b"]
        A_b  = degparam_mm_dict["A_b"]

        TMP_L = simconf_dict["TMP_L"] + 273.0
        TMP_H = simconf_dict["TMP_H"] + 273.0

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
            trsh = 0.0
        else :  raise Exception

        print(f'{"--- Basic Info of Input Img ---"}')
        print(f'{"Load files: "}{str(path_img)}')
        print(f'{"Load files: "}{str(path_htmap)}')
        print(f'{"width:"}{str(width)}{", height:"}{str(height)}')
        print(f'{"process type:"}{str(process_type)}')
        print(f'{"-- start processing --"}')

        # 累積時間Map生成
        if ini_en == 1 :
            if os.path.exists(stat_ini_r) and os.path.exists(stat_ini_g) and os.path.exists(stat_ini_b) :
                stat_r = np.loadtxt(stat_ini_r, delimiter=",", dtype=float)
                stat_g = np.loadtxt(stat_ini_g, delimiter=",", dtype=float)
                stat_b = np.loadtxt(stat_ini_b, delimiter=",", dtype=float)
            else :
                raise Exception
        else :
            stat_r = np.full((height, width),0.0, dtype = float)
            stat_g = np.full((height, width),0.0, dtype = float)
            stat_b = np.full((height, width),0.0, dtype = float)

        # 温度Map(中間計算用に使用)　（モデル式修正に伴い将来的にはこの場所での記述は不要になるかも）
        temp = np.full((height, width),TMP_L, dtype = float)

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
                    rtn_code_br_img_update  = temp_update_stat_and_burn_img (
                        tsample= trsh,
                        img = img, ht=ht, bcset_dict=bc_dict,
                        degparam_mm_dict=degparam_mm_dict, simconf_dict=simconf_dict,
                        stat_r=stat_r[:],stat_g=stat_g[:],stat_b=stat_b[:]
                    )

                    if rtn_code_br_img_update != 0 : raise Exception

                    # 劣化率更新の為，温度分布を更新（※モデル的に問題あり，改善必要）
                    temp[:] = (ht[:, :, 0] / 255) * (TMP_H - TMP_L) + TMP_L
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
                rtn_code_br_img_update = temp_update_stat_and_burn_img(
                    tsample=trsh,
                    img=img, ht=ht, bcset_dict=bc_dict,
                    degparam_mm_dict=degparam_mm_dict, simconf_dict=simconf_dict,
                    stat_r=stat_r[:], stat_g=stat_g[:], stat_b=stat_b[:]
                )

                if rtn_code_br_img_update != 0 : raise Exception

                # 劣化率更新の為，温度分布を更新（※モデル的に問題あり，改善必要）
                temp[:] = (ht[:, :, 0] / 255) * (TMP_H - TMP_L) + TMP_L
                cv2.imwrite(path_output_file, img)
            except : rtn_code = -1
            else : rtn_code = 0
            finally :
                del img
    except : rtn_code = -1
    else :
        rtn_code = 0
        # 劣化率更新
        deg_b = np.exp(-1.0 * (stat_b[:] ** (B0_b + A_b * temp[:])))
        deg_g = np.exp(-1.0 * (stat_g[:] ** (B0_g + A_g * temp[:])))
        deg_r = np.exp(-1.0 * (stat_r[:] ** (B0_r + A_r * temp[:])))

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

    return rtn_code

if __name__ == "__main__":
    rtn_out = main()
    if rtn_out == 0:
        print(f'{"-- Normal End --"}')
    else :
        print(f'{"-- Abnormal End --"}{"rtn="}{str(rtn_out)}')
    sys.exit(rtn_out)

