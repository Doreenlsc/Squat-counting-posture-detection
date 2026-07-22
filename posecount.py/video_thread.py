import cv2
import time
import numpy as np
import mediapipe as mp
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage
import utils
from database import load_data

mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

class VideoThread(QThread):
    """深蹲、人脸识别、多组降序计数与休息倒计时的工作线程"""
    frame_signal = Signal(QImage)
    data_signal = Signal(int, int, int, str, str, bool, bool) 
    face_verified_signal = Signal(str) 

    def __init__(self, target_username="", total_sets=3, target_per_set=10, rest_time=15):
        super().__init__()
        self.running = True
        self.is_paused = False  
        self.target_username = target_username
        self.total_sets = total_sets
        self.target_per_set = target_per_set
        self.rest_time_setting = rest_time
        
        self.current_set = 0  
        self.remaining_count = target_per_set
        self.total_accumulated_count = 0
        
        self.is_resting = False
        self.current_rest_countdown = 0
        self._rest_timer_counter = 0

        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.face_recognized = False
        
        self.started_by_user = False
        self.last_emitted_feedback = ""

    def reset_sets_config(self):
        self.current_set = 0  
        self.remaining_count = self.target_per_set
        self.total_accumulated_count = 0
        self.is_resting = False
        self.current_rest_countdown = 0
        self.is_paused = False
        self.started_by_user = False
        self.last_emitted_feedback = ""

    def run(self):
        cap = cv2.VideoCapture(0)
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        hands = mp_hands.Hands(min_detection_confidence=0.5, min_tracking_confidence=0.5, max_num_hands=1)
        
        stage = "up"
        is_active = False
        hip_y_standing = None
        guest_cooldown = 0
        
        last_detected_gesture = None
        gesture_frame_count = 0
        required_frames = 10  
        
        no_action_counter = 0     
        rest_overtime_counter = 0  
        
        db = load_data()
        user_face_hist = db.get(self.target_username, {}).get("face_hist", None)
        if user_face_hist:
            user_face_hist = np.array(user_face_hist, dtype=np.float32)
        
        verify_frames_count = 0 
        
        while self.running:
            res, frame = cap.read()
            if not res:
                self.msleep(10)
                continue
                
            frame = cv2.flip(frame, 1)
            h, w, c = frame.shape

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(50, 50))
            
            # 严格的人脸识别比对逻辑：必须有注册特征，且直方图相似度达标才算通过
            if not self.face_recognized and user_face_hist is not None and len(faces) > 0:
                (x, y, fw, fh) = max(faces, key=lambda f: f[2] * f[3])
                cv2.rectangle(frame, (x, y), (x+fw, y+fh), (0, 255, 0), 2)
                
                face_roi = gray[y:y+fh, x:x+fw]
                current_hist = cv2.calcHist([face_roi], [0], None, [64], [0, 256])
                cv2.normalize(current_hist, current_hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
                
                similarity = cv2.compareHist(user_face_hist, current_hist, cv2.HISTCMP_CORREL)
                
                if similarity > 0.65: 
                    verify_frames_count += 1
                    if verify_frames_count >= 5: 
                        self.face_recognized = True
                        self.face_verified_signal.emit(self.target_username)
                else:
                    verify_frames_count = max(0, verify_frames_count - 1)
            elif not self.face_recognized and len(faces) > 0:
                (x, y, fw, fh) = faces[0]
                cv2.rectangle(frame, (x, y), (x+fw, y+fh), (0, 0, 255), 2)

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = pose.process(image)
            hands_results = hands.process(image)
            image.flags.writeable = True
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            
            is_full_body_visible = False
            is_side_pose = False
            pose_mode = "none" 
            
            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                right_indices = [mp_pose.PoseLandmark.RIGHT_SHOULDER.value, mp_pose.PoseLandmark.RIGHT_HIP.value, mp_pose.PoseLandmark.RIGHT_KNEE.value, mp_pose.PoseLandmark.RIGHT_ANKLE.value]
                left_indices = [mp_pose.PoseLandmark.LEFT_SHOULDER.value, mp_pose.PoseLandmark.LEFT_HIP.value, mp_pose.PoseLandmark.LEFT_KNEE.value, mp_pose.PoseLandmark.LEFT_ANKLE.value]
                
                right_visible = all(landmarks[idx].visibility > 0.4 for idx in right_indices)
                left_visible = all(landmarks[idx].visibility > 0.4 for idx in left_indices)
                
                if right_visible or left_visible:
                    is_full_body_visible = True
                    is_side_pose = True  
                    if right_visible and not left_visible:
                        pose_mode = "right_side"
                    elif left_visible and not right_visible:
                        pose_mode = "left_side"
                    else:
                        pose_mode = "right_side"

            if guest_cooldown > 0:
                guest_cooldown -= 1
                
            gesture_detected_in_this_frame = False
            if self.started_by_user and self.face_recognized and hands_results.multi_hand_landmarks:
                for hand_landmarks in hands_results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                    if guest_cooldown == 0:
                        detected_gesture = utils.recognize_gesture(hand_landmarks)
                        if detected_gesture is not None:
                            gesture_detected_in_this_frame = True
                            if detected_gesture == last_detected_gesture:
                                gesture_frame_count += 1
                            else:
                                last_detected_gesture = detected_gesture
                                gesture_frame_count = 1
                                
                            if gesture_frame_count >= required_frames:
                                if detected_gesture == "START":
                                    no_action_counter = 0 
                                    rest_overtime_counter = 0
                                    if self.is_paused:
                                        if is_full_body_visible:
                                            self.is_paused = False
                                            is_active = True
                                            if self.current_set == 0:
                                                self.current_set = 1
                                            feedback = "已通过手势恢复计数"
                                            guest_cooldown = 30
                                        else:
                                            feedback = "恢复失败，未检测到全身入镜"
                                            guest_cooldown = 15
                                    else:
                                        if self.is_resting:
                                            self.is_resting = False
                                        is_active = True
                                        if self.current_set == 0:
                                            self.current_set = 1
                                        feedback = "已开始计数"
                                        guest_cooldown = 30
                                        
                                elif detected_gesture == "STOP":
                                    self.is_paused = True
                                    is_active = False
                                    feedback = "系统已暂停"
                                    guest_cooldown = 30
                                    
                                gesture_frame_count = 0
                                last_detected_gesture = None

            if not gesture_detected_in_this_frame:
                gesture_frame_count = max(0, gesture_frame_count - 1)
                if gesture_frame_count == 0:
                    last_detected_gesture = None

            # 核心状态与语音提示分发
            if not self.started_by_user:
                feedback = "请点击开始运动按钮以启动系统"
                is_active = False
            elif self.is_paused:
                if not is_full_body_visible:
                    feedback = "系统已暂停，未检测到全身入镜"
                else:
                    feedback = "系统已暂停，全身已入镜，请伸出一个手指恢复运动"
                is_active = False
            else:
                if self.is_resting:
                    self._rest_timer_counter += 1
                    if self._rest_timer_counter >= 30:
                        self.current_rest_countdown -= 1
                        self._rest_timer_counter = 0
                        if self.current_rest_countdown <= 0:
                            self.is_resting = False
                            is_active = False 
                
                if not self.face_recognized:
                    feedback = "请正对摄像头，保持光线充足进行人脸识别"
                elif self.current_set > self.total_sets:
                    feedback = "恭喜你，完成所有训练"
                    is_active = False
                elif self.is_resting:
                    feedback = f"组间休息中，剩余 {self.current_rest_countdown} 秒"
                    is_active = False
                elif self.current_set == 0:
                    if is_full_body_visible:
                        feedback = "全身已入镜，请伸出一个手指开始计数"
                    else:
                        feedback = "人脸识别通过，请往后退，确保全身入镜"
                    is_active = False
                elif not is_full_body_visible:
                    feedback = "未检测到全身，请往后退，确保身体完整入镜"
                    is_active = False  
                elif not is_side_pose:
                    feedback = "请调整站立姿态，确保侧身入镜"
                    is_active = False
                elif not is_active:
                    feedback = "站立检测通过，请伸出一个手指开始计数"
                else:
                    feedback = "姿势标准，请继续"
                    no_action_counter += 1
                    if no_action_counter > 250: 
                        feedback = "检测到您长时间未动"

                # 纠错与计数逻辑
                if is_active and results.pose_landmarks and is_side_pose and self.current_set <= self.total_sets and not self.is_resting:
                    try:
                        landmarks = results.pose_landmarks.landmark
                        if pose_mode == "right_side":
                            r_hip = [landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].x * w, landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].y * h]
                            r_knee = [landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].x * w, landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].y * h]
                            r_ankle = [landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].x * w, landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].y * h]
                            r_shoulder = [landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x * w, landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y * h]
                            knee_angle = utils.calculate_angle(r_hip, r_knee, r_ankle)
                            current_hip_y = r_hip[1]
                            
                            if abs(r_shoulder[0] - r_hip[0]) > w * 0.15:
                                feedback = "上身前倾严重"
                            elif abs(r_knee[0] - r_ankle[0]) > w * 0.08:
                                feedback = "膝盖不要内扣"
                        else: 
                            l_hip = [landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].x * w, landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].y * h]
                            l_knee = [landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value].x * w, landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value].y * h]
                            l_ankle = [landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value].x * w, landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value].y * h]
                            l_shoulder = [landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x * w, landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y * h]
                            knee_angle = utils.calculate_angle(l_hip, l_knee, l_ankle)
                            current_hip_y = l_hip[1]
                            
                            if abs(l_shoulder[0] - l_hip[0]) > w * 0.15:
                                feedback = "上身前倾严重"
                            elif abs(l_knee[0] - l_ankle[0]) > w * 0.08:
                                feedback = "膝盖不要内扣"
                        
                        if knee_angle > 160:
                            stage = "up"
                            hip_y_standing = current_hip_y
                        elif knee_angle < 95 and stage == 'up':
                            if hip_y_standing is not None and (current_hip_y - hip_y_standing) > h * 0.05:
                                stage = "down"
                                self.remaining_count -= 1
                                self.total_accumulated_count += 1
                                no_action_counter = 0 
                                
                                if self.remaining_count <= 0:
                                    self.current_set += 1
                                    if self.current_set <= self.total_sets:
                                        self.is_resting = True
                                        self.current_rest_countdown = self.rest_time_setting
                                        self._rest_timer_counter = 0
                                        self.remaining_count = self.target_per_set
                                        is_active = False
                                        feedback = f"完成一组进入休息"
                                    else:
                                        is_active = False
                                        feedback = "恭喜你，完成所有训练"
                                
                        mp_drawing.draw_landmarks(image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                    except Exception as e:
                        pass

            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            qt_image = QImage(rgb_image.data, w, h, w * c, QImage.Format_RGB888)
            scaled_image = qt_image.scaled(640, 480, Qt.KeepAspectRatio)
            
            current_stage_display = "已暂停" if self.is_paused else (stage if is_active else "准备中")
            self.frame_signal.emit(scaled_image)
            self.data_signal.emit(self.current_set, self.remaining_count, self.total_accumulated_count, current_stage_display, feedback, self.is_resting, is_active)
            
        cap.release()
        pose.close()
        hands.close()

    def stop(self):
        self.running = False
        self.is_paused = False 
        if self.isRunning():
            self.quit()
            self.wait(1000)