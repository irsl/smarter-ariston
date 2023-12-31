#!/usr/bin/env python3

import cv2
import sys
import os
import json
from sys import argv
from collections import namedtuple
import imutils
from imutils.perspective import four_point_transform
import numpy as np
from collections import defaultdict

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
MIN_FLOOD_PERCENTAGE = 0.44
DEBUG_DIR = os.getenv("DEBUG")

def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

def img_transform(cropped_image):
    gray = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2GRAY)
    #thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU )[1]
    #blur = cv2.GaussianBlur(gray,(3,3),0)
    #thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU )[1]
    
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 37, -30)
    
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


def calculate_contour_distance(contour1, contour2): 
    x1, y1, w1, h1 = cv2.boundingRect(contour1)
    c_x1 = x1 + w1/2
    c_y1 = y1 + h1/2

    x2, y2, w2, h2 = cv2.boundingRect(contour2)
    c_x2 = x2 + w2/2
    c_y2 = y2 + h2/2

    return max(abs(c_x1 - c_x2) - (w1 + w2)/2, abs(c_y1 - c_y2) - (h1 + h2)/2)

def merge_contours(contour1, contour2):
    return np.concatenate((contour1, contour2), axis=0)

# this is borrowed from here: https://inf.news/en/news/750c405b8bcdb61dda3d24ee49855c74.html
def agglomerative_cluster(contours, threshold_distance=40.0):
    current_contours = list(contours)
    while len(current_contours) > 1:
        min_distance = None
        min_coordinate = None

        for x in range(len(current_contours)-1):
            for y in range(x+1, len(current_contours)):
                distance = calculate_contour_distance(current_contours[x], current_contours[y])
                if min_distance is None:
                    min_distance = distance
                    min_coordinate = (x, y)
                elif distance < min_distance:
                    min_distance = distance
                    min_coordinate = (x, y)

        if min_distance < threshold_distance:
            index1, index2 = min_coordinate
            current_contours[index1] = merge_contours(current_contours[index1], current_contours[index2])
            del current_contours[index2]
        else: 
            break

    return current_contours

def process_img(img_path):
    img_basepath = os.path.basename(img_path)
    test_img = cv2.imread(img_path)
    
    
    # pre-process the image by resizing it, converting it to
    # graycale, blurring it, and computing an edge map
    image = imutils.resize(test_img, height=1080)
    save_debug_img(image, img_basepath, "00-input.png")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (11, 11), 0)
    
    thresh = cv2.adaptiveThreshold(blurred,255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 37, -30)    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (1, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    
    edged = cv2.Canny(thresh, 50, 200, 255)
    save_debug_img(edged, img_basepath, "01-edged.png")
    
    # find contours in the edge map, then sort them by their
    # size in descending order
    cnts = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
    ariston_logo_cnt = None
    manual_displaybox_cnt = None
    top_helper_cnt = None
    outer_top_helper_cnt = None
    top_line_cnt = None
    left_curly_stuff_cnt = None
    
    reference_cnts = defaultdict(list)
    
    left_curly_ty_shift = 0
    right_curly_ty_shift = 0
    color = (0, 0, 255)
    i = 0
    for c in cnts:
        i+= 1
        if i > 10:
            break
        if DEBUG_DIR:
            aimage = image.copy()
            cv2.polylines(aimage, c, True, color, 3)
            save_debug_img(aimage, img_basepath, "02-logocandidates-"+str(i)+".png")
        # approximate the contour
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        (x, y, w, h) = cv2.boundingRect(approx)
        l = len(approx)
        eprint("contour for log candidate", i, l, len(c), w, h)
        if l in [3, 4] and w > 1313 and w < 1450 and h > 80 and h < 120:
            eprint("potential top line found")
            reference_cnts["top_line"].append(c)
        elif l == 6 and len(c) > 300 and c[0][0][0] < 600 and w > 300 and w < 340 and h > 125 and h < 150:
            eprint("potential left_curly_stuff_cnt found")
            reference_cnts["left_curly_stuff"].append(c)
            left_curly_ty_shift = 0
        elif l == 6 and len(c) > 240 and c[0][0][0] < 600 and w > 220 and w < 260 and h > 125 and h < 150:
            eprint("potential left_curly_stuff_cnt 2 found")
            reference_cnts["left_curly_stuff"].append(c)
            left_curly_ty_shift = 10
        elif l == 6 and len(c) > 230 and c[0][0][0] > 600 and w > 300 and w < 340 and h > 125 and h < 150:
            eprint("potential right_curly_stuff_cnt found")
            reference_cnts["right_curly_stuff"].append(c)
            right_curly_ty_shift = -20
        elif l == 6 and len(c) > 180 and c[0][0][0] > 600 and w > 250 and w < 300 and h > 125 and h < 150:
            eprint("potential right_curly_stuff_cnt 2 found")
            reference_cnts["right_curly_stuff"].append(c)
            right_curly_ty_shift = 5
        elif l == 4 and w > 260 and w < 285 and h > 160 and h < 170:
            eprint("potential top_helper_cnt found (inner)")
            reference_cnts["top_helper"].append(c)
        elif l in [4,6] and w >= 286 and w < 300 and h > 170 and h < 195:
            eprint("potential top_helper_cnt found (outer)")
            reference_cnts["outer_top_helper"].append(c)
            reference_cnts["outer_top_helper_new_pos"].append(c)
        elif l == 4 and w > 180 and w < 220:
            eprint("potential manual display boundary found")
            reference_cnts["manual_display"].append(c)
        elif reference_cnts.get("ariston_logo") is None and l in [5,6] and w < 100:
            eprint("potential ariston logo found")
            reference_cnts["ariston_logo"].append(c)

    eprint("potential reference point categories", reference_cnts.keys())
    cnt_counter = 0
    for reference_category in ["left_curly_stuff",  "right_curly_stuff", "outer_top_helper_new_pos", "outer_top_helper", "top_helper", "top_line", "manual_display", "ariston_logo"]:
        cnts = reference_cnts.get(reference_category)
        if cnts is None:
            continue
        eprint("trying to extract the digits using reference category", reference_category)
        for ref_cnt in cnts:
        
            cnt_counter += 1
            
            eprint("reference category counter", cnt_counter)
        
    
            if reference_category == "top_line":
                (fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height) = find_top_bottom(ref_cnt)
                eprint("coordinates of top_line_cnt:", fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height)
                box_width = int(fd_width / 8)
                box_height = int(fd_width / 16)
                display_lx = fd_left[0] + int(box_width * 4)
                display_rx = display_lx + box_width
                display_ty = fd_bottom[1] + int(box_height * 2.3)
                display_by = display_ty + box_height
                digit_one_upper_length = int(fd_width / 65)
                cnt_retrieval_mode = cv2.RETR_LIST

            elif reference_category == "left_curly_stuff":
                (fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height) = find_top_bottom(ref_cnt)
                eprint("coordinates of left_curly_stuff_cnt:", fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height)
                box_width = int(fd_width / 2.1)
                box_height = int(fd_width / 3.2)
                display_lx = fd_right[0] + int(box_width * 1.3)
                display_rx = display_lx + box_width
                display_ty = fd_right[1] + left_curly_ty_shift
                display_by = display_ty + box_height
                digit_one_upper_length = int(fd_width / 15)
                cnt_retrieval_mode = cv2.RETR_LIST

            elif reference_category == "right_curly_stuff":
                (fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height) = find_top_bottom(ref_cnt)
                eprint("coordinates of right_curly_stuff_cnt:", fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height)
                box_width = int(fd_width / 2.3)
                box_height = int(fd_width / 3.4)
                display_rx = fd_left[0] - int(box_width * 0.3)
                display_lx = display_rx - box_width
                display_ty = fd_left[1] + right_curly_ty_shift
                display_by = display_ty + box_height
                digit_one_upper_length = int(fd_width / 15)
                cnt_retrieval_mode = cv2.RETR_LIST

                
            elif reference_category == "outer_top_helper":
                (fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height) = find_top_bottom(ref_cnt)
                eprint("coordinates of outer_top_helper_cnt:", fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height)
                display_lx = fd_left[0] + 40
                display_rx = fd_right[0] - int(fd_width*0.4)
                display_ty = fd_bottom[1] + int(fd_height * 1.2)
                display_by = display_ty + int(fd_height*0.55)
                digit_one_upper_length = int(fd_width / 14)
                cnt_retrieval_mode = cv2.RETR_LIST

            elif reference_category == "outer_top_helper_new_pos":
                (fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height) = find_top_bottom(ref_cnt)
                eprint("coordinates of outer_top_helper_new_pos_cnt:", fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height)
                display_lx = fd_left[0] + int(fd_width/3.2)
                display_rx = fd_right[0] - int(fd_width*0.25)
                display_ty = fd_bottom[1] + int(fd_height * 1.5)
                display_by = display_ty + int(fd_height*0.5)
                digit_one_upper_length = int(fd_width / 14)
                cnt_retrieval_mode = cv2.RETR_LIST

            elif reference_category == "top_helper":
                (fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height) = find_top_bottom(ref_cnt)
                eprint("coordinates of top_helper_cnt:", fd_left, fd_right, fd_top, fd_bottom, fd_width, fd_height)
                display_lx = fd_left[0] + 20
                display_rx = fd_right[0] - int(fd_width*0.4)
                display_ty = fd_bottom[1] + int(fd_height * 1.375)
                display_by = display_ty + int(fd_height*0.55)
                digit_one_upper_length = int(fd_width / 14)
                cnt_retrieval_mode = cv2.RETR_LIST

            elif reference_category == "manual_display":
                # extract the thermostat display, apply a perspective transform
                # to it
                #reshaped = manual_displaybox_cnt.reshape(-1, 1, 4, 2)
                #warped = four_point_transform(gray, reshaped)
                #output = four_point_transform(image, reshaped)
                (alogo_left, alogo_right, alogo_top, alogo_bottom, alogo_width, alogo_height) = find_top_bottom(ref_cnt)
                display_lx = alogo_left[0] + int(alogo_width/10)
                display_rx = alogo_right[0] - int(alogo_width/3.5) + 1
                display_ty = alogo_top[1] + 20
                display_by = alogo_bottom[1] - 20
                cnt_retrieval_mode = cv2.RETR_LIST
                # a regular digit has width around 50px; this division results width around 20px
                digit_one_upper_length = int(alogo_width/10)

            elif reference_category == "ariston_logo":
                (alogo_left, alogo_right, alogo_top, alogo_bottom, alogo_width, alogo_height) = find_top_bottom(ref_cnt)
                display_lx = alogo_right[0] + int(alogo_width*2.4)
                display_rx = alogo_right[0] + int(alogo_width*4.8)
                display_ty = alogo_bottom[1] + int(alogo_height*1.6)
                display_by = alogo_bottom[1] + int(alogo_height*2.8)
                cnt_retrieval_mode = cv2.RETR_EXTERNAL
                digit_one_upper_length = int(alogo_width/3)        
            else:
                raise Exception("should never happen")
                
            eprint("digit_one_length", digit_one_upper_length)
            display_box = np.array([
                [ display_lx, display_ty ],  # top left
                [ display_rx, display_ty ],  # top right
                [ display_rx, display_by ],  # bottom right
                [ display_lx, display_by ],  # bottom left
            ])

            if DEBUG_DIR:
                eprint("display box", reference_category, display_box)
                aimage = image.copy()
                cv2.polylines(aimage, [display_box], True, color, 3)
                save_debug_img(aimage, img_basepath, f"04-{reference_category}-{cnt_counter}-display-box-on-full.png")

            cropped_test_img = image[display_ty:display_by, display_lx:display_rx]    
            save_display_pic = os.getenv("SAVE_DISPLAY_PATH")
            if save_display_pic:
                cv2.imwrite(save_display_pic, cropped_test_img)
            save_debug_img(cropped_test_img, img_basepath, f"05-{reference_category}-{cnt_counter}-cropped-display-box.png")
            thresh_cropped_test_img = img_transform(cropped_test_img)
            save_debug_img(thresh_cropped_test_img, img_basepath, f"06-{reference_category}-{cnt_counter}-cropped-threshed-display-box.png")

            # find contours in the thresholded image, then initialize the
            # digit contours lists
            cnts = cv2.findContours(thresh_cropped_test_img.copy(), cnt_retrieval_mode, cv2.CHAIN_APPROX_SIMPLE)
            cnts = imutils.grab_contours(cnts)
            
            # sometimes when the picture is excellent quality we need to merge close contours
            if len(cnts) >= 8:
                cnts = agglomerative_cluster(cnts, 3)
            
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
                    save_debug_img(aimage, img_basepath, f"07-{reference_category}-{cnt_counter}-digit-cnt-{d}.png")

                # if the contour is sufficiently large, it must be a digit
                if (w >= 10 and w <= 62) and (h >= 44 and h <= 85):
                    eprint("saving digit", d, x, y, w, h)
                    digitCnts.append(c)
            if len(digitCnts) < 2:
                eprint("we didn't find enough digits")
                continue
            digitCnts = sort_contours(digitCnts, method="left-to-right")[0]
            result = ""
            failure = False
            d = 0
            # loop over each of the digits
            for c in digitCnts:
                d+=1
                if d > 2:
                    break
                # extract the digit ROI
                (x, y, w, h) = cv2.boundingRect(c)
                eprint("bounding", d, x, y, w, h)
                color_roi = cropped_test_img[y:y + h, x:x + w]
                roi = img_transform(color_roi)
                if DEBUG_DIR:
                    save_debug_img(roi, img_basepath, f"07-{reference_category}-{cnt_counter}-digit-d{d}.png")

                # compute the width and height of each of the 7 segments
                # we are going to examine
                (roiH, roiW) = roi.shape
                (dW, dH) = (int(roiW * 0.21), int(roiH * 0.15))
                dHC = int(roiH * 0.05)
                
                if w < digit_one_upper_length:
                    # this is super thin, probably digit 1. 20% is not enough
                    dW = dW * 3

                # define the set of 7 segments
                segments = [
                    ((0, 0), (w, dH)),	                         # top
                    ((0, 0), (dW, h // 2)),	                     # top-left
                    ((w - dW, 0), (w, h // 2)),	                 # top-right
                    ((0, (h // 2) - dHC) , (w, (h // 2) + dHC)), # center
                    ((0, h // 2), (dW, h)),	                     # bottom-left
                    ((w - int(dW * 1.2), h // 2), (w- int(dW * 0.2), h)),	                 # bottom-right
                    ((0, h - int(dH*1.0)), (w, h-int(dH*0.0)))                        # bottom
                ]
                on = [0] * len(segments)
                
                # loop over the segments
                for (i, ((xA, yA), (xB, yB))) in enumerate(segments):
                    if DEBUG_DIR:
                        acolor_roi = cv2.rectangle(color_roi.copy(), (xA, yA), (xB, yB), (0, 0, 255), 2)
                        save_debug_img(acolor_roi, img_basepath, f"07-{reference_category}-{cnt_counter}-digit-d{d}-{i}.png")
                    # extract the segment ROI, count the total number of
                    # thresholded pixels in the segment, and then compute
                    # the area of the segment
                    segROI = roi[yA:yB, xA:xB]
                    total = cv2.countNonZero(segROI)
                    area = (xB - xA) * (yB - yA)

                    # if the total number of non-zero pixels is greater than
                    # 50% of the area, mark the segment as "on"
                    eprint("flood", d, i, SEGMENT_NAMES[i], total / float(area))
                    if total / float(area) > MIN_FLOOD_PERCENTAGE:
                        on[i]= 1

                if w < digit_one_upper_length: # this is super thin, probably digit 1. the horizontal ones dont make a sense here
                    on[0] = 0 # top
                    on[3] = 0 # center
                    on[6] = 0 # bottom
                    on[2] = 1 if on[1] or on[2] else 0
                    on[5] = 1 if on[4] or on[5] else 0
                    on[1] = 0
                    on[4] = 0

                # lookup the digit and draw it on the image
                digit = DIGITS_LOOKUP.get(tuple(on))
                eprint("digits slices", on, digit)
                if digit is None:
                    # the bottom of the display may have some noise, trying to workaround it
                    (xA, yA), (xB, yB) = ((0, h - int(dH*1.3)), (w, h-int(dH*0.3)))
                    segROI = roi[yA:yB, xA:xB]
                    total = cv2.countNonZero(segROI)
                    area = (xB - xA) * (yB - yA)

                    # if the total number of non-zero pixels is greater than
                    # 50% of the area, mark the segment as "on"
                    eprint("retried flood", d, i, SEGMENT_NAMES[i], total / float(area))
                    if total / float(area) > MIN_FLOOD_PERCENTAGE:
                        on[i]= 1
                    digit = DIGITS_LOOKUP.get(tuple(on))
                    if not digit:
                        failure = True
                        break
                result += str(digit)
            if failure:
                continue
            return int(result)


def do_the_job(*imgs):
    re = []
    for img in imgs:
        eprint("-----------", img)
        re.append(process_img(img))
    return re
    
if __name__ == "__main__":
    x = do_the_job(*sys.argv[1:])
    print(json.dumps(x))
