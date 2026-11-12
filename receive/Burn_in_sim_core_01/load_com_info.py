import cv2
import numpy as np
import sys

############################################## Main code ##############################################
def load_bcset (bcset) :
    bc_dict = {}
    pattern = r'([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'      # 数値のみ抽出
    gi_lut_word = 0
    bc_num = 0
    try :
        with open(bcset, "r", encoding="utf-8-sig") as f_bcset :
            while True :
                line = f_bcset.readline()
                if not line : break

                dum = line.strip().split(",")
                if not dum or dum[0] == "" : continue
                if dum[0] == "BC_BAND_NUM" :
                    bc_dict["BC_BAND_NUM"] = int(dum[1])
                    bc_num = int(dum[1])

                elif dum[0] == "APL_DPK" :
                    bc_dict["APL_DPK"] = float(dum[1])

                elif dum[0] == "DBV_NIT_DPK":
                    bc_dict["DBV_NIT_DPK"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])

                elif dum[0] == "DBV_NIT_BC":
                    bc_dict["DBV_NIT_BC"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])

                elif dum[0] == "DUTY_BC":
                    bc_dict["DUTY_BC"]  = np.array([float(x) for x in dum[1:] if x.strip() != ''])

                elif dum[0] == "CURR_BC_R":
                    bc_dict["CURR_BC_R"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])

                elif dum[0] == "CURR_BC_G":
                    bc_dict["CURR_BC_G"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])

                elif dum[0] == "CURR_BC_B":
                    bc_dict["CURR_BC_B"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])

                elif dum[0] == "CURR_RATIO":
                    bc_dict["CURR_RATIO_R"] = float(dum[1])
                    bc_dict["CURR_RATIO_G"] = float(dum[2])
                    bc_dict["CURR_RATIO_B"] = float(dum[3])

                elif dum[0] == "GI_LUT_WRD_GRY":
                    bc_dict["GI_LUT_WRD_GRY"] = int(dum[1])
                    gi_lut_word = int(dum[1])

                elif dum[0] == "GI_LUT_GRY":
                    bc_dict["GI_LUT_GRY"] = np.array([int(x) for x in dum[1:] if x.strip() != ''])
                    if len(bc_dict["GI_LUT_GRY"]) != gi_lut_word : raise Exception
                    break

            data_array = np.fromregex(f_bcset, pattern, dtype=[('f', float)])
            data_array_2d = data_array['f'].reshape(-1, bc_num * 3)     # 3 = "RGB"
            if data_array_2d.shape[0] != gi_lut_word : raise Exception
            data_array_3d = data_array_2d.reshape(gi_lut_word, bc_num, 3)
            bc_dict["GI_LUT_GRY_BC_R"] = data_array_3d[:,:,0]
            bc_dict["GI_LUT_GRY_BC_G"] = data_array_3d[:,:,1]
            bc_dict["GI_LUT_GRY_BC_B"] = data_array_3d[:,:,2]
    except :
        rtn_code = -1
    else :
        rtn_code = 0

    return rtn_code, bc_dict


def load_degparam_mm (degparam_mm) :
    degparam_mm_dict = {}
    try :
        with open(degparam_mm, "r", encoding="utf-8-sig") as f_degparam_mm :
            for line in f_degparam_mm :
                dum=line.strip().split(",")
                if dum[0] == "N" :
                    degparam_mm_dict["N_r"] = float(dum[1])
                    degparam_mm_dict["N_g"] = float(dum[2])
                    degparam_mm_dict["N_b"] = float(dum[3])

                elif dum[0] == "K0" :
                    degparam_mm_dict["K0_r"] = float(dum[1])
                    degparam_mm_dict["K0_g"] = float(dum[2])
                    degparam_mm_dict["K0_b"] = float(dum[3])

                elif dum[0] == "Q":
                    degparam_mm_dict["Q_r"] = float(dum[1])
                    degparam_mm_dict["Q_g"] = float(dum[2])
                    degparam_mm_dict["Q_b"] = float(dum[3])

                elif dum[0] == "B0":
                    degparam_mm_dict["B0_r"] = float(dum[1])
                    degparam_mm_dict["B0_g"] = float(dum[2])
                    degparam_mm_dict["B0_b"] = float(dum[3])

                elif dum[0] == "A":
                    degparam_mm_dict["A_r"] = float(dum[1])
                    degparam_mm_dict["A_g"] = float(dum[2])
                    degparam_mm_dict["A_b"] = float(dum[3])
    except :
        rtn_code = -1
    else :
        rtn_code = 0

    return rtn_code, degparam_mm_dict


def load_simconf (simconf) :
    simconf_dict = {}
    try :
        with open(simconf, "r", encoding="utf-8-sig") as f_simconf :
            for line in f_simconf :
                dum=line.strip().split(",")
                if dum[0] == "AGING_TIME" :
                    simconf_dict["AGING_TIME"] = float(dum[1])

                elif dum[0] == "ACCEL_RATIO" :
                    simconf_dict["ACCEL_RATIO"] = float(dum[1])

                elif dum[0] == "TMP_L":
                    simconf_dict["TMP_L"] = float(dum[1])

                elif dum[0] == "TMP_H":
                    simconf_dict["TMP_H"] = float(dum[1])

                elif dum[0] == "DBV_NIT":
                    simconf_dict["DBV_NIT"] = float(dum[1])

                elif dum[0] == "DPK_ON":
                    simconf_dict["DPK_ON"] = int(dum[1])

                elif dum[0] == "GADJ":
                    simconf_dict["GADJ_R"] = float(dum[1])
                    simconf_dict["GADJ_G"] = float(dum[2])
                    simconf_dict["GADJ_B"] = float(dum[3])
    except :
        rtn_code = -1
    else :
        rtn_code = 0

    return rtn_code, simconf_dict


def load_degparam_sm (degparam_sm) :
    degparam_sm_dict = {}
    word_axis_deg = 0
    word_axis_i = 0
    pattern = r'([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'      # 数値のみ抽出
    try :
        with open(degparam_sm, "r", encoding="utf-8-sig") as f_degparam_sm :
            while True :
                line = f_degparam_sm.readline()
                if not line : break

                dum = line.strip().split(",")
                if not dum or dum[0] == "" : continue

                if dum[0] == "DEG_2D_WRD_DEG" :
                    degparam_sm_dict["DEG_2D_WRD_DEG"] = int(dum[1])
                    word_axis_deg = int(dum[1])

                elif dum[0] == "DEG_2D_DEG_R" :
                    degparam_sm_dict["DEG_2D_DEG_R"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])
                    if len(degparam_sm_dict["DEG_2D_DEG_R"]) != word_axis_deg : raise Exception

                elif dum[0] == "DEG_2D_DEG_G" :
                    degparam_sm_dict["DEG_2D_DEG_G"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])
                    if len(degparam_sm_dict["DEG_2D_DEG_G"]) != word_axis_deg : raise Exception

                elif dum[0] == "DEG_2D_DEG_B" :
                    degparam_sm_dict["DEG_2D_DEG_B"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])
                    if len(degparam_sm_dict["DEG_2D_DEG_B"]) != word_axis_deg : raise Exception

                elif dum[0] == "DEG_2D_WRD_I":
                    degparam_sm_dict["DEG_2D_WRD_I"] = int(dum[1])
                    word_axis_i = int(dum[1])

                elif dum[0] == "DEG_2D_I_R":
                    degparam_sm_dict["DEG_2D_I_R"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])
                    if len(degparam_sm_dict["DEG_2D_I_R"]) != word_axis_i: raise Exception

                elif dum[0] == "DEG_2D_I_G":
                    degparam_sm_dict["DEG_2D_I_G"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])
                    if len(degparam_sm_dict["DEG_2D_I_G"]) != word_axis_i: raise Exception

                elif dum[0] == "DEG_2D_I_B":
                    degparam_sm_dict["DEG_2D_I_B"] = np.array([float(x) for x in dum[1:] if x.strip() != ''])
                    if len(degparam_sm_dict["DEG_2D_I_B"]) != word_axis_i: raise Exception
                    break

            data_array = np.fromregex(f_degparam_sm, pattern, dtype=[('f', float)])
            data_array_2d = data_array['f'].reshape(-1, word_axis_deg * 3)      # 3="RGB"
            bc_num = data_array_2d.shape[0] // word_axis_i
            data_array_4d = data_array_2d.reshape(bc_num,word_axis_i, 3, word_axis_deg)      # BC x 2d-lut axis-i x RGB x 2d-lut axis-deg
            degparam_sm_dict["DEG_2D_BC_IxDEG_R"] = data_array_4d[:,:,0,:]
            degparam_sm_dict["DEG_2D_BC_IxDEG_G"] = data_array_4d[:,:,1,:]
            degparam_sm_dict["DEG_2D_BC_IxDEG_B"] = data_array_4d[:,:,2,:]
    except :
        rtn_code = -1
    else :
        rtn_code = 0

    return rtn_code, degparam_sm_dict
