from PySide6.QtWidgets import (QStackedWidget)
from auth_window import AuthWindow
from main_window import MainWindow


class AppManager(QStackedWidget):
    """主程序堆栈管理器"""
    def __init__(self):
        super().__init__()
        self.auth_window = AuthWindow(self)
        self.addWidget(self.auth_window)
        self.resize(450, 350)

    def start_main_window(self, username):
        self.main_window = MainWindow(username, self) # 传入 self 以便主界面调用返回
        self.addWidget(self.main_window)
        self.setCurrentWidget(self.main_window)
        self.resize(950, 650)

    def show_auth_window(self):
        # 重新实例化登录窗口并切换回去，同时调整窗口大小
        self.auth_window = AuthWindow(self)
        self.addWidget(self.auth_window)
        self.setCurrentWidget(self.auth_window)
        self.resize(400, 300)
