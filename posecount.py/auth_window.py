import time
import re
import hashlib
import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QLineEdit, QMessageBox
)
from database import load_data, save_data


class AuthWindow(QWidget):
    """登录与注册界面"""
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowTitle("AI 运动系统 - 登录/注册")
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        self.title = QLabel("AI 智能深蹲计数系统")
        self.title.setFont(QFont("Arial", 16, QFont.Bold))
        self.title.setAlignment(Qt.AlignCenter)
        
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("请输入用户名 (支持中英文)")
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("请输入密码 (至少6位，含数字/字符)")
        self.pass_input.setEchoMode(QLineEdit.Password)
        
        self.login_btn = QPushButton("登录（含人脸识别校验）")
        self.register_btn = QPushButton("注册新账号（录入人脸）")
        
        layout.addWidget(self.title)
        layout.addWidget(self.user_input)
        layout.addWidget(self.pass_input)
        layout.addWidget(self.login_btn)
        layout.addWidget(self.register_btn)
        
        self.login_btn.clicked.connect(self.handle_login)
        self.register_btn.clicked.connect(self.handle_register)

    def hash_password(self, password):
        """使用 SHA-256 对密码进行哈希加盐加密"""
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def handle_login(self):
        username = self.user_input.text().strip()
        password = self.pass_input.text().strip()
        db = load_data()
        
        if username not in db:
            QMessageBox.warning(self, "错误", "用户不存在，请先注册！")
            return
            
        hashed_pass = self.hash_password(password)
        if db[username]["password"] != hashed_pass:
            QMessageBox.warning(self, "错误", "密码错误！")
            return
            
        if "face_hist" not in db[username]:
            QMessageBox.warning(self, "错误", "该账号未成功录入人脸，请重新注册！")
            return
            
        self.main_app.start_main_window(username)

    def handle_register(self):
        username = self.user_input.text().strip()
        password = self.pass_input.text().strip()
        
        if not username:
            QMessageBox.warning(self, "错误", "用户名不能为空！")
            return
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+$', username):
            QMessageBox.warning(self, "错误", "用户名仅支持中文、英文字母、数字和下划线！")
            return
            
        if len(password) < 6:
            QMessageBox.warning(self, "错误", "密码长度不能少于 6 位！")
            return
            
        db = load_data()
        if username in db:
            QMessageBox.warning(self, "错误", "该用户已存在！")
            return
            
        QMessageBox.information(self, "人脸录入", "请正对摄像头，确保面部清晰无遮挡，点击确定后开始采集！")
        
        cap = cv2.VideoCapture(0)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        face_hist_list = None
        start_time = time.time()
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(60, 60))
            
            if len(faces) > 0:
                (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(frame, "Capturing Face...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                face_roi = gray[y:y+h, x:x+w]
                hist = cv2.calcHist([face_roi], [0], None, [64], [0, 256])
                cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
                face_hist_list = hist.flatten().tolist()
                
                cv2.imshow("Face Registration", frame)
                cv2.waitKey(1000)
                break
            else:
                cv2.putText(frame, "No face detected!", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            cv2.imshow("Face Registration", frame)
            if cv2.waitKey(1) & 0xFF == ord('q') or (time.time() - start_time > 10):
                break
                
        cap.release()
        cv2.destroyAllWindows()
        
        if face_hist_list is None:
            QMessageBox.warning(self, "错误", "未检测到有效人脸，注册失败！")
            return
            
        db[username] = {
            "password": self.hash_password(password),  # 保存加密后的密码
            "face_hist": face_hist_list,
            "history": []
        }
        save_data(db)
        QMessageBox.information(self, "成功", "注册成功，人脸特征已绑定！现在可以登录了。")

    def closeEvent(self, event):
        QApplication.quit()
        event.accept()
