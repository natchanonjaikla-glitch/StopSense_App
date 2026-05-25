import cv2
import numpy as np
import time
import os
import json
import datetime # เพิ่มเข้ามาเพื่อดึงเวลา
from collections import defaultdict
from ultralytics import YOLO
import supervision as sv

class FutureTrajectoryAnalyzer:
    def __init__(self, video_path, model_path, output_dir="output", 
                 lookahead_s=3.0, proximity_px=80.0, target_classes=None,
                 log_callback=None, calc_parallel=True):
        self.video_path = video_path
        self.model_path = model_path
        self.base_output_dir = output_dir # โฟลเดอร์หลักที่ผู้ใช้เลือก
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

    def run_analysis(self):
        # 1. สร้างโฟลเดอร์ย่อยตามเวลาปัจจุบัน (เช่น Run_20260525_143000)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_run_dir = os.path.join(self.base_output_dir, f"Run_{timestamp}")
        os.makedirs(self.current_run_dir, exist_ok=True)
        
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        lookahead_frames = int(self.lookahead_s * fps)
        model = YOLO(self.model_path)
        byte_track = sv.ByteTrack(frame_rate=int(fps))

        self.log("==================================================")
        self.log(f"📁 สร้างโฟลเดอร์สำหรับรอบนี้: {self.current_run_dir}")
        self.log("🔍 PHASE 1: Data Gathering (สแกนเก็บข้อมูลล่วงหน้า)")
        self.log("==================================================")
        
        frame_idx = 0
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break
            frame_idx += 1
            results = model.predict(frame, classes=self.target_classes, verbose=False, conf=0.5)[0]
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
        
        # เซฟวิดีโอลงโฟลเดอร์ของรอบนี้
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
            
            for tid in current_objects:
                future_path = []
                for f in range(frame_idx, frame_idx + lookahead_frames, 3): 
                    if f in self.history_positions[tid]:
                        future_path.append(self.history_positions[tid][f])
                if len(future_path) > 1:
                    pts = np.array(future_path, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(frame, [pts], False, (0, 255, 0), 2)
                    end_pt = future_path[-1]
                    cv2.circle(frame, end_pt, 5, (0, 255, 0), -1)

            for i in range(len(current_objects)):
                for j in range(i + 1, len(current_objects)):
                    id_a, id_b = current_objects[i], current_objects[j]
                    conflict_found, conflict_type, min_distance, conflict_pt = False, "", float('inf'), None
                    
                    for f in range(frame_idx, frame_idx + lookahead_frames):
                        if f in self.history_positions[id_a] and f in self.history_positions[id_b]:
                            pt_a, pt_b = self.history_positions[id_a][f], self.history_positions[id_b][f]
                            dist = self._euclidean_distance(pt_a, pt_b)
                            if dist < min_distance:
                                min_distance, conflict_pt = dist, pt_a 
                            if dist < self.proximity_px:
                                if dist < 20.0:
                                    conflict_found, conflict_type = True, "CROSSING"
                                    break
                                elif self.calc_parallel:
                                    conflict_found, conflict_type = True, "PROXIMITY"
                                    break
                    
                    pair_key = tuple(sorted([id_a, id_b]))
                    if conflict_found and (frame_idx - risk_cooldown.get(pair_key, -999) > fps * 3): 
                        risk_cooldown[pair_key] = frame_idx
                        pt_a_curr, pt_b_curr = self.history_positions[id_a][frame_idx], self.history_positions[id_b][frame_idx]
                        cv2.line(frame, pt_a_curr, pt_b_curr, (0, 0, 255), 2)
                        if conflict_pt:
                            cv2.circle(frame, conflict_pt, 30, (0, 0, 255), 2)
                            cv2.putText(frame, conflict_type, (conflict_pt[0]-50, conflict_pt[1]-40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
                        timestamp_s = round(frame_idx / fps, 2)
                        self.log(f"⚠️ [Time: {timestamp_s}s] Risk: {conflict_type} (ID:{id_a} & ID:{id_b})")
                        self.conflict_logs.append({
                            "time": timestamp_s,
                            "type": conflict_type,
                            "obj_a": self.history_classes.get(id_a, "N/A"),
                            "obj_b": self.history_classes.get(id_b, "N/A"),
                            "distance": round(min_distance, 1),
                            "mode": "OFFLINE"
                        })

            cv2.imshow("StopSense - Future Trajectory", frame)
            video_writer.write(frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

        cap.release()
        video_writer.release()
        cv2.destroyAllWindows()
        
        # เซฟ Log ลงโฟลเดอร์ของรอบนี้
        log_path = os.path.join(self.current_run_dir, "conflict_log.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.conflict_logs, f, ensure_ascii=False, indent=4)

        self.log("\n✅ วิเคราะห์เสร็จสิ้น!")
        self.log(f"🎬 ผลลัพธ์ทั้งหมดถูกบันทึกไว้ใน: {self.current_run_dir}")