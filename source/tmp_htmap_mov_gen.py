import cv2
import sys

############################################## Main code ##############################################
def main():
    input_mov_file = str(sys.argv[1])   # fullpathで指定
    blur_w = int(sys.argv[2])
    blur_h = int(sys.argv[3])
    output_mov_file = str(sys.argv[4])   # fullpathで指定

    rtn = htmap_mov_gen_by_blur (input_mov_file, blur_w, blur_h, output_mov_file)
    return rtn

############################################## Main Body ##############################################
def htmap_mov_gen_by_blur (path_mov, ksize_w, ksize_h, path_mov_out) :
    # 動画ファイル読み込み
    cap_img = cv2.VideoCapture(path_mov)

    # サイズ，フレーム確認
    width = int(cap_img.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap_img.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap_img.get(cv2.CAP_PROP_FPS)
    frame_num = int(cap_img.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f'{"--- Basic Info of Input Img ---"}')
    print(f'{"width:"}{str(width)}{", height:"}{str(height)}')
    print(f'{"total_frm:"}{str(frame_num)}')
    print(f'{"--- Temp Heat Map gen (Method: Blur(INTER_AREA))---"}')
    print(f'{"Blur ksize(w,h)"}{"("}{str(ksize_w)}{","}{str(ksize_w)}{")"}')
    print(f'{"Output file name"}{path_mov_out}')
    print(f'{"-- processing --"}')

    fmt = cv2.VideoWriter.fourcc(*"mp4v")
    out = cv2.VideoWriter(path_mov_out, fmt, fps, (width, height))
    try :
        for i in range(frame_num):
            ret, img = cap_img.read()
            if not ret:
                raise Exception
            img_blr = cv2.blur(img, (ksize_w,ksize_h), cv2.BORDER_REPLICATE)
            img_gray_pre = cv2.cvtColor(img_blr, cv2.COLOR_BGR2GRAY)
            img_gray = cv2.cvtColor(img_gray_pre, cv2.COLOR_GRAY2BGR)
            out.write(img_gray)
            del img_blr
            del img_gray_pre
            del img_gray
    except:
        rtn_code = -1
    else:
        rtn_code = 0
    finally:
        cap_img.release()
        out.release()
    return rtn_code

if __name__ == "__main__":
    rtn_out = main()
    if rtn_out == 0:
        print(f'{"-- Normal End --"}')
    else :
        print(f'{"-- Abnormal End --"}{"rtn="}{str(rtn_out)}')
    sys.exit(rtn_out)
