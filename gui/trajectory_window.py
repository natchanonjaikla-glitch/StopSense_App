import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading

from core.offline_processor import FutureTrajectoryAnalyzer

class TrajectoryWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("StopSense - Future Trajectory Analyzer")
        self.root.geometry("850x850")
        self.root.configure(bg="#f5f6fa")
        
        self.video_path, self.model_path, self.processor = "", "", None
        self.output_base_dir = os.path.abspath("output")
        
        self.class_vars = {} 
        self.var_lookahead = tk.DoubleVar(value=3.0)
        self.var_proximity = tk.DoubleVar(value=80.0)
        self.var_calc_parallel = tk.BooleanVar(value=True)
        self._create_widgets()

    def _create_widgets(self):
        header = tk.Frame(self.root, bg="#192a56", height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="Future Trajectory Analyzer", font=("Helvetica", 16, "bold"), fg="#f5f6fa", bg="#192a56").pack(pady=22)

        main = tk.Frame(self.root, bg="#f5f6fa", padx=20, pady=10)
        main.pack(fill=tk.BOTH, expand=True)

        # 1. เลือกไฟล์และโฟลเดอร์ผลลัพธ์
        file_lf = tk.LabelFrame(main, text=" 1. เลือกไฟล์และที่อยู่จัดเก็บ ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=15, pady=10)
        file_lf.pack(fill=tk.X, pady=5)
        
        tk.Button(file_lf, text="เลือกวิดีโอ", command=self.select_video, width=12).grid(row=0, column=0, pady=5)
        self.lbl_video = tk.Label(file_lf, text="ยังไม่ได้เลือก...", bg="#f5f6fa"); self.lbl_video.grid(row=0, column=1, padx=10, sticky="w")
        
        tk.Button(file_lf, text="เลือกโมเดล", command=self.select_model, width=12).grid(row=1, column=0, pady=5)
        self.lbl_model = tk.Label(file_lf, text="ยังไม่ได้เลือก...", bg="#f5f6fa"); self.lbl_model.grid(row=1, column=1, padx=10, sticky="w")
        
        tk.Button(file_lf, text="โฟลเดอร์บันทึกผล", command=self.select_output_dir, width=12).grid(row=2, column=0, pady=5)
        self.lbl_output = tk.Label(file_lf, text=self.output_base_dir, bg="#f5f6fa", fg="#2980b9", font=("Helvetica", 9, "bold")); self.lbl_output.grid(row=2, column=1, padx=10, sticky="w")

        # 2. ตั้งค่า
        param_lf = tk.LabelFrame(main, text=" 2. ตั้งค่า ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=15, pady=10)
        param_lf.pack(fill=tk.X, pady=5)
        tk.Label(param_lf, text="ดูล่วงหน้า (วิ):", bg="#f5f6fa").grid(row=0, column=0, sticky="w")
        tk.Entry(param_lf, textvariable=self.var_lookahead, width=8).grid(row=0, column=1, padx=10)
        tk.Checkbutton(param_lf, text="คำนวณระยะประชิดด้วย (ขนานกัน)", variable=self.var_calc_parallel, bg="#f5f6fa").grid(row=1, column=0, columnspan=2, sticky="w")

        # 3. คลาส
        self.class_lf = tk.LabelFrame(main, text=" 3. วัตถุที่ตรวจจับ ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", height=150)
        self.class_lf.pack(fill=tk.X, pady=5); self.class_lf.pack_propagate(False)
        self.canvas = tk.Canvas(self.class_lf, bg="#f5f6fa"); self.scrollbar = ttk.Scrollbar(self.class_lf, orient="vertical", command=self.canvas.yview)
        self.checkbox_frame = tk.Frame(self.canvas, bg="#f5f6fa")
        self.canvas.create_window((0, 0), window=self.checkbox_frame, anchor="nw")
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y); self.canvas.pack(fill=tk.BOTH, expand=True)
        self.checkbox_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # 4. Logs
        log_lf = tk.LabelFrame(main, text=" 4. Logs ", font=("Helvetica", 11, "bold"), bg="#f5f6fa", padx=10)
        log_lf.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_text = tk.Text(log_lf, bg="#2f3542", fg="#f1f2f6", font=("Courier New", 9), state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Control Panel
        cp = tk.Frame(main, bg="#f5f6fa")
        cp.pack(fill=tk.X, pady=10)
        self.btn_start = tk.Button(cp, text="▶ เริ่มสแกน", command=self.start_analysis, bg="#44bd32", fg="white", font=("Helvetica", 12, "bold"), width=15)
        self.btn_start.pack(side=tk.LEFT, padx=10)
        
        tk.Button(cp, text="📊 Dashboard", command=self.open_dashboard, bg="#f39c12", fg="white", font=("Helvetica", 11, "bold"), width=12).pack(side=tk.RIGHT, padx=5)
        tk.Button(cp, text="📁 โฟลเดอร์ผลลัพธ์", command=self.open_output_folder, bg="#0984e3", fg="white", font=("Helvetica", 11, "bold"), width=15).pack(side=tk.RIGHT, padx=5)

        self.status_var = tk.StringVar(value="พร้อมใช้งาน")
        tk.Label(self.root, textvariable=self.status_var, bg="#dcdde1", anchor="w", padx=10).pack(side=tk.BOTTOM, fill=tk.X)

    def append_log(self, msg):
        self.log_text.config(state=tk.NORMAL); self.log_text.insert(tk.END, msg + "\n"); self.log_text.see(tk.END); self.log_text.config(state=tk.DISABLED)

    # === อัปเดตฟังก์ชันเรียก Dashboard ===
    def open_dashboard(self):
        try:
            from gui.viewer import DashboardWindow 
            
            dash_win = tk.Toplevel(self.root)
            app = DashboardWindow(dash_win)
            
        except ImportError:
            messagebox.showerror("Error", "ไม่พบคลาส DashboardWindow ในไฟล์ gui/viewer.py\nกรุณาตรวจสอบชื่อคลาสในไฟล์ viewer.py ครับ")
        except Exception as e:
            messagebox.showerror("Error", f"เกิดข้อผิดพลาดในการเปิด Dashboard: {e}")
    # ====================================

    def open_output_folder(self):
        if os.path.exists(self.output_base_dir):
            os.startfile(self.output_base_dir)
        else:
            messagebox.showinfo("แจ้งเตือน", "ยังไม่มีโฟลเดอร์ผลลัพธ์ครับ")

    def select_video(self):
        path = filedialog.askopenfilename(); self.video_path = path; self.lbl_video.config(text=os.path.basename(path))

    def select_model(self):
        path = filedialog.askopenfilename(filetypes=[('YOLO Model', '*.pt')]); self.model_path = path; self.lbl_model.config(text=os.path.basename(path)); self.load_classes()

    def select_output_dir(self):
        path = filedialog.askdirectory()
        if path: self.output_base_dir = path; self.lbl_output.config(text=path)

    def load_classes(self):
        try:
            from ultralytics import YOLO
            model = YOLO(self.model_path)
            for widget in self.checkbox_frame.winfo_children(): widget.destroy()
            self.class_vars = {}
            r, c = 0, 0
            for cid, name in model.names.items():
                var = tk.BooleanVar(value=True); self.class_vars[cid] = var
                tk.Checkbutton(self.checkbox_frame, text=name, variable=var, bg="#f5f6fa").grid(row=r, column=c, sticky="w", padx=5)
                c += 1
                if c > 3: c=0; r+=1
        except Exception as e:
            messagebox.showerror("Error", f"โหลดโมเดลไม่สำเร็จ: {e}")

    def start_analysis(self):
        selected = [cid for cid, v in self.class_vars.items() if v.get()]
        if not self.video_path or not self.model_path:
            messagebox.showwarning("เตือน", "โปรดเลือกวิดีโอและโมเดล")
            return
            
        self.processor = FutureTrajectoryAnalyzer(
            video_path=self.video_path, 
            model_path=self.model_path, 
            output_dir=self.output_base_dir, 
            target_classes=selected, 
            log_callback=self.append_log, 
            calc_parallel=self.var_calc_parallel.get()
        )
        self.log_text.config(state=tk.NORMAL); self.log_text.delete("1.0", tk.END); self.log_text.config(state=tk.DISABLED)
        threading.Thread(target=lambda: self.processor.run_analysis(), daemon=True).start()