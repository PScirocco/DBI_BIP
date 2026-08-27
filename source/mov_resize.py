import cv2
import numpy as np
import sys

############################################## Main code ##############################################
def main():
    input_mov_file = str(sys.argv[1])   # fullpathで指定
    target_w = int(sys.argv[2])
    target_h = int(sys.argv[3])
    output_mov_file = str(sys.argv[4])   # fullpathで指定

    rtn = mov_resize (input_mov_file, target_w, target_h, output_mov_file)
    return rtn

#-----------------------
## def Functions
#-----------------------
def smart_resize_with_padding(img, target_w, target_h, border_type=cv2.BORDER_CONSTANT, border_value=(0, 0, 0)):
    """
    画像の縦横比を維持したまま拡大・縮小し、指定サイズに収まるようパディングする関数。
    縮小時は INTER_AREA、拡大時は INTER_CUBIC を自動選択
    """
    h, w = img.shape[:2]

    # 1. 縦横の拡大・縮小倍率を計算し、画像の比率を維持できる小さい方の倍率を採用
    scale_w = target_w / w
    scale_h = target_h / h
    scale = min(scale_w, scale_h)

    # 2. 倍率に応じて補間方式（Interpolation）を自動切り替え
    if scale < 1.0:
        # 縮小の場合
        interp = cv2.INTER_AREA
    else:
        # 拡大の場合（バイキュービックを指定。バイリニアなら cv2.INTER_LINEAR）
        interp = cv2.INTER_CUBIC

    # 3. アスペクト比を維持した仮のリサイズサイズを計算
    inter_w = int(w * scale)
    inter_h = int(h * scale)

    # 4. 一次リサイズを実行
    resized_img = cv2.resize(img, (inter_w, inter_h), interpolation=interp)

    # 5. 目標サイズ（target_w, target_h）に合わせるためのパディング量を計算
    # 上下左右に均等に振り分ける（中央配置にするため）
    pad_top = (target_h - inter_h) // 2
    pad_bottom = target_h - inter_h - pad_top
    pad_left = (target_w - inter_w) // 2
    pad_right = target_w - inter_w - pad_left

    # 6. 指定された端数処理（パディング方法）で境界を埋める
    final_img = cv2.copyMakeBorder(
        resized_img,
        top=pad_top, bottom=pad_bottom, left=pad_left, right=pad_right,
        borderType=border_type,
        value=border_value
    )

    return final_img

############################################## Main Body ##############################################
def mov_resize (path_mov, target_w, target_h, path_mov_out) :

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
    print(f'{"--- Resize target ---"}')
    print(f'{"Method: LetterBox(Padding after resizing)"}')
    print(f'{"width:"}{str(target_w)}{", height:"}{str(target_h)}')
    print(f'{"Output file name"}{path_mov_out}')
    print(f'{"-- processing --"}')

    fmt = cv2.VideoWriter.fourcc(*"mp4v")
    out = cv2.VideoWriter(path_mov_out, fmt, fps, (target_w, target_h))

    try:
        for i in range(frame_num):
            ret_img, img = cap_img.read()

            if not ret_img :
                raise Exception
            # 画像Resizeの実行
            resize_img = smart_resize_with_padding(
                img, target_w, target_h,
                border_type=cv2.BORDER_REPLICATE
            )

            out.write(resize_img)
            del resize_img
    except:
        rtn_code = -1
    else:
        rtn_code = 0
    finally:
        cap_img.release()
        out.release()
    return rtn_code

if __name__ == "__main__" :
    rtn_out = main()
    if rtn_out == 0:
        print(f'{"-- Normal End --"}')
    else :
        print(f'{"-- Abnormal End --"}{"rtn="}{str(rtn_out)}')
    sys.exit(rtn_out)
