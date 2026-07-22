import numpy as np
import mediapipe as mp

mp_hands = mp.solutions.hands

def calculate_angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    if angle > 180.0:
        angle = 360.0 - angle
    return angle

import numpy as np
import mediapipe as mp

mp_hands = mp.solutions.hands

def calculate_angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    if angle > 180.0:
        angle = 360.0 - angle
    return angle

def recognize_gesture(hand_landmarks):
    lm = hand_landmarks.landmark
    threshold = 0.02
    
    index_is_up = (lm[mp_hands.HandLandmark.INDEX_FINGER_TIP].y + threshold) < lm[mp_hands.HandLandmark.INDEX_FINGER_PIP].y
    middle_is_up = (lm[mp_hands.HandLandmark.MIDDLE_FINGER_TIP].y + threshold) < lm[mp_hands.HandLandmark.MIDDLE_FINGER_PIP].y
    ring_is_up = (lm[mp_hands.HandLandmark.RING_FINGER_TIP].y + threshold) < lm[mp_hands.HandLandmark.RING_FINGER_PIP].y
    pinky_is_up = (lm[mp_hands.HandLandmark.PINKY_TIP].y + threshold) < lm[mp_hands.HandLandmark.PINKY_PIP].y
    
    # 1. 伸出 1 个手指表示开始
    if index_is_up and not middle_is_up and not ring_is_up and not pinky_is_up:
        return "START"
        
    # 2. 伸出 2 个手指表示暂停
    if index_is_up and middle_is_up and not ring_is_up and not pinky_is_up:
        return "STOP"
    
    return None