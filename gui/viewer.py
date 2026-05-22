import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import csv
import os
import glob
from PIL import Image, ImageTk

class ResultViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("StopSense - Dashboard รายงานความเสี่ยงอุบัติเหตุ (ซูมภาพได้)")
        self.root.geometry("1100x750") # ปรับหน้าต่างให้ใหญ่ขึ้นเล็กน้อย
        self.root.configure(bg="#f5f6fa")

        # --- ตัวแปรสำหรับระบบซูมและเลื่อนภาพ ---
        self.output_dir = ""
        self.log_data = []
        self.pil_image = None      # เก็บรูปต้นฉบับ PIL
        self.tk_image = None       # เก็บรูปที่แปลงสำหรับแสดงผล
        self.image_item = None     # เก็บ object รูปบน Canvas
        self.zoom_level = 1.0      # ระดับการซูมปัจจุบัน
        self.origin_x = 0          # พิกัด x เริ่มต้นตอนลากเมาส์
        self.origin_y = 0          # พิกัด y เริ่มต้นตอนลากเมาส์

        self._create_widgets()

    def _create_widgets(self):
        # === ส่วนหัว (Top Bar) ===
        top_frame = tk.Frame(self.root, bg="#2f3640", pady=15)
        top_frame.pack(fill=tk.X)

        btn_load = tk.Button(top_frame, text="📁 เลือกโฟลเดอร์ Output", command=self.load_output_folder, 
                             bg="#0984e3", fg="white", font=("Helvetica", 10, "bold"), padx=10, pady=5)
        btn_load.pack(side=tk.LEFT, padx=20)
        
        self.lbl_folder = tk.Label(top_frame, text="กรุณาเลือกโฟลเดอร์ output ที่ได้จากการประมวลผล...", 
                                   bg="#2f3640", fg="#dcdde1", font=("Helvetica", 10, "italic"))
        self.lbl_folder.pack(side=tk.LEFT)

        # === หน้าต่างหลักแบ่งซ้ายขวา (PanedWindow) ===
        paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # === ฝั่งซ้าย: ตารางข้อมูล Log (Treeview) ===
        left_frame = tk.Frame(paned_window, bg="white", bd=1, relief=tk.SUNKEN)
        paned_window.add(left_frame, weight=1)

        lbl_table = tk.Label(left_frame, text="📊 รายการเหตุการณ์เสี่ยงชน (คลิกเพื่อดูภาพ)", bg="#dcdde1", font=("Helvetica", 10, "bold"), pady=5)
        lbl_table.pack(fill=tk.X)

        columns = ("เวลา", "เฟรม", "โซน", "TTC (วิ)", "คู่กรณี")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", selectmode="browse")
        
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("เวลา", width=140, anchor=tk.CENTER)
        self.tree.column("เฟรม", width=60, anchor=tk.CENTER)
        self.tree.column("โซน", width=80, anchor=tk.CENTER)
        self.tree.column("TTC (วิ)", width=60, anchor=tk.CENTER)
        self.tree.column("คู่กรณี", width=120, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)

        # === NEW ฝั่งขวา: หน้าจอแสดงภาพ (เปลี่ยนเป็น Canvas สำหรับซูม) ===
        self.right_frame = tk.Frame(paned_window, bg="#353b48", bd=1, relief=tk.SUNKEN)
        paned_window.add(self.right_frame, weight=2)

        # สร้าง Canvas สำหรับแสดงรูป
        self.canvas = tk.Canvas(self.right_frame, bg="#353b48", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ใส่ข้อความแนะนำเบื้องต้น
        self.lbl_instruction = tk.Label(self.canvas, text="🖼️ รอการเลือกข้อมูลจากตาราง...\n(กลิ้งเมาส์เพื่อซูม, คลิกซ้ายลากเพื่อเลื่อน)", 
                                         font=("Helvetica", 12), fg="#7f8c8d", bg="#353b48")
        self.instruction_window = self.canvas.create_window(10, 10, window=self.lbl_instruction, anchor="nw")
        
        # ผูกอีเวนต์สำหรับเมาส์เพื่อซูมและเลื่อน
        self.canvas.bind("<MouseWheel>", self.on_zoom)          # ซูม (Windows)
        self.canvas.bind("<Button-4>", self.on_zoom)            # ซูมเข้า (Linux)
        self.canvas.bind("<Button-5>", self.on_zoom)            # ซูมออก (Linux)
        
        self.canvas.bind("<ButtonPress-1>", self.on_pan_start)  # เริ่มลากภาพ
        self.canvas.bind("<B1-Motion>", self.on_pan_move)       # กำลังลากภาพ

        # จัดการตำแหน่งข้อความแนะนำเมื่อเปลี่ยนขนาดหน้าต่าง
        self.right_frame.bind("<Configure>", self.on_frame_configure)

    def on_frame_configure(self, event):
        """จัดข้อความแนะนำให้อยู่ตรงกลางเสมอ"""
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.coords(self.instruction_window, w//2, h//2)
        self.lbl_instruction.config(anchor="center")
        
        # ถ้ารูปโหลดอยู่ ให้ปรับสเกลใหม่ให้พอดีจอตอนเปลี่ยนขนาดหน้าต่าง
        if self.pil_image:
            self.show_image_fit()

    def load_output_folder(self):
        folder_path = filedialog.askdirectory(title="เลือกโฟลเดอร์ Output ของ StopSense")
        if not folder_path: return

        csv_path = os.path.join(folder_path, "risk_summary_log.csv")
        if not os.path.exists(csv_path):
            messagebox.showerror("ไม่พบไฟล์ Log", f"ไม่พบไฟล์ 'risk_summary_log.csv' ในโฟลเดอร์นี้ครับ")
            return

        self.output_dir = folder_path
        self.lbl_folder.config(text=folder_path, fg="white", font=("Helvetica", 10))
        self.log_data = []

        for item in self.tree.get_children(): self.tree.delete(item)

        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                next(reader, None) # ข้าม header
                for i, row in enumerate(reader):
                    if len(row) >= 9:
                        time_str = row[0].split()[1]
                        frame_num = row[1]; zone = row[2]; ttc = row[4]
                        obj_pair = f"{row[5]} ⚡ {row[7]}"
                        self.log_data.append(row)
                        self.tree.insert("", tk.END, values=(time_str, frame_num, zone, ttc, obj_pair), tags=(str(i),))
        except Exception as e: messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถอ่านไฟล์ CSV ได้:\n{e}")

    def on_item_select(self, event):
        selected = self.tree.selection()
        if not selected: return

        item_tags = self.tree.item(selected[0], "tags")
        if not item_tags: return
        
        idx = int(item_tags[0])
        row = self.log_data[idx]
        frame_num = row[1]

        frames_dir = os.path.join(self.output_dir, "risk_frames")
        search_pattern = os.path.join(frames_dir, f"Risk_Frame{frame_num}_*.jpg")
        matching_files = glob.glob(search_pattern)

        if matching_files:
            # ซ่อนข้อความแนะนำ
            self.canvas.itemconfigure(self.instruction_window, state='hidden')
            # โหลดรูป
            self.load_pil_image(matching_files[0])
        else:
            self.canvas.itemconfigure(self.instruction_window, state='normal')
            self.lbl_instruction.config(text="❌ ไม่พบรูปภาพหลักฐานสำหรับเหตุการณ์นี้", fg="#c23616")
            self.canvas.delete("all")
            self.pil_image = None

    def load_pil_image(self, img_path):
        """โหลดรูปต้นฉบับ PIL และแสดงผลแบบพอดีจอครั้งแรก"""
        try:
            self.pil_image = Image.open(img_path)
            self.zoom_level = 1.0 # รีเซ็ตระดับซูม
            self.show_image_fit()
        except Exception as e:
            messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถโหลดรูปได้:\n{e}")

    def show_image_fit(self):
        """คำนวณสเกลเพื่อแสดงรูปให้พอดีกับพื้นที่ Canvas ปัจจุบัน (ไม่เบี้ยว)"""
        if not self.pil_image: return

        # อัปเดตขนาด UI เพื่อให้ได้ขนาด Canvas ที่ถูกต้อง
        self.root.update_idletasks()
        canv_w = self.canvas.winfo_width()
        canv_h = self.canvas.winfo_height()

        # ป้องกันบั๊กขนาดศูนย์ตอนเปิดโปรแกรม
        if canv_w < 10 or canv_h < 10: canv_w, canv_h = 800, 600

        img_w, img_h = self.pil_image.size

        # หาอัตราส่วนสเกลเพื่อให้รูปพอดี
        ratio_w = canv_w / img_w
        ratio_h = canv_h / img_h
        self.fit_scale = min(ratio_w, ratio_h)
        
        # เริ่มต้นแสดงผลที่สเกลพอดีจอ
        self.zoom_level = self.fit_scale
        self.update_canvas_image()

    def update_canvas_image(self):
        """แปลงรูปตามระดับซูมปัจจุบันและวาดลงบน Canvas"""
        if not self.pil_image: return

        # คำนวณขนาดรูปใหม่ตามระดับการซูม
        img_w, img_h = self.pil_image.size
        new_w = int(img_w * self.zoom_level)
        new_h = int(img_h * self.zoom_level)

        # ป้องกันการย่อรูปจนเล็กเกินไปหรือใหญ่เกินไป
        if new_w < 50 or new_h < 50: return 

        # ย่อ/ขยายรูปด้วยคุณภาพสูงสุด
        res_img = self.pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # แปลงเป็น PhotoImage สำหรับ Tkinter
        self.tk_image = ImageTk.PhotoImage(res_img)

        # ล้างรูปเก่าและวาดรูปใหม่ตรงกลาง Canvas
        self.canvas.delete("image")
        canv_w = self.canvas.winfo_width()
        canv_h = self.canvas.winfo_height()
        self.image_item = self.canvas.create_image(canv_w // 2, canv_h // 2, image=self.tk_image, anchor="center", tags="image")
        
        # ปรับพื้นที่การเลื่อน (Scrollregion) ให้ครอบคลุมรูปภาพทั้งหมด
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # --- ระบบซูม (Zooming) ---
    def on_zoom(self, event):
        """จัดการการซูมด้วยลูกกลิ้งเมาส์"""
        if not self.pil_image: return

        # ตรวจสอบทิศทางการกลิ้ง (Windows/Linux)
        if event.num == 4 or event.delta > 0:    # กลิ้งขึ้น = ซูมเข้า
            zoom_factor = 1.1
        elif event.num == 5 or event.delta < 0: # กลิ้งลง = ซูมออก
            zoom_factor = 0.9
        else: zoom_factor = 1.0

        new_zoom_level = self.zoom_level * zoom_factor

        # จำกัดขอบเขตการซูม (ไม่ให้เล็กกว่าพอดีจอ และไม่ให้ใหญ่กว่า 5 เท่าของรูปจริง)
        if new_zoom_level < self.fit_scale * 0.8: new_zoom_level = self.fit_scale * 0.8
        if new_zoom_level > 5.0: new_zoom_level = 5.0

        # อัปเดตรูป
        self.zoom_level = new_zoom_level
        self.update_canvas_image()

    # --- ระบบเลื่อนภาพ (Panning) ---
    def on_pan_start(self, event):
        """บันทึกพิกัดเมาส์ตอนเริ่มคลิกซ้าย"""
        self.canvas.scan_mark(event.x, event.y)

    def on_pan_move(self, event):
        """เลื่อนภาพตามการลากเมาส์"""
        self.canvas.scan_dragto(event.x, event.y, gain=1)

if __name__ == "__main__":
    # สำหรับทดสอบรันแยกไฟล์
    root = tk.Tk()
    app = ResultViewer(root)
    root.mainloop()