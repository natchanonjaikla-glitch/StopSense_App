import os
import cv2
from datetime import datetime

def handle_risk_event(tracker_id_a, tracker_id_b, class_name_a, class_name_b, 
                      event_type, metric_value, zone_name, 
                      save_log, save_frame, frame, output_dir, frame_number):
    """
    ฟังก์ชันสำหรับจัดการบันทึกข้อมูลสรุปผล (Log) และรูปภาพเมื่อเกิดความเสี่ยง
    """
    
    # 1. สร้างโฟลเดอร์หลักและโฟลเดอร์เก็บรูป (ถ้ายังไม่มี)
    os.makedirs(output_dir, exist_ok=True)
    frames_dir = os.path.join(output_dir, "risk_frames")
    os.makedirs(frames_dir, exist_ok=True)
    
    # 2. ดึงวันและเวลาปัจจุบัน
    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    file_time_str = now.strftime("%H%M%S") # สำหรับตั้งชื่อไฟล์ไม่ให้ซ้ำกัน
    
    # 3. บันทึกรูปภาพจังหวะเสี่ยง (.jpg)
    if save_frame and frame is not None:
        # ตั้งชื่อไฟล์รูปให้รู้เลยว่าเกิดอะไรขึ้น เช่น Risk_Frame150_142030_car_vs_motorcycle.jpg
        image_name = f"Risk_Frame{frame_number}_{file_time_str}_{class_name_a}_vs_{class_name_b}.jpg"
        image_path = os.path.join(frames_dir, image_name)
        cv2.imwrite(image_path, frame)
        
    # 4. บันทึกข้อมูลสรุปผลลงไฟล์ .csv (เปิดใน Excel ได้)
    if save_log:
        log_file = os.path.join(output_dir, "risk_summary_log.csv")
        
        # ถ้าไฟล์เพิ่งถูกสร้างครั้งแรก ให้เขียนหัวตาราง (Header) ก่อน
        # ใช้ utf-8-sig เพื่อให้เปิดใน Excel แล้วภาษาไทย/ภาษาอังกฤษไม่เป็นภาษาต่างดาว
        if not os.path.exists(log_file):
            with open(log_file, "w", encoding="utf-8-sig") as f:
                f.write("วันที่_เวลา,เฟรมที่,โซนวิเคราะห์,ประเภทเหตุการณ์,เวลาชน(TTC_วินาที),วัตถุที่1,ID_1,วัตถุที่2,ID_2\n")
        
        # เขียนข้อมูลเหตุการณ์ที่เกิดขึ้นลงไปบรรทัดใหม่
        with open(log_file, "a", encoding="utf-8-sig") as f:
            f.write(f"{timestamp_str},{frame_number},{zone_name},{event_type},{metric_value:.2f},{class_name_a},{tracker_id_a},{class_name_b},{tracker_id_b}\n")
            
        # พิมพ์บอกใน Terminal (Console) ด้วยเพื่อความอุ่นใจ
        print(f"⚠️ [ALERT] บันทึกเหตุการณ์: {class_name_a} หวิดชน {class_name_b} (TTC: {metric_value:.1f}s) ที่ {zone_name}")