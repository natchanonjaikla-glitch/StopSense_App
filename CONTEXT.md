# StopSense - Project Context & Documentation

ระบบวิเคราะห์ความเสี่ยงอุบัติเหตุทางจราจรและแนวโน้มเส้นทางการเคลื่อนที่ล่วงหน้าด้วย AI (Traffic Risk Detection & Future Trajectory Analyzer)

---

## 1. ภาพรวมโปรเจกต์ (Project Overview)
**StopSense** เป็นแอปพลิเคชันบนระบบปฏิบัติการ Windows ที่ออกแบบมาเพื่อยกระดับความปลอดภัยทางถนน ผ่านการประมวลผลวิดีโอจราจรด้วยปัญญาประดิษฐ์ (Computer Vision) 
* **เป้าหมายการปรับใช้ (Deployment):** โปรเจกต์นี้เตรียมความพร้อมสำหรับการแพ็กเป็นสแตนด์อโลนไฟล์ `.exe` (ผ่าน PyInstaller/Auto-py-to-exe) 
* **ความสามารถหลัก:** ประเมินดัชนีเวลาที่อาจเกิดการชนกัน (Online TTC) และ ดัชนีจำลองจุดตัดวิถีการเคลื่อนที่ล่วงหน้าแบบออฟไลน์ (Future Trajectory Analysis)

---

## 2. โครงสร้างซอร์สโค้ด (Project Directory Structure)

```text
StopSense_App/
│
├── main.py                     # จุดสแกนหลักเข้าสู่โหมดวิเคราะห์เรียลไทม์ 
├── main_trajectory.py          # จุดสแกนหลักเข้าสู่โหมดวิเคราะห์วิถีล่วงหน้า 
├── icon_realtime.ico           # ไฟล์ไอคอนหลัก 
│
├── core/                       
│   ├── video_processor.py      # เอ็นจิ้นคำนวณ Online TTC และความเร็วเชิงกายภาพ 
│   └── offline_processor.py    # เอ็นจิ้นวิเคราะห์ Future Trajectory และหาความเร็วจากโซน
│
├── gui/                        
│   ├── main_window.py          # หน้าต่างหลักตั้งค่าพารามิเตอร์โหมด Real-time
│   ├── trajectory_window.py    # หน้าต่างโหมด Offline (รองรับการวาด Zone และตั้งค่าคลาสแบบ Bulk)
│   └── viewer.py               # คลาส ResultViewer สำหรับแสดง Dashboard และภาพหลักฐาน (รองรับ Zoom/Pan)
│
├── utils/                      
│   ├── zone_drawer.py          # เครื่องมือวาดโซน 4 จุดเพื่อหา Homography Matrix
│   ├── get_fps.py              # ตัวดึงค่าอัตราเฟรมวิดีโอ (FPS) 
│   └── file_manager.py         # จัดการ Risk Event, ตัดภาพ และบันทึก CSV (UTF-8-SIG)
│
└── models/                     
    └── rtdetr-x.pt             # โมเดล AI หลัก (รองรับ Git LFS)


    ## 3. รายละเอียดโครงสร้างส่วนประกอบและตรรกะ (Logic Deep-Dive)

### 3.1 `core/video_processor.py` (Online TTC Engine)
* **การทำงาน:** ทำงานแบบ Real-time ตรวจจับและแทร็กวัตถุ (YOLO + ByteTrack) แปลงพิกัดภาพเป็นพิกัดกายภาพผ่าน Homography Matrix เพื่อหาความเร็ว (km/h)
* **การหาความเสี่ยง:** ใช้หลักการ Ray-Segment Intersection (TTC) หากรถมีระยะห่างทางเวลาก่อนชนน้อยกว่าที่กำหนด จะบันทึกภาพและล็อกทันที

### 3.2 `core/offline_processor.py` (Future Trajectory Engine)
* **การทำงานสองระยะ (Two-Phase):**
  * **Phase 1 (Data Gathering):** สแกนทั้งวิดีโอเพื่อจดจำ Tracker ID และตำแหน่ง (x, y) ของรถทุกคันในทุกเฟรมเก็บไว้ในหน่วยความจำ
  * **Phase 2 (Analysis):** ลากเส้นวิถีล่วงหน้าตามเวลาที่กำหนด (`lookahead_s`) เพื่อหาโอกาสชน
* **ตรรกะโอกาสเกิดอุบัติเหตุ (Decoupled Logic):**
  * **CROSSING:** เส้นทางของรถ 2 คันในอนาคต "ตัดกัน" ชัดเจน (ระยะห่าง < 20 px)
  * **PROXIMITY:** เส้นทางไม่ตัด แต่ "ขนานเบียดกัน" ในระยะอันตราย (ระยะห่าง < `proximity_px`) ผู้ใช้สามารถปิดการคำนวณส่วนนี้ได้
* **การคำนวณความเร็ว (Zone-based Speed):** หากมีการโหลดไฟล์ Zone (`.txt`) โปรแกรมจะแปลงพิกัดและดึงตำแหน่งรถย้อนหลัง 1 วินาทีมาเทียบเพื่อหาความเร็ว (km/h) โดยตรรกะความเร็วนี้จะแสดงผลบนหน้าจอเท่านั้น ไม่มีผลนำไปคิดรวมกับโอกาสเกิดอุบัติเหตุ

### 3.3 `gui/viewer.py` (Risk Intelligence Dashboard)
* **คลาสหลัก:** `ResultViewer` (เชื่อมต่อจากเมนู Dashboard ของหน้าต่างหลัก)
* **การทำงาน:** โหลดข้อมูลจาก `risk_summary_log.csv` แสดงลง Treeview เมื่อคลิกแถวจะแสดงภาพจากโฟลเดอร์ผลลัพธ์
* **ฟีเจอร์พิเศษบน Canvas:** ผู้ใช้สามารถใช้ MouseWheel ซูมภาพ และลากเมาส์ (Drag to Pan) เพื่อดูป้ายทะเบียนได้

---

## 4. มาตรฐานข้อมูล (Data & Logging Standards)

* **รูปแบบไฟล์:** บันทึกเป็น CSV เข้ารหัส **UTF-8-SIG** เพื่อให้สามารถเปิดใน Excel ได้โดยภาษาไทยไม่เพี้ยน
* **Prefix การบันทึก:** ในโหมดออฟไลน์ การบันทึกเหตุการณ์ผ่าน `utils/file_manager.py` จะถูกบังคับใส่ Prefix ไว้ที่ประเภทเหตุการณ์ (เช่น `FUTURE_CROSSING`, `FUTURE_PROXIMITY`) เพื่อให้แยกข้อมูลออกจากโหมด Real-time ได้อย่างชัดเจนเมื่อดูผ่าน Dashboard
* **การตัดภาพ (Risk Frames):** ทุกครั้งที่เกิดเหตุการณ์ จะดึงภาพเฟรมนั้นมาวาด Bounding Box ย้อนหลัง และบันทึกลงโฟลเดอร์แยกตามรอบรัน (รูปแบบ `Run_YYYYMMDD_HHMMSS`)

---

## 5. แนวทางปฏิบัติสำหรับผู้พัฒนา (Developer Guidelines & Constraints)

* **AI & Developer Note - การทำ Executable (`.exe`):** เนื่องจากโปรเจกต์นี้จะถูก Build ด้วย PyInstaller หากมีการเขียนโค้ดที่ต้องอ้างอิงไฟล์รูปภาพ (เช่น Icon) หรือไฟล์ AI Model ภายใน Directory ของโปรแกรม จะต้องใช้ฟังก์ชันห่อหุ้ม Path เพื่อรองรับ Temp Folder (`sys._MEIPASS`) เสมอ เพื่อป้องกันปัญหา File Not Found หลังจาก Build เสร็จสิ้น