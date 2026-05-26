import cv2
import numpy as np
import time
import os
import json
import datetime 
from collections import defaultdict
from ultralytics import YOLO
import supervision as sv

from utils.file_manager import handle_risk_event

# ==================== Math Helpers (สำหรับคำนวณความเร็ว) ====================
def transform_point(point, H):
    if H is None: return None
    pt = np.array([[[float(point[0]), float(point[1])]]], dtype=np.float32)
    return cv2.perspectiveTransform(pt, H)[0][0]

def calculate_real_distance(p1, p2, H):
    if H is None: return None
    r1, r2 = transform_point(p1, H), transform_point(p2, H)
    if r1 is None or r2 is None: return None
    return float(np.hypot(r2[0] - r1[0], r2[1] - r1[1]))

def is_point_in_polygon(point, polygon):
    if polygon is None: return True
    return cv2.pointPolygonTest(polygon, (float(point[0]), float(point[1])), False) >= 0
# ============================================================================

class FutureTrajectoryAnalyzer:
    def __init__(self, video_path, model_path, calibration_path="", output_dir="output", 
                 lookahead_s=3.0, proximity_px=80.0, target_classes=None,
                 log_callback=None, calc_parallel=True):
        self.video_path = video_path
        self.model_path = model_path
        self.calibration_path = calibration_path
        self.base_output_dir = output_dir 
        self.lookahead_s = lookahead_s      
        self.proximity_px = proximity_px    
        self.target_classes = target_classes if target_classes else [0, 1, 2, 3, 5, 7]
        self.log_callback = log_callback
        self.calc_parallel = calc_parallel
        
        self.history_positions = defaultdict(dict) 
        self.history_classes = {}                  
        self.conflict_logs = []

    def log(self, message):
        print(message)
        if self.log_callback:
            self.log_callback(message)

    def _euclidean_distance(self, pt1, pt2):
        return np.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2)

    def load_zone_from_txt(self):
        zones = []
        if not self.calibration_path or not os.path.exists(self.calibration_path):
            return zones
            
        try:
            with open(self.calibration_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            i = 0
            while i < len(lines):
                zone_info = lines[i].split(',')
                name = zone_info[0]
                if len(zone_info) >= 5:
                    l1, l2, l3, l4 = float(zone_info[1]), float(zone_info[2]), float(zone_info[3]), float(zone_info[4])
                else:
                    l1, l2, l3, l4 = 10.0, 20.0, 10.0, 20.0
                
                points = []
                for j in range(1, 5):
                    if i + j < len(lines):
                        pts = lines[i+j].split(',')
                        if len(pts) >= 2: 
                            points.append((int(float(pts[0])), int(float(pts[1]))))
                
                if len(points) == 4:
                    src_points = np.float32(points)
                    real_width, real_height = (l1 + l3) / 2.0, (l2 + l4) / 2.0
                    dst_points = np.float32([[0, 0], [real_width, 0], [real_width, real_height], [0, real_height]]) 
                    H, _ = cv2.findHomography(src_points, dst_points)
                    zones.append({'name': name, 'points': points, 'polygon': np.array(points, dtype=np.int32), 'homography_matrix': H})
                i += 5
            return zones
        except Exception as e:
            self.log(f"Error loading calibration: {e}")
            return []

    def run_analysis(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_run_dir = os.path.join(self.base_output_dir, f"Run_{timestamp}")
        os.makedirs(self.current_run_dir, exist_ok=True)
        
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        lookahead_frames = int(self.lookahead_s * fps)
        time_gap_frames = int(2.0 * fps) # กำหนดเวลาเฉียดชนที่ยอมรับได้คือ 2 วินาที (2.0 * fps)
        
        model = YOLO(self.model_path)
        byte_track = sv.ByteTrack(frame_rate=int(fps))
        
        ZONES = self.load_zone_from_txt()

        self.log("==================================================")
        self.log(f"📁 สร้างโฟลเดอร์สำหรับรอบนี้: {self.current_run_dir}")
        self.log("🔍 PHASE 1: Data Gathering (สแกนเก็บข้อมูลล่วงหน้า)")
        if ZONES: self.log(f"📍 ตรวจพบการโหลด Zone {len(ZONES)} โซน สำหรับคำนวณความเร็ว")
        self.log("==================================================")
        
        frame_idx = 0
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break
            frame_idx += 1
            results = model.predict(frame, classes=self.target_classes, verbose=False, conf=0.5, iou=0.45)[0]
            detections = sv.Detections.from_ultralytics(results)
            detections = byte_track.update_with_detections(detections)
            points = detections.get_anchors_coordinates(anchor=sv.Position.BOTTOM_CENTER).astype(int)
            
            for tid, cid, pt in zip(detections.tracker_id, detections.class_id, points):
                if tid is not None:
                    self.history_positions[tid][frame_idx] = (pt[0], pt[1])
                    self.history_classes[tid] = model.names[cid]
                    
            if frame_idx % 100 == 0:
                self.log(f"สแกนข้อมูล: เฟรม {frame_idx}/{total_frames} ({(frame_idx/total_frames)*100:.1f}%)")

        self.log("✅ PHASE 1 เสร็จสิ้น! เริ่ม PHASE 2: เรนเดอร์และวิเคราะห์จุดตัด...\n")
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0) 
        
        out_path = os.path.join(self.current_run_dir, "SF404_Result_Offline.mp4")
        video_writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        
        cv2.namedWindow("StopSense - Future Trajectory", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("StopSense - Future Trajectory", 1280, 720)

        frame_idx = 0
        risk_cooldown = {} 

        while cap.isOpened():
            success, frame = cap.read()
            if not success: break
            frame_idx += 1
            current_objects = [tid for tid, frames in self.history_positions.items() if frame_idx in frames]
            
            conflicting_tids = set()
            events_to_log = []

            # 1. แอบเช็ควิเคราะห์จุดตัดล่วงหน้า (เงื่อนไขใหม่: ห่างกันไม่เกิน 2 วิ ให้นับหมด)
            for i in range(len(current_objects)):
                for j in range(i + 1, len(current_objects)):
                    id_a, id_b = current_objects[i], current_objects[j]
                    conflict_found, conflict_type, min_distance, conflict_pt = False, "", float('inf'), None
                    
                    # หาเฟรมอนาคตทั้งหมดของรถ A (จำกัดแค่ใน lookahead)
                    future_f_a = [f for f in range(frame_idx, frame_idx + lookahead_frames) if f in self.history_positions[id_a]]
                    
                    for f_a in future_f_a:
                        pt_a = self.history_positions[id_a][f_a]
                        
                        # ให้รถ B เช็คในกรอบเวลา (เฟรมของ A - 2 วิ) ถึง (เฟรมของ A + 2 วิ)
                        f_b_start = max(frame_idx, f_a - time_gap_frames)
                        f_b_end = min(frame_idx + lookahead_frames, f_a + time_gap_frames)
                        
                        for f_b in range(f_b_start, f_b_end + 1):
                            if f_b in self.history_positions[id_b]:
                                pt_b = self.history_positions[id_b][f_b]
                                dist = self._euclidean_distance(pt_a, pt_b)
                                
                                if dist < min_distance:
                                    min_distance = dist
                                    conflict_pt = pt_a 
                                
                                if dist < self.proximity_px:
                                    if dist < 20.0:
                                        conflict_found, conflict_type = True, "CROSSING"
                                        break
                                    elif self.calc_parallel and conflict_type != "CROSSING": 
                                        conflict_found, conflict_type = True, "PROXIMITY"
                                        
                        if conflict_found and conflict_type == "CROSSING":
                            break # เจอเคสหนักสุด (ตัดกัน) แล้ว ให้ออกจากลูปเช็คของคู่นี้เลย
                    
                    if conflict_found:
                        conflicting_tids.add(id_a)
                        conflicting_tids.add(id_b)
                        pair_key = tuple(sorted([id_a, id_b]))
                        
                        if (frame_idx - risk_cooldown.get(pair_key, -999) > fps * 3): 
                            risk_cooldown[pair_key] = frame_idx
                            events_to_log.append({
                                'id_a': id_a, 'id_b': id_b,
                                'type': conflict_type, 'dist': min_distance, 'pt': conflict_pt
                            })

            # 2. วาดกรอบ Zone (ถ้ามี)
            for zone in ZONES:
                cv2.polylines(frame, [zone['polygon']], True, (0, 255, 255), 2)
                cx, cy = int(zone['polygon'][:, 0].mean()), int(zone['polygon'][:, 1].mean())
                cv2.putText(frame, zone['name'], (cx-40, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)

            # 3. วาดเส้นทางล่วงหน้า (ถ้าอยู่ในกลุ่มที่ชน/เฉียดใน 2 วิ เปลี่ยนเป็นสีแดง)
            for tid in current_objects:
                curr_pt = self.history_positions[tid][frame_idx]
                
                line_color = (0, 0, 255) if tid in conflicting_tids else (0, 255, 0)
                
                future_path = []
                for f in range(frame_idx, frame_idx + lookahead_frames, 3): 
                    if f in self.history_positions[tid]:
                        future_path.append(self.history_positions[tid][f])
                if len(future_path) > 1:
                    pts = np.array(future_path, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(frame, [pts], False, line_color, 2)
                    end_pt = future_path[-1]
                    cv2.circle(frame, end_pt, 5, line_color, -1)

                # คำนวณความเร็ว (เช็คว่าอยู่ใน Zone ไหม)
                for zone in ZONES:
                    if is_point_in_polygon(curr_pt, zone['polygon']):
                        past_frame = max(1, frame_idx - int(fps))
                        past_pt = self.history_positions[tid].get(past_frame)
                        
                        if not past_pt:
                            for f in range(frame_idx - 1, max(0, frame_idx - int(fps*1.5)), -1):
                                if f in self.history_positions[tid]:
                                    past_pt = self.history_positions[tid][f]
                                    past_frame = f
                                    break
                                    
                        if past_pt:
                            real_dist = calculate_real_distance(past_pt, curr_pt, zone['homography_matrix'])
                            if real_dist and real_dist > 0:
                                t_elapsed = (frame_idx - past_frame) / fps
                                if t_elapsed > 0:
                                    speed_kmh = (real_dist / t_elapsed) * 3.6
                                    if speed_kmh > 3.0: 
                                        cv2.putText(frame, f"{speed_kmh:.1f} km/h", (curr_pt[0]-30, curr_pt[1]-20), 
                                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        break

            # 4. วาดมาร์กเกอร์จุดชน และ บันทึกรูปลง Dashboard
            for ev in events_to_log:
                id_a, id_b = ev['id_a'], ev['id_b']
                c_type, min_dist, c_pt = ev['type'], ev['dist'], ev['pt']

                pt_a_curr, pt_b_curr = self.history_positions[id_a][frame_idx], self.history_positions[id_b][frame_idx]
                cv2.line(frame, pt_a_curr, pt_b_curr, (0, 0, 255), 2)
                
                if c_pt:
                    cv2.circle(frame, c_pt, 30, (0, 0, 255), 2)
                    cv2.putText(frame, f"{c_type} (Gap <= 2s)", (c_pt[0]-50, c_pt[1]-40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                timestamp_s = round(frame_idx / fps, 2)
                self.log(f"⚠️ [Time: {timestamp_s}s] Risk: {c_type} (Gap <= 2s) (ID:{id_a} & ID:{id_b})")
                
                cls_a = self.history_classes.get(id_a, "N/A")
                cls_b = self.history_classes.get(id_b, "N/A")

                self.conflict_logs.append({
                    "time": timestamp_s,
                    "type": c_type,
                    "obj_a": cls_a,
                    "obj_b": cls_b,
                    "distance": round(min_dist, 1),
                    "mode": "OFFLINE"
                })

                handle_risk_event(
                    tracker_id_a=id_a,
                    tracker_id_b=id_b,
                    class_name_a=cls_a,
                    class_name_b=cls_b,
                    event_type=f"FUTURE_{c_type}",
                    metric_value=min_dist,
                    zone_name="Offline_Scan",
                    save_log=True,
                    save_frame=True,
                    frame=frame.copy(),
                    output_dir=self.current_run_dir,
                    frame_number=frame_idx
                )

            cv2.imshow("StopSense - Future Trajectory", frame)
            video_writer.write(frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

        cap.release()
        video_writer.release()
        cv2.destroyAllWindows()
        
        log_path = os.path.join(self.current_run_dir, "conflict_log.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.conflict_logs, f, ensure_ascii=False, indent=4)

        self.log("\n✅ วิเคราะห์เสร็จสิ้น!")
        self.log(f"🎬 ผลลัพธ์ทั้งหมดถูกบันทึกไว้ใน: {self.current_run_dir}")