import sys
from  PySide6.QtWidgets  import QApplication
from  app_manager  import AppManager


if __name__ == "__main__":
    app = QApplication(sys.argv)
    manager = AppManager()
    manager.show()
    sys.exit(app.exec())