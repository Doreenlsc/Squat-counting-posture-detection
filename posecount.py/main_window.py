import time
import re
import hashlib
import cv2
import threading
import pyttsx3
from PySide6.QtCore import Slot, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, 
    QPushButton, QMessageBox, QTableWidget, QTableWidgetItem, QSpinBox
)
from database import load_data, save_data
from video_thread import VideoThread

class MainWindow(QMainWindow):
    """运动监测与历史记录主界面"""
    def __init__(self, username, app_manager=None):
        super().__init__()
        self.username = username
        self.app_manager = app_manager
        self.setWindowTitle(f"AI 深蹲系统 - 用户: {username}")
        self.resize(1050, 750)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2f; }
            QLabel { color: #ffffff; font-family: "Microsoft YaHei", Arial; }
            QPushButton { background-color: #4e54c8; color: white; border-radius: 6px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #6c63ff; }
            QSpinBox { background-color: #2d2d44; color: #ffffff; border: 1px solid #555577; border-radius: 4px; padding: 3px; }
            QTableWidget { background-color: #252538; color: #ffffff; gridline-color: #3b3b58; border: 1px solid #444466; }
            QHeaderView::section { background-color: #2f2f4f; color: #00ffcc; font-weight: bold; border: none; padding: 4px; }
        """)
        
        self.active_duration = 0  
        self.final_total_count = 0
        self.is_thread_active = False 
        self.is_workout_finished = False 
        
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 180)
        except Exception:
            self.tts_engine = None
            
        self.last_spoken_text = ""
        self.last_speak_time = 0
        
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        
        self.video_label = QLabel("正在初始化摄像头与人脸识别...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #0f0f1a; color: #00ffcc; border-radius: 10px; border: 2px solid #3b3b58;")
        self.video_label.setFixedSize(640, 480)
        main_layout.addWidget(self.video_label)
        
        control_layout = QVBoxLayout()
        self.title_label = QLabel(f"欢迎运动达人: {username}")
        self.title_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.title_label.setStyleSheet("color: #00ffcc;")
        
        settings_layout = QHBoxLayout()
        self.sets_spin = QSpinBox()
        self.sets_spin.setRange(1, 10)
        self.sets_spin.setValue(3)
        
        self.per_set_spin = QSpinBox()
        self.per_set_spin.setRange(1, 50)
        self.per_set_spin.setValue(10)
        
        self.rest_spin = QSpinBox()
        self.rest_spin.setRange(5, 60)
        self.rest_spin.setValue(15)
        
        settings_layout.addWidget(QLabel("组数:"))
        settings_layout.addWidget(self.sets_spin)
        settings_layout.addWidget(QLabel("每组:"))
        settings_layout.addWidget(self.per_set_spin)
        settings_layout.addWidget(QLabel("休息(秒):"))
        settings_layout.addWidget(self.rest_spin)
        
        apply_btn = QPushButton("应用设置并重置")
        apply_btn.setStyleSheet("background-color: #00b894; color: white;")
        apply_btn.clicked.connect(self.apply_settings)
        
        self.timer_label = QLabel("有效运动时间: 00:00")
        self.timer_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.timer_label.setStyleSheet("color: #00cec9;")
        
        self.set_status_label = QLabel("当前组: 第 0 组 / 共 3 组")
        self.set_status_label.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.set_status_label.setStyleSheet("color: #fdcb6e;")
        
        self.count_label = QLabel("10")
        self.count_label.setFont(QFont("Microsoft YaHei", 32, QFont.Bold))
        self.count_label.setStyleSheet("color: #55efc4; background-color: #2d2d44; border-radius: 8px; qproperty-alignment: AlignCenter;")
        
        self.status_label = QLabel("人脸识别中...")
        self.status_label.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.status_label.setStyleSheet("color: #fab1a0;")
        
        self.feedback_label = QLabel("请正对镜头，完成人脸认证并点击开始运动")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setMinimumHeight(70)
        self.feedback_label.setAlignment(Qt.AlignCenter)
        self.feedback_label.setStyleSheet("""
            background-color: #d35400; color: #ffffff; padding: 12px; border-radius: 8px; 
            font-weight: bold; font-size: 18px; border: 2px solid #f39c12;
        """)
        
        self.finish_btn = QPushButton("开始运动")
        self.finish_btn.setStyleSheet("background-color: #00b894; color: white; font-size: 13px; font-weight: bold;")
        self.finish_btn.clicked.connect(self.finish_workout)
        
        self.logout_btn = QPushButton("退出登录")
        self.logout_btn.setStyleSheet("background-color: #636e72; color: white;")
        self.logout_btn.clicked.connect(self.handle_logout)
        
        self.history_table = QTableWidget(0, 2)
        self.history_table.setHorizontalHeaderLabels(["运动时长", "总深蹲个数"])
        self.load_user_history()
        
        control_layout.addWidget(self.title_label)
        control_layout.addLayout(settings_layout)
        control_layout.addWidget(apply_btn)
        control_layout.addWidget(self.timer_label)
        control_layout.addWidget(self.set_status_label)
        control_layout.addWidget(QLabel("当前组剩余目标个数:"))
        control_layout.addWidget(self.count_label)
        control_layout.addWidget(QLabel("当前系统状态:"))
        control_layout.addWidget(self.status_label)
        control_layout.addWidget(QLabel("实时提示 / 夸奖通知:"))
        control_layout.addWidget(self.feedback_label)
        control_layout.addWidget(self.finish_btn)
        control_layout.addWidget(self.logout_btn)
        control_layout.addWidget(QLabel("历史运动记录:"))
        control_layout.addWidget(self.history_table)
        
        main_layout.addLayout(control_layout)
        self.setCentralWidget(central_widget)
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_timer_display)
        self.clock_timer.start(1000)
        
        self.thread = VideoThread(username, total_sets=3, target_per_set=10, rest_time=15)
        self.thread.frame_signal.connect(self.update_image)
        self.thread.data_signal.connect(self.update_data)
        self.thread.face_verified_signal.connect(self.on_face_verified)
        self.thread.start()

    def speak_text(self, text):
        """优化后的语音播报：支持状态切换立即播报，且对关键重复提示设定合理的冷却时间"""
        if not self.tts_engine:
            return
        
        current_time = time.time()
        clean_text = text.replace("⚠️", "").replace("☕", "").replace("🔥", "").replace("🎉", "").replace("⏸️", "").replace("✅", "").strip()
        
        if not clean_text:
            return

        # 判断是否为需要周期性重复提醒的关键状态
        is_critical_reminder = any(keyword in clean_text for keyword in [
            "全身", "手势", "正对", "侧身", "休息", "长时间未动", "请点击"
        ])

        # 确定冷却时间：普通提示/状态切换 2 秒，重要未入镜/手势提示 4.5 秒，避免频繁打断但又不会漏掉
        cooldown_threshold = 4.5 if is_critical_reminder else 2.0

        # 触发播报条件：1. 文本内容变了（状态切换） 2. 或者是关键提示且超过了冷却时间
        if clean_text != self.last_spoken_text or (current_time - self.last_speak_time > cooldown_threshold):
            self.last_spoken_text = clean_text
            self.last_speak_time = current_time
            
            def _play():
                try:
                    # 每次独立初始化一个 engine 实例以防底层队列死锁或文本叠音截断
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 180)
                    engine.say(clean_text)
                    engine.runAndWait()
                except Exception:
                    pass
            
            # 启动独立线程播报，确保不卡主界面 UI 线程
            threading.Thread(target=_play, daemon=True).start()

    def apply_settings(self):
        total_sets = self.sets_spin.value()
        per_set = self.per_set_spin.value()
        rest_time = self.rest_spin.value()
        
        if hasattr(self, 'thread') and self.thread is not None:
            self.thread.total_sets = total_sets
            self.thread.target_per_set = per_set
            self.thread.rest_time_setting = rest_time
            self.thread.reset_sets_config()
            self.active_duration = 0
            self.is_workout_finished = False
            self.finish_btn.setText("开始运动")
            self.finish_btn.setStyleSheet("background-color: #00b894; color: white;")
            QMessageBox.information(self, "设置成功", f"参数已更新：共 {total_sets} 组，每组 {per_set} 个，休息 {rest_time} 秒。")

    def update_timer_display(self):
        if self.is_thread_active and not self.is_workout_finished:
            self.active_duration += 1
            
        mins = self.active_duration // 60
        secs = self.active_duration % 60
        self.timer_label.setText(f"有效运动时间: {mins:02d}:{secs:02d}")

    def load_user_history(self):
        db = load_data()
        history = db.get(self.username, {}).get("history", [])
        total_count = len(history)
        reversed_history = history[::-1] 
        
        self.history_table.setRowCount(total_count)
        self.history_table.setVerticalHeaderLabels([str(i + 1) for i in range(total_count)])
        
        for row, item in enumerate(reversed_history):
            self.history_table.setItem(row, 0, QTableWidgetItem(str(item.get("duration"))))
            self.history_table.setItem(row, 1, QTableWidgetItem(str(item.get("count"))))

    @Slot(QImage)
    def update_image(self, image):
        self.video_label.setPixmap(QPixmap.fromImage(image))

    @Slot(str)
    def on_face_verified(self, name):
        self.status_label.setText("人脸验证成功！请点击开始运动并比出手势")
        self.speak_text("人脸识别通过")

    @Slot(int, int, int, str, str, bool, bool)
    def update_data(self, current_set, remaining_count, total_accumulated, stage, feedback, is_resting, is_active):
        self.final_total_count = total_accumulated
        self.is_thread_active = is_active
        
        display_set = current_set if current_set <= self.sets_spin.value() else self.sets_spin.value()
        if current_set == 0:
            display_set = 0
            
        self.count_label.setText(str(remaining_count))
        self.set_status_label.setText(f"当前组: 第 {display_set} 组 / 共 {self.sets_spin.value()} 组")
        
        if is_resting:
            self.status_label.setText("组间休息中 ☕")
            self.status_label.setStyleSheet("color: #fdcb6e; font-weight: bold;")
        else:
            self.status_label.setText(stage)
            self.status_label.setStyleSheet("color: #55efc4; font-weight: bold;")
            
        self.feedback_label.setText(feedback)
        
        # 触发语音播报
        self.speak_text(feedback)
        
        target_total_count = self.sets_spin.value() * self.per_set_spin.value()
        if ("完成所有训练" in feedback or self.final_total_count >= target_total_count) and not self.is_workout_finished:
            self.is_workout_finished = True
            self.finish_btn.setText("重新开始运动")
            self.finish_btn.setStyleSheet("background-color: #00b894; color: white;")
            if not getattr(self, '_finished_dialog_shown', False):
                self._finished_dialog_shown = True
                QMessageBox.information(self, "恭喜", feedback)

    def finish_workout(self):
        btn_text = self.finish_btn.text()
        
        if btn_text == "开始运动":
            self.finish_btn.setText("结束并保存本次运动")
            self.finish_btn.setStyleSheet("background-color: #d63031; color: white;")
            if hasattr(self, 'thread') and self.thread is not None:
                self.thread.started_by_user = True  
            self.speak_text("已开始运动")
            return

        if btn_text == "重新开始运动":
            self.finish_btn.setText("结束并保存本次运动")
            self.finish_btn.setStyleSheet("background-color: #d63031; color: white;")
            if hasattr(self, 'thread') and self.thread is not None:
                self.thread.reset_sets_config()
                self.thread.started_by_user = True
            self.active_duration = 0
            self.is_workout_finished = False
            self._finished_dialog_shown = False
            self.speak_text("已重新开始运动")
            return

        minutes = self.active_duration // 60
        seconds = self.active_duration % 60
        duration_str = f"{minutes}分{seconds}秒"
        
        if hasattr(self, 'thread') and self.thread is not None:
            self.final_total_count = self.thread.total_accumulated_count
        
        if self.final_total_count > 0 or self.active_duration > 0: 
            db = load_data()
            if self.username in db:
                db[self.username]["history"].append({
                    "duration": duration_str if duration_str != "0分0秒" else "1分0秒",
                    "count": self.final_total_count
                })
                save_data(db)
            self.load_user_history()
            QMessageBox.information(self, "运动结束", f"本次运动已成功保存！\n有效时长: {duration_str}\n总深蹲个数: {self.final_total_count}")
        else:
            QMessageBox.warning(self, "提示", "未检测到有效深蹲计数，未保存记录。")
            
        self.finish_btn.setText("重新开始运动")
        self.finish_btn.setStyleSheet("background-color: #00b894; color: white;")
        self.active_duration = 0
        self._finished_dialog_shown = False
        self.is_workout_finished = True

        if hasattr(self, 'thread') and self.thread is not None:
            self.thread.current_set = 0
            self.thread.remaining_count = self.thread.target_per_set
            self.thread.is_paused = False
            self.thread.started_by_user = False

    def handle_logout(self):
        if hasattr(self, 'thread') and self.thread is not None:
            self.thread.stop()
            self.thread = None
        if self.clock_timer.isActive():
            self.clock_timer.stop()
        if self.app_manager:
            self.app_manager.show_auth_window()

    def closeEvent(self, event):
        if hasattr(self, 'thread') and self.thread is not None:
            self.thread.stop()
            self.thread = None
        if self.clock_timer.isActive():
            self.clock_timer.stop()
        event.accept()
        QApplication.quit()