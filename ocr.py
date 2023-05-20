#!/usr/bin/env python3

import cv2
import sys
import os
import json
from sys import argv
from collections import namedtuple
import imutils
import numpy as np

DIGITS_LOOKUP = {
	(1, 1, 1, 0, 1, 1, 1): 0,
	(0, 0, 1, 0, 0, 1, 0): 1,
	(1, 0, 1, 1, 1, 0, 1): 2,
	(1, 0, 1, 1, 0, 1, 1): 3,
	(0, 1, 1, 1, 0, 1, 0): 4,
	(1, 1, 0, 1, 0, 1, 1): 5,
	(1, 1, 0, 1, 1, 1, 1): 6,
	(1, 0, 1, 0, 0, 1, 0): 7,
	(1, 1, 1, 1, 1, 1, 1): 8,
	(1, 1, 1, 1, 0, 1, 1): 9
}

SEGMENT_NAMES = [
  "top",
  "top-left",
  "top-right",
  "center",
  "bottom-left",
  "bottom-right", 
  "bottom",
]
DEBUG_DIR = os.getenv("DEBUG")

def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

def img_transform(cropped_image):
    gray = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2GRAY)
    #thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU )[1]
    #blur = cv2.GaussianBlur(gray,(3,3),0)
    #thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU )[1]
    
    thresh = cv2.adaptiveThreshold(gray,255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 37, -26)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (1, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    inverted = cv2.bitwise_not(thresh)
    return inverted


def save_debug_img(img, img_basepath, name):
    if not DEBUG_DIR: return
    idir = os.path.join(DEBUG_DIR, img_basepath)
    if not os.path.exists(idir):
        os.mkdir(idir)
    cv2.imwrite(os.path.join(idir, name), img)
    
def find_top_bottom(c):

    # determine the most extreme points along the contour
    extLeft = tuple(c[c[:, :, 0].argmin()][0])
    extRight = tuple(c[c[:, :, 0].argmax()][0])
    extTop = tuple(c[c[:, :, 1].argmin()][0])
    extBot = tuple(c[c[:, :, 1].argmax()][0])
    height = extBot[1] - extTop[1]
    width = extRight[0] - extLeft[0]
    return (extLeft, extRight, extTop, extBot, width, height)

def sort_contours(cnts, method="left-to-right"):
    '''
    sort_contours : Function to sort contours
    argument:
        cnts (array): image contours
        method(string) : sorting direction
    output:
        cnts(list): sorted contours
        boundingBoxes(list): bounding boxes
    '''
    # initialize the reverse flag and sort index
    reverse = False
    i = 0

    # handle if we need to sort in reverse
    if method == "right-to-left" or method == "bottom-to-top":
        reverse = True

    # handle if we are sorting against the y-coordinate rather than
    # the x-coordinate of the bounding box
    if method == "top-to-bottom" or method == "bottom-to-top":
        i = 1

    # construct the list of bounding boxes and sort them from top to
    # bottom
    boundingBoxes = [cv2.boundingRect(c) for c in cnts]
    (cnts, boundingBoxes) = zip(*sorted(zip(cnts, boundingBoxes),
        key=lambda b:b[1][i], reverse=reverse))

    # return the list of sorted contours and bounding boxes
    return (cnts, boundingBoxes)

def process_img(img_path):
    img_basepath = os.path.basename(img_path)
    test_img = cv2.imread(img_path)
    
    
    # pre-process the image by resizing it, converting it to
    # graycale, blurring it, and computing an edge map
    image = imutils.resize(test_img, height=1080)
    save_debug_img(image, img_basepath, "00-input.png")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 200, 255)
    save_debug_img(edged, img_basepath, "01-edged.png")
    
    # find contours in the edge map, then sort them by their
    # size in descending order
    cnts = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
    ariston_logo_cnt = None
    
    color = (0, 0, 255)
    i = 0
    for c in cnts:
        i+= 1
        if DEBUG_DIR:
            aimage = image.copy()
            cv2.polylines(aimage, c, True, color, 3)
            save_debug_img(aimage, img_basepath, "02-logocandidates-"+str(i)+".png")
        # approximate the contour
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        (x, y, w, h) = cv2.boundingRect(approx)
        eprint("contour for log candidate", i, len(approx), w)
        if len(approx) in [5,6] and w < 100:
            ariston_logo_cnt = c
            break

    if ariston_logo_cnt is None:
        eprint("logo not found")
        return

    (alogo_left, alogo_right, alogo_top, alogo_bottom, alogo_width, alogo_height) = find_top_bottom(ariston_logo_cnt)
    if DEBUG_DIR:
        eprint("ariston logo cnt", alogo_left, alogo_right, alogo_top, alogo_bottom, alogo_width, alogo_height)
        aimage = image.copy()
        cv2.polylines(aimage, ariston_logo_cnt, True, color, 3)
        save_debug_img(aimage, img_basepath, "03-logo.png")
    display_lx = alogo_right[0] + int(alogo_width*2.4)
    display_rx = alogo_right[0] + int(alogo_width*4.8)
    display_ty = alogo_bottom[1] + int(alogo_height*1.6)
    display_by = alogo_bottom[1] + int(alogo_height*2.8)
    display_box = np.array([
        [ display_lx, display_ty ],  # top left
        [ display_rx, display_ty ],  # top right
        [ display_rx, display_by ],  # bottom right
        [ display_lx, display_by ],  # bottom left
    ])
    if DEBUG_DIR:
        eprint("display box", display_box)
        aimage = image.copy()
        cv2.polylines(aimage, [display_box], True, color, 3)
        save_debug_img(aimage, img_basepath, "04-display-box-on-full.png")
    
    cropped_test_img = image[display_ty:display_by, display_lx:display_rx]    
    save_display_pic = os.getenv("SAVE_DISPLAY_PATH")
    if save_display_pic:
        cv2.imwrite(save_display_pic, cropped_test_img)
    save_debug_img(cropped_test_img, img_basepath, "05-cropped-display-box.png")
    thresh_cropped_test_img = img_transform(cropped_test_img)
    save_debug_img(thresh_cropped_test_img, img_basepath, "06-cropped-threshed-display-box.png")

    # find contours in the thresholded image, then initialize the
    # digit contours lists
    cnts = cv2.findContours(thresh_cropped_test_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    digitCnts = []

    # loop over the digit area candidates
    d = 0
    for c in cnts:
        d += 1
        # compute the bounding box of the contour
        (x, y, w, h) = cv2.boundingRect(c)
        if DEBUG_DIR:
            eprint("digit contour", d, x, y, w, h)
            aimage = cropped_test_img.copy()
            cv2.polylines(aimage, c, True, color, 3)
            save_debug_img(aimage, img_basepath, "07-digit-cnt-"+str(d)+".png")

        # if the contour is sufficiently large, it must be a digit
        if (w >= 10 and w <= 55) and (h >= 44 and h <= 75):
            eprint("saving digit", d, x, y, w, h)
            digitCnts.append(c)
    if len(digitCnts) < 2:
        return
    digitCnts = sort_contours(digitCnts, method="left-to-right")[0]
    result = ""
    d = 0
    # loop over each of the digits
    for c in digitCnts:
        d+=1
        # extract the digit ROI
        (x, y, w, h) = cv2.boundingRect(c)
        eprint("bounding", d, x, y, w, h)
        roi = thresh_cropped_test_img[y:y + h, x:x + w]
        if DEBUG_DIR:
            color_roi = cropped_test_img[y:y + h, x:x + w]
            save_debug_img(roi, img_basepath, "07-digit-d"+str(d)+".png")

        # compute the width and height of each of the 7 segments
        # we are going to examine
        (roiH, roiW) = roi.shape
        (dW, dH) = (int(roiW * 0.25), int(roiH * 0.15))
        dHC = int(roiH * 0.05)

        # define the set of 7 segments
        segments = [
            ((0, 0), (w, dH)),	                         # top
            ((0, 0), (dW, h // 2)),	                     # top-left
            ((w - dW, 0), (w, h // 2)),	                 # top-right
            ((0, (h // 2) - dHC) , (w, (h // 2) + dHC)), # center
            ((0, h // 2), (dW, h)),	                     # bottom-left
            ((w - dW, h // 2), (w, h)),	                 # bottom-right
            ((0, h - dH), (w, h))                        # bottom
        ]
        on = [0] * len(segments)
        
    
        # loop over the segments
        for (i, ((xA, yA), (xB, yB))) in enumerate(segments):
            if DEBUG_DIR:
                acolor_roi = cv2.rectangle(color_roi.copy(), (xA, yA), (xB, yB), (0, 0, 255), 2)
                save_debug_img(acolor_roi, img_basepath, "07-digit-d"+str(d)+"-"+str(i)+".png")
            # extract the segment ROI, count the total number of
            # thresholded pixels in the segment, and then compute
            # the area of the segment
            segROI = roi[yA:yB, xA:xB]
            total = cv2.countNonZero(segROI)
            area = (xB - xA) * (yB - yA)

            # if the total number of non-zero pixels is greater than
            # 50% of the area, mark the segment as "on"
            eprint("flood", d, i, SEGMENT_NAMES[i], total / float(area))
            if total / float(area) > 0.50:
                on[i]= 1

        
        if w < int(alogo_width/3): # this is super thin, probably digit 1. the horizontal ones dont make a sense here
            on[0] = 0 # top
            on[3] = 0 # center
            on[6] = 0 # bottom
            on[2] = 1 if on[1] or on[2] else 0
            on[5] = 1 if on[4] or on[5] else 0
            on[1] = 0
            on[4] = 0

        # lookup the digit and draw it on the image
        eprint("digits slices", on)
        digit = DIGITS_LOOKUP.get(tuple(on))
        if digit is None:
            return
        result += str(digit)

    return int(result)


def do_the_job(*imgs):
    re = []
    for img in imgs:
        re.append(process_img(img))
    return re
    
if __name__ == "__main__":
    x = do_the_job(*sys.argv[1:])
    print(json.dumps(x))
