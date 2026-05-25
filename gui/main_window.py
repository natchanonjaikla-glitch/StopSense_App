import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading

from core.video_processor import VideoProcessor

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("StopSense - Realtime TTC & Speed Analyzer")
        self.root.geometry("850x850")
        self.root.configure(bg="#f5f6fa")
        
        self.video_path = ""
        self.model_path = ""
        self.calibration_path = ""
        self.output_base_dir = os.path.abspath("output") 
        self.processor = None
        self.class_vars = {}

        # พารามิเตอร์ของระบบ
        self.var_ttc = tk.DoubleVar(value=1.5)
        self.var_gap = tk.DoubleVar(value=3.0) 
        self.var_speed_comp = tk.DoubleVar(value=0.0)
        
        # ตัวแปรสำหรับปรับลูกศร
        self.var_arrow_min = tk.IntVar(value=40)
        self.var_arrow_mult = tk.DoubleVar(value=3.0)

        self._create_widgets()

    def _create_widgets(self):
        header = tk.Frame(self.root, bg="#2c3e50", height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="StopSense - Realtime TTC Analyzer", font=("Helvetica", 16, "bold"), fg="white", bg="#2c3e50").pack(pady=22)

        main_container = tk.Frame(self.root, bg="#f5f6fa", padx=20, pady=10)
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. เลือกไฟล์ข้อมูล
        file_lf = tk.LabelFrame(main_container, text=" 1. เลือกไฟล์และที่อยู่จัดเก็บข้อมูล ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=15, pady=10)
        file_lf.pack(fill=tk.X, pady=5)
        
        tk.Button(file_lf, text="เลือกวิดีโอ", command=self.select_video, width=15).grid(row=0, column=0, pady=4)
        self.lbl_video = tk.Label(file_lf, text="ยังไม่ได้เลือก...", bg="#f5f6fa")
        self.lbl_video.grid(row=0, column=1, padx=10, sticky="w")
        
        tk.Button(file_lf, text="เลือกโมเดล", command=self.select_model, width=15).grid(row=1, column=0, pady=4)
        self.lbl_model = tk.Label(file_lf, text="ยังไม่ได้เลือก...", bg="#f5f6fa")
        self.lbl_model.grid(row=1, column=1, padx=10, sticky="w")
        
        tk.Button(file_lf, text="เลือกไฟล์พิกัด Zone", command=self.select_calibration, width=15).grid(row=2, column=0, pady=4)
        self.lbl_calib = tk.Label(file_lf, text="ยังไม่ได้เลือก...", bg="#f5f6fa")
        self.lbl_calib.grid(row=2, column=1, padx=10, sticky="w")

        tk.Button(file_lf, text="โฟลเดอร์บันทึกผล", command=self.select_output_dir, width=15).grid(row=3, column=0, pady=4)
        self.lbl_output = tk.Label(file_lf, text=self.output_base_dir, bg="#f5f6fa", fg="#2980b9", font=("Helvetica", 9, "bold"))
        self.lbl_output.grid(row=3, column=1, padx=10, sticky="w")

        # 2. ตั้งค่าพารามิเตอร์
        param_lf = tk.LabelFrame(main_container, text=" 2. ตั้งค่าพารามิเตอร์จราจรและภาพ ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=15, pady=10)
        param_lf.pack(fill=tk.X, pady=5)
        
        tk.Label(param_lf, text="TTC Threshold (วิ):", bg="#f5f6fa", width=20, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Entry(param_lf, textvariable=self.var_ttc, width=10).grid(row=0, column=1, padx=5, pady=2, sticky="w")
        
        tk.Label(param_lf, text="PET (วิ) - ความห่าง:", bg="#f5f6fa", width=20, anchor="w").grid(row=1, column=0, sticky="w")
        tk.Entry(param_lf, textvariable=self.var_gap, width=10).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        tk.Label(param_lf, text="ชดเชยความเร็ว (+/-):", bg="#f5f6fa", width=20, anchor="w").grid(row=2, column=0, sticky="w")
        tk.Entry(param_lf, textvariable=self.var_speed_comp, width=10).grid(row=2, column=1, padx=5, pady=2, sticky="w")
        
        tk.Label(param_lf, text="ความยาวลูกศร (ขั้นต่ำ/คูณ):", bg="#f5f6fa", width=20, anchor="w").grid(row=3, column=0, sticky="w")
        arr_frame = tk.Frame(param_lf, bg="#f5f6fa")
        arr_frame.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        tk.Entry(arr_frame, textvariable=self.var_arrow_min, width=5).pack(side=tk.LEFT)
        tk.Label(arr_frame, text="px,  x", bg="#f5f6fa").pack(side=tk.LEFT, padx=2)
        tk.Entry(arr_frame, textvariable=self.var_arrow_mult, width=5).pack(side=tk.LEFT)

        # 3. คลาสวัตถุ
        self.class_lf = tk.LabelFrame(main_container, text=" 3. วัตถุที่ต้องการตรวจจับ ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", height=180) 
        self.class_lf.pack(fill=tk.X, pady=5)
        self.class_lf.pack_propagate(False)
        
        self.class_btn_frame = tk.Frame(self.class_lf, bg="#f5f6fa")
        self.class_btn_frame.pack(fill=tk.X, pady=(0, 5))
        self.btn_select_all = tk.Button(self.class_btn_frame, text="☑ เลือกทั้งหมด", command=self.select_all_classes, bg="#dcdde1", font=("Helvetica", 9))
        self.btn_select_all.pack(side=tk.LEFT, padx=(5, 5))
        self.btn_deselect_all = tk.Button(self.class_btn_frame, text="☐ เอาออกทั้งหมด", command=self.deselect_all_classes, bg="#dcdde1", font=("Helvetica", 9))
        self.btn_deselect_all.pack(side=tk.LEFT)

        self.canvas = tk.Canvas(self.class_lf, bg="#f5f6fa", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.class_lf, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.checkbox_frame = tk.Frame(self.canvas, bg="#f5f6fa")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.checkbox_frame, anchor="nw")
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.checkbox_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel) 

        # Control Panel
        cp = tk.Frame(main_container, bg="#f5f6fa")
        cp.pack(fill=tk.X, pady=15)
        
        self.btn_start = tk.Button(cp, text="▶ เริ่มวิเคราะห์ Real-time", command=self.start_analysis, bg="#27ae60", fg="white", font=("Helvetica", 12, "bold"), width=20)
        self.btn_start.pack(side=tk.LEFT, padx=10)
        
        self.btn_stop = tk.Button(cp, text="⏹ หยุดรัน", command=self.stop_analysis, bg="#c0392b", fg="white", font=("Helvetica", 12, "bold"), width=10, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        tk.Button(cp, text="📊 Dashboard", command=self.open_dashboard, bg="#f39c12", fg="white", font=("Helvetica", 11, "bold"), width=12).pack(side=tk.RIGHT, padx=5)
        tk.Button(cp, text="📁 โฟลเดอร์ผลลัพธ์", command=self.open_output_folder, bg="#2980b9", fg="white", font=("Helvetica", 11, "bold"), width=15).pack(side=tk.RIGHT, padx=5)

        self.status_var = tk.StringVar(value="สถานะ: พร้อมใช้งาน")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bg="#dcdde1", anchor="w", padx=10, pady=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def select_all_classes(self):
        for var in self.class_vars.values(): 
            var.set(True)

    def deselect_all_classes(self):
        for var in self.class_vars.values(): 
            var.set(False)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # === อัปเดตฟังก์ชันเรียก Dashboard ให้ดึงโค้ดมารันเป็นหน้าต่างย่อย ===
    def open_dashboard(self):
        try:
            # สมมติว่าในไฟล์ gui/viewer.py ของคุณ คลาสหลักชื่อว่า DashboardWindow หรือคล้ายกัน
            # หากชื่อคลาสต่างไปจากนี้ ให้เปลี่ยนชื่อ "DashboardWindow" เป็นชื่อคลาสจริงของคุณครับ
            from gui.viewer import DashboardWindow 
            
            # สร้างหน้าต่างใหม่ที่เชื่อมโยงกับโปรแกรมหลัก
            dash_win = tk.Toplevel(self.root)
            app = DashboardWindow(dash_win)
            
        except ImportError:
            messagebox.showerror("Error", "ไม่พบคลาส DashboardWindow ในไฟล์ gui/viewer.py\nกรุณาตรวจสอบชื่อคลาสในไฟล์ viewer.py ครับ")
        except Exception as e:
            messagebox.showerror("Error", f"เกิดข้อผิดพลาดในการเปิด Dashboard: {e}")
    # ==============================================================

    def open_output_folder(self):
        if os.path.exists(self.output_base_dir):
            os.startfile(self.output_base_dir)
        else:
            messagebox.showinfo("แจ้งเตือน", "ยังไม่มีโฟลเดอร์ผลลัพธ์ครับ")

    def select_video(self):
        path = filedialog.askopenfilename()
        if path:
            self.video_path = path
            self.lbl_video.config(text=os.path.basename(path))

    def select_model(self):
        path = filedialog.askopenfilename(filetypes=[('YOLO Model', '*.pt')])
        if path:
            self.model_path = path
            self.lbl_model.config(text=os.path.basename(path))
            self.load_classes()

    def select_calibration(self):
        path = filedialog.askopenfilename(filetypes=[('Text Files', '*.txt')])
        if path:
            self.calibration_path = path
            self.lbl_calib.config(text=os.path.basename(path))

    def select_output_dir(self):
        path = filedialog.askdirectory()
        if path: 
            self.output_base_dir = path
            self.lbl_output.config(text=path)

    def load_classes(self):
        try:
            from ultralytics import YOLO
            model = YOLO(self.model_path)
            for widget in self.checkbox_frame.winfo_children(): 
                widget.destroy()
            self.class_vars = {}
            r, c = 0, 0
            for cid, name in model.names.items():
                var = tk.BooleanVar(value=True)
                self.class_vars[cid] = var
                tk.Checkbutton(self.checkbox_frame, text=name, variable=var, bg="#f5f6fa").grid(row=r, column=c, sticky="w", padx=5)
                c += 1
                if c > 3: 
                    c = 0; r += 1
        except Exception as e:
            messagebox.showerror("Error", f"โหลดโมเดลไม่สำเร็จ: {e}")

    def start_analysis(self):
        if not all([self.video_path, self.model_path, self.calibration_path]):
            messagebox.showwarning("ข้อมูลไม่ครบ", "กรุณาเลือกไฟล์วิดีโอ, โมเดล และไฟล์พิกัด Zone ให้ครบถ้วน")
            return
        
        selected = [cid for cid, v in self.class_vars.items() if v.get()]
        if not selected:
            messagebox.showwarning("เตือน", "กรุณาเลือกวัตถุที่ต้องการตรวจจับอย่างน้อย 1 อย่างครับ")
            return

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_var.set("สถานะ: กำลังประมวลผลระบบ Real-time...")
        
        try:
            self.processor = VideoProcessor(
                video_path=self.video_path, 
                model_path=self.model_path, 
                calibration_path=self.calibration_path,
                target_classes=selected, 
                ttc_threshold=self.var_ttc.get(), 
                arrival_gap=self.var_gap.get(),
                speed_comp=self.var_speed_comp.get(), 
                output_dir=self.output_base_dir,
                arrow_min_len=self.var_arrow_min.get(),
                arrow_speed_mult=self.var_arrow_mult.get()
            )
            self.processor.start()
            
            def check_alive():
                if self.processor and self.processor.thread.is_alive():
                    self.root.after(500, check_alive)
                else:
                    self.btn_start.config(state=tk.NORMAL)
                    self.btn_stop.config(state=tk.DISABLED)
                    self.status_var.set("สถานะ: ประมวลผลเสร็จสิ้น (หรือถูกหยุด)")
            
            self.root.after(500, check_alive)
        except Exception as e:
            messagebox.showerror("Error", f"เกิดข้อผิดพลาดในการเริ่มวิเคราะห์:\n{e}")
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)

    def stop_analysis(self):
        if self.processor:
            self.processor.stop()
            self.status_var.set("สถานะ: กำลังหยุดการทำงาน...")