import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os

from core.video_processor import VideoProcessor
from gui.viewer import ResultViewer 

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("StopSense - Traffic Collision Risk Detection System")
        self.root.geometry("900x850") # ขยายหน้าต่างแนวตั้งให้รองรับเมนูใหม่
        self.root.configure(bg="#f5f6fa")
        self.root.minsize(850, 750)
        
        self.video_path = ""
        self.model_path = ""
        self.calibration_path = ""
        self.processor = None
        self.class_vars = {} 

        # === ตัวแปรสำหรับตั้งค่าพารามิเตอร์ ===
        self.var_ttc = tk.DoubleVar(value=3.0)
        self.var_gap = tk.DoubleVar(value=1.5)
        self.var_lookahead = tk.DoubleVar(value=4.0)
        self.var_skip = tk.IntVar(value=1)
        self.var_speed_comp = tk.DoubleVar(value=0.0)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._create_widgets()

    def _create_widgets(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#2f3640", height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        lbl_title = tk.Label(header_frame, text="StopSense AI - ระบบวิเคราะห์ความเสี่ยงอุบัติเหตุจราจร", font=("Helvetica", 16, "bold"), fg="#f5f6fa", bg="#2f3640")
        lbl_title.pack(pady=22)

        main_container = tk.Frame(self.root, bg="#f5f6fa", padx=20, pady=5)
        main_container.pack(fill=tk.BOTH, expand=True)

        # === กรอบที่ 1: เลือกไฟล์ข้อมูล ===
        file_lf = tk.LabelFrame(main_container, text=" 1. เลือกไฟล์ข้อมูล ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=15, pady=5)
        file_lf.pack(fill=tk.X, pady=5)

        tk.Label(file_lf, text="ไฟล์วิดีโอ (Video):", font=("Helvetica", 10), bg="#f5f6fa").grid(row=0, column=0, sticky="w", pady=5)
        self.lbl_video = tk.Label(file_lf, text="ยังไม่ได้เลือกไฟล์...", font=("Helvetica", 9, "italic"), fg="#7f8c8d", bg="#f5f6fa", anchor="w", width=40)
        self.lbl_video.grid(row=0, column=1, padx=10, sticky="w")
        self.btn_select_video = tk.Button(file_lf, text="เลือกไฟล์", command=self.select_video, width=10, bg="#dcdde1")
        self.btn_select_video.grid(row=0, column=2, pady=3)

        tk.Label(file_lf, text="โมเดล AI (.pt):", font=("Helvetica", 10), bg="#f5f6fa").grid(row=1, column=0, sticky="w", pady=5)
        self.lbl_model = tk.Label(file_lf, text="ยังไม่ได้เลือกไฟล์...", font=("Helvetica", 9, "italic"), fg="#7f8c8d", bg="#f5f6fa", anchor="w", width=40)
        self.lbl_model.grid(row=1, column=1, padx=10, sticky="w")
        self.btn_select_model = tk.Button(file_lf, text="เลือกไฟล์", command=self.select_model, width=10, bg="#dcdde1")
        self.btn_select_model.grid(row=1, column=2, pady=3)

        tk.Label(file_lf, text="ไฟล์พิกัด (.txt):", font=("Helvetica", 10), bg="#f5f6fa").grid(row=2, column=0, sticky="w", pady=5)
        self.lbl_calib = tk.Label(file_lf, text="ยังไม่ได้เลือกไฟล์...", font=("Helvetica", 9, "italic"), fg="#7f8c8d", bg="#f5f6fa", anchor="w", width=40)
        self.lbl_calib.grid(row=2, column=1, padx=10, sticky="w")
        self.btn_select_calib = tk.Button(file_lf, text="เลือกไฟล์", command=self.select_calibration, width=10, bg="#dcdde1")
        self.btn_select_calib.grid(row=2, column=2, pady=3)
        self.btn_draw_zone = tk.Button(file_lf, text="✏️ วาด Zone เอง", command=self.draw_custom_zones, width=14, bg="#0984e3", fg="white", font=("Helvetica", 9, "bold"))
        self.btn_draw_zone.grid(row=2, column=3, pady=3, padx=(5,0))

        # === NEW กรอบที่ 2: ตั้งค่าพารามิเตอร์ระบบ ===
        param_lf = tk.LabelFrame(main_container, text=" 2. ตั้งค่าพารามิเตอร์ (Advanced Settings) ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=15, pady=10)
        param_lf.pack(fill=tk.X, pady=5)

        # จัด Layout แบบ Grid
        def add_param_row(parent, row, label_text, var, width, desc_text):
            tk.Label(parent, text=label_text, font=("Helvetica", 10, "bold"), bg="#f5f6fa").grid(row=row, column=0, sticky="e", pady=3, padx=5)
            tk.Entry(parent, textvariable=var, width=width, justify="center").grid(row=row, column=1, pady=3)
            tk.Label(parent, text=desc_text, font=("Helvetica", 9), fg="#57606f", bg="#f5f6fa").grid(row=row, column=2, sticky="w", pady=3, padx=10)

        add_param_row(param_lf, 0, "TTC_THRESHOLD :", self.var_ttc, 8, "ความไวแจ้งเตือน (วิ) - ถ้ารถจะถึงจุดตัดในเวลานี้ ระบบจะเตือน")
        add_param_row(param_lf, 1, "ARRIVAL_GAP :", self.var_gap, 8, "ความห่าง (วิ) - คัดกรองรถที่ขับผ่านไปแล้ว (เวลาถึงจุดตัดต่างกันเกินค่านี้จะไม่เตือน)")
        add_param_row(param_lf, 2, "TTC_LOOKAHEAD_S :", self.var_lookahead, 8, "มองล่วงหน้า (วิ) - ความยาวเส้นลูกศรเพื่อหาจุดตัดอนาคต")
        add_param_row(param_lf, 3, "FRAME_SKIP :", self.var_skip, 8, "ข้ามเฟรม - (1=วิเคราะห์ทุกเฟรมลื่นสุด, 2=ข้าม1เฟรมเพื่อลดกระตุก)")
        add_param_row(param_lf, 4, "ชดเชยความเร็ว (+/-) :", self.var_speed_comp, 8, "กม./ชม. - (บวกเพิ่มเมื่อรถวิ่ง > 15 km/h, ตัดเป็น 0 หากวิ่ง < 3 km/h)")

        # === กรอบที่ 3: เลือกวัตถุที่ต้องการตรวจจับ ===
        self.class_lf = tk.LabelFrame(main_container, text=" 3. เลือกวัตถุที่ต้องการตรวจจับ (โหลดอัตโนมัติ) ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=10, pady=5)
        self.class_lf.pack(fill=tk.BOTH, expand=True, pady=5)

        self.class_btn_frame = tk.Frame(self.class_lf, bg="#f5f6fa")
        self.class_btn_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.btn_select_all = tk.Button(self.class_btn_frame, text="☑ เลือกทั้งหมด", command=self.select_all_classes, bg="#dcdde1", font=("Helvetica", 9))
        self.btn_select_all.pack(side=tk.LEFT, padx=(0, 5))
        
        self.btn_deselect_all = tk.Button(self.class_btn_frame, text="☐ เอาออกทั้งหมด", command=self.deselect_all_classes, bg="#dcdde1", font=("Helvetica", 9))
        self.btn_deselect_all.pack(side=tk.LEFT)

        self.canvas = tk.Canvas(self.class_lf, bg="#f5f6fa", highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.class_lf, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.checkbox_frame = tk.Frame(self.canvas, bg="#f5f6fa")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.checkbox_frame, anchor="nw")

        self.checkbox_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.lbl_no_model = tk.Label(self.checkbox_frame, text="กรุณาเลือกไฟล์โมเดล AI (.pt) เพื่อดูรายการวัตถุ...", font=("Helvetica", 9, "italic"), fg="#7f8c8d", bg="#f5f6fa")
        self.lbl_no_model.pack(pady=10)

        # === Control Panel ===
        control_frame = tk.Frame(main_container, bg="#f5f6fa")
        control_frame.pack(fill=tk.X, pady=10)

        self.btn_start = tk.Button(control_frame, text="▶ เริ่มการวิเคราะห์", command=self.start_analysis, font=("Helvetica", 12, "bold"), bg="#44bd32", fg="white", width=18, pady=8)
        self.btn_start.pack(side=tk.LEFT, padx=(20, 10))
        self.btn_stop = tk.Button(control_frame, text="■ หยุดทำงาน", command=self.stop_analysis, font=("Helvetica", 12, "bold"), bg="#c23616", fg="white", width=18, pady=8, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        self.btn_dashboard = tk.Button(control_frame, text="📊 Dashboard", command=self.open_dashboard, font=("Helvetica", 12, "bold"), bg="#f39c12", fg="white", width=15, pady=8)
        self.btn_dashboard.pack(side=tk.RIGHT, padx=20)

        # Status Bar
        self.status_var = tk.StringVar()
        self.status_var.set("สถานะ: พร้อมใช้งาน (กรุณาเลือกไฟล์ให้ครบถ้วน)")
        status_bar = tk.Label(self.root, textvariable=self.status_var, font=("Helvetica", 9), fg="#57606f", bg="#dcdde1", anchor="w", padx=10, pady=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def open_dashboard(self):
        dashboard_window = tk.Toplevel(self.root)
        dashboard_window.focus_force() 
        viewer_app = ResultViewer(dashboard_window)

    def select_all_classes(self):
        for var in self.class_vars.values(): var.set(True)

    def deselect_all_classes(self):
        for var in self.class_vars.values(): var.set(False)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def select_video(self):
        path = filedialog.askopenfilename(title="เลือกไฟล์วิดีโอจราจร", filetypes=[('Video Files', '*.mp4 *.avi *.mov')])
        if path:
            self.video_path = path
            self.lbl_video.config(text=os.path.basename(path), fg="#2f3640", font=("Helvetica", 9, "bold"))
            self._check_ready_status()

    def select_model(self):
        path = filedialog.askopenfilename(title="เลือกไฟล์โมเดล YOLO (.pt)", filetypes=[('YOLO Model', '*.pt')])
        if path:
            self.model_path = path
            self.lbl_model.config(text=os.path.basename(path), fg="#2f3640", font=("Helvetica", 9, "bold"))
            self._check_ready_status()
            self.load_classes_from_model()

    def load_classes_from_model(self):
        try:
            self.status_var.set("สถานะ: กำลังอ่านข้อมูลคลาสจากโมเดล กรุณารอสักครู่...")
            self.root.update()

            from ultralytics import YOLO
            model = YOLO(self.model_path)
            classes_info = model.names 

            for widget in self.checkbox_frame.winfo_children():
                widget.destroy()

            self.class_vars = {}
            col, row = 0, 0
            
            for class_id, class_name in classes_info.items():
                var = tk.BooleanVar(value=True) 
                self.class_vars[class_id] = var
                
                display_text = f"{class_name.capitalize()} (ID: {class_id})"
                cb = tk.Checkbutton(self.checkbox_frame, text=display_text, variable=var, bg="#f5f6fa", font=("Helvetica", 9))
                cb.grid(row=row, column=col, sticky="w", padx=10, pady=2)
                
                col += 1
                if col > 3: 
                    col = 0
                    row += 1

            self.status_var.set("สถานะ: โหลดข้อมูลคลาสสำเร็จ พร้อมสำหรับการวิเคราะห์")

        except Exception as e:
            messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถอ่านข้อมูลคลาสจากโมเดลได้:\n{e}")
            self.status_var.set("สถานะ: เกิดข้อผิดพลาดในการดึงข้อมูลคลาส")

    def select_calibration(self):
        path = filedialog.askopenfilename(title="เลือกไฟล์พิกัด (.txt)", filetypes=[('Text Files', '*.txt')])
        if path:
            self.calibration_path = path
            self.lbl_calib.config(text=os.path.basename(path), fg="#2f3640", font=("Helvetica", 9, "bold"))
            self._check_ready_status()

    def draw_custom_zones(self):
        if not self.video_path:
            messagebox.showwarning("แจ้งเตือน", "กรุณาเลือกไฟล์วิดีโอก่อนครับ!")
            return
        save_path = filedialog.asksaveasfilename(title="ตั้งชื่อไฟล์บันทึกพิกัด Zone", defaultextension=".txt", filetypes=[('Text Files', '*.txt')])
        if save_path:
            from utils.zone_drawer import draw_zones_interactively
            self.root.withdraw()
            success, msg = draw_zones_interactively(self.video_path, save_path)
            self.root.deiconify()
            if success:
                self.calibration_path = save_path
                self.lbl_calib.config(text=os.path.basename(save_path), fg="#2f3640", font=("Helvetica", 9, "bold"))
                self._check_ready_status()
                messagebox.showinfo("สำเร็จ", msg)
            else:
                messagebox.showwarning("ยกเลิก", msg)

    def _check_ready_status(self):
        if self.video_path and self.model_path and self.calibration_path:
            self.status_var.set("สถานะ: เลือกไฟล์ครบแล้ว พร้อมสำหรับการวิเคราะห์")
        else:
            self.status_var.set("สถานะ: กำลังรอการเลือกไฟล์ข้อมูลให้ครบถ้วน...")

    def start_analysis(self):
        if not all([self.video_path, self.model_path, self.calibration_path]):
            messagebox.showwarning("ข้อมูลไม่ครบ", "กรุณาเลือกไฟล์ให้ครบทั้ง 3 ช่อง หรือวาด Zone ก่อนเริ่มทำงานครับ!")
            return

        selected_classes = [class_id for class_id, var in self.class_vars.items() if var.get()]
        
        if not selected_classes:
            messagebox.showwarning("แจ้งเตือน", "กรุณาเลือกวัตถุที่ต้องการตรวจจับอย่างน้อย 1 ประเภทครับ!")
            return

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        
        self.status_var.set("สถานะ: ระบบกำลังประมวลผลวิดีโอ...")
        
        # === NEW: ดึงค่าจากหน้าต่าง UI ไปให้ระบบวิเคราะห์ ===
        self.processor = VideoProcessor(
            self.video_path, 
            self.model_path, 
            self.calibration_path, 
            target_classes=selected_classes,
            ttc_threshold=self.var_ttc.get(),
            arrival_gap=self.var_gap.get(),
            ttc_lookahead_s=self.var_lookahead.get(),
            frame_skip=self.var_skip.get(),
            speed_comp=self.var_speed_comp.get()
        )
        self.processor.start()

    def stop_analysis(self):
        if self.processor:
            self.processor.stop()
            self.processor = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set("สถานะ: หยุดการประมวลผลเรียบร้อยแล้ว")

    def on_closing(self):
        if self.processor and self.processor.is_running:
            if messagebox.askokcancel("ปิดโปรแกรม", "ระบบกำลังทำงานอยู่ ต้องการปิดโปรแกรมใช่หรือไม่?"):
                self.processor.stop()
                self.root.destroy()
        else:
            self.root.destroy()