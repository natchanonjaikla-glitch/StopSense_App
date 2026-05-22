import cv2
import numpy as np
import tkinter as tk
from tkinter import simpledialog

current_points = []
zones = []

def mouse_callback(event, x, y, flags, param):
    global current_points
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(current_points) < 4:
            current_points.append((x, y))

def draw_zones_interactively(video_path, save_path):
    global current_points, zones
    current_points = []
    zones = []

    cap = cv2.VideoCapture(video_path)
    ret, orig_frame = cap.read()
    cap.release()

    if not ret: return False, "ไม่สามารถอ่านไฟล์วิดีโอได้"

    cv2.namedWindow("StopSense - Draw Zones", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("StopSense - Draw Zones", mouse_callback)
    zone_counter = 1

    # ข้อความแนะนำการจิ้มจุด
    instructions = [
        "Point 1: มุมซ้าย-บน (Top-Left)",
        "Point 2: มุมขวา-บน (Top-Right)",
        "Point 3: มุมขวา-ล่าง (Bottom-Right)",
        "Point 4: มุมซ้าย-ล่าง (Bottom-Left)"
    ]

    while True:
        frame = orig_frame.copy()
        
        # วาด Zone เก่าที่วาดเสร็จไปแล้ว
        for z in zones:
            pts = np.array(z['points'], np.int32)
            cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
            cv2.putText(frame, z['name'], (pts[0][0], pts[0][1]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # เขียนระยะกำกับบนแต่ละเส้นของ Zone เก่า
            for i in range(4):
                pt1, pt2 = pts[i], pts[(i+1)%4]
                mid_x, mid_y = (pt1[0]+pt2[0])//2, (pt1[1]+pt2[1])//2
                cv2.putText(frame, f"L{i+1}: {z['lengths'][i]}m", (mid_x-20, mid_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # วาดจุดและเส้นที่กำลังจิ้มปัจจุบัน
        for i, pt in enumerate(current_points):
            cv2.circle(frame, pt, 5, (0, 0, 255), -1)
            cv2.putText(frame, f"P{i+1}", (pt[0]+10, pt[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            if i > 0:
                pt_prev = current_points[i-1]
                cv2.line(frame, pt_prev, pt, (0, 0, 255), 2)
                mid_x, mid_y = (pt_prev[0]+pt[0])//2, (pt_prev[1]+pt[1])//2
                cv2.putText(frame, f"Line {i}", (mid_x-20, mid_y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # เมื่อคลิกครบ 4 จุด ให้ตีเส้นปิดท้าย (Line 4)
        if len(current_points) == 4:
            pt_prev, pt_first = current_points[3], current_points[0]
            cv2.line(frame, pt_prev, pt_first, (0, 0, 255), 2)
            mid_x, mid_y = (pt_prev[0]+pt_first[0])//2, (pt_prev[1]+pt_first[1])//2
            cv2.putText(frame, "Line 4", (mid_x-20, mid_y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            cv2.putText(frame, "Press [Enter] to SAVE Zone, [r] to RESET, [q] to FINISH", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        else:
            cv2.putText(frame, f"Zone {zone_counter}: Click {instructions[len(current_points)]}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, "Press [q] when done.", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("StopSense - Draw Zones", frame)
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'): break
        elif key == ord('r'): current_points = []
        elif key == 13 and len(current_points) == 4: # กด Enter
            root = tk.Tk()
            root.withdraw()
            
            # เด้งหน้าต่างถามระยะทั้ง 4 เส้น
            l1 = simpledialog.askfloat("ระยะทางจริง", f"ความยาว [Line 1] เส้นบน (เมตร):", parent=root, minvalue=0.1)
            l2 = simpledialog.askfloat("ระยะทางจริง", f"ความยาว [Line 2] เส้นขวา (เมตร):", parent=root, minvalue=0.1)
            l3 = simpledialog.askfloat("ระยะทางจริง", f"ความยาว [Line 3] เส้นล่าง (เมตร):", parent=root, minvalue=0.1)
            l4 = simpledialog.askfloat("ระยะทางจริง", f"ความยาว [Line 4] เส้นซ้าย (เมตร):", parent=root, minvalue=0.1)
            
            root.destroy()
            
            # เช็คว่ากรอกข้อมูลครบหรือไม่
            if all([l1, l2, l3, l4]):
                zones.append({
                    'name': f"Zone_{zone_counter}", 
                    'points': current_points.copy(),
                    'lengths': [l1, l2, l3, l4]
                })
                zone_counter += 1
                current_points = []
            else:
                print("ยกเลิกการสร้าง Zone เนื่องจากกรอกระยะทางไม่ครบ")
                current_points = []
    
    cv2.destroyAllWindows()
    
    # บันทึกไฟล์รูปแบบใหม่: ชื่อ, L1, L2, L3, L4 ตามด้วยพิกัด
    if len(zones) > 0:
        with open(save_path, 'w', encoding='utf-8') as f:
            for z in zones:
                f.write(f"{z['name']},{z['lengths'][0]},{z['lengths'][1]},{z['lengths'][2]},{z['lengths'][3]}\n")
                for pt in z['points']: f.write(f"{pt[0]},{pt[1]}\n")
        return True, "บันทึก Zone และระยะทางสำเร็จ"
    return False, "ไม่มีการวาด Zone ใดๆ"