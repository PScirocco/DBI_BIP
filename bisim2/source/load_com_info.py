import cv2
import numpy as np
import sys

############################################## Main code ##############################################
def load_bcset (bcset) :
    bc_dict = {}
    try :
        with open(bcset, "r", encoding="utf-8-sig") as f_bcset :
            for line in f_bcset :
                dum=line.strip().split(",")
                if dum[0] == "DMP_GAIN" :
                    bc_dict["DMP_GAIN"] = float(dum[1])
                elif dum[0] == "DBV_NIT_CURR" :
                    bc_dict["DBV_NIT_CURR"] = float(dum[1])
                elif dum[0] == "DBV_NIT_BC_U":
                    bc_dict["DBV_NIT_BC_U"] = float(dum[1])
                elif dum[0] == "DBV_NIT_BC_L":
                    bc_dict["DBV_NIT_BC_L"] = float(dum[1])
                elif dum[0] == "DUTY_CURR":
                    bc_dict["DUTY_CURR"] = float(dum[1])
                elif dum[0] == "DUTY_BC_U":
                    bc_dict["DUTY_BC_U"] = float(dum[1])
                elif dum[0] == "DUTY_BC_L":
                    bc_dict["DUTY_BC_L"] = float(dum[1])
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
    except :
        rtn_code = -1
    else :
        rtn_code = 0

    return rtn_code, simconf_dict
