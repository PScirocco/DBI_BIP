import cv2
import numpy as np
import sys

width = 480
height = 270
col = 3

img = np.full((height, width, col), 0.0, dtype=np.uint8)
img[:,:,0] = 255
img[:,:,1] = 255
img[:,:,2] = 255

cv2.imwrite("./eval_img.png", img)
