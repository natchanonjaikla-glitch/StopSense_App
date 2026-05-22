import sys
import os
import tkinter as tk

# ตั้งค่า Path เพื่อให้ Python มองเห็นโฟลเดอร์ gui, core, utils
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Import หน้าต่างหลักจากโฟลเดอร์ gui
from gui.main_window import MainWindow

def main():
    # สร้างหน้าต่าง GUI หลัก
    root = tk.Tk()
    
    # ตั้งค่าหัวข้อและขนาดหน้าต่างเบื้องต้น
    root.title("StopSense - Traffic Risk Detection")
    root.geometry("800x600")
    
    # โหลดคลาส MainWindow มาใส่ในหน้าต่างนี้
    app = MainWindow(root)
    
    # สั่งให้โปรแกรมรันวนลูป (เปิดหน้าต่างค้างไว้)
    root.mainloop()

if __name__ == "__main__":
    main()