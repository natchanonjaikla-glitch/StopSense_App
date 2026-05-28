import cv2
import threading
import os
import numpy as np
import time
import queue
import json
from datetime import datetime 
from collections import defaultdict, deque
from ultralytics import YOLO
import supervision as sv

from utils.file_manager import handle_risk_event

SHOW_FRAME_INFO = True

# ==================== Math Helpers ====================
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

def estimate_direction(track_points):
    if len(track_points) < 5: return None, None
    pts = [(p[0], p[1]) for p in track_points]
    total_vx, total_vy, total_w = 0.0, 0.0, 0.0
    for i in range(1, len(pts)):
        dx, dy, w = pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1], i
        total_vx += dx * w
        total_vy += dy * w
        total_w += w
    if total_w == 0: return None, None
    vx, vy = total_vx / total_w, total_vy / total_w
    norm = np.sqrt(vx**2 + vy**2)
    if norm < 1e-6: return None, None
    vx, vy = vx / norm, vy / norm
    
    overall_dx, overall_dy = float(pts[-1][0] - pts[0][0]), float(pts[-1][1] - pts[0][1])
    if np.sqrt(overall_dx**2 + overall_dy**2) > 1e-6 and (vx * overall_dx + vy * overall_dy < 0):
        vx, vy = -vx, -vy
    return float(np.degrees(np.arctan2(vy, vx))), (vx, vy, float(pts[-1][0]), float(pts[-1][1]))

def _get_real_direction_vector(direction_vector, homography_matrix, track_points):
    vx, vy, x0, y0 = direction_vector
    pt_base = transform_point((int(x0), int(y0)), homography_matrix)
    pt_tip  = transform_point((int(x0 + vx * 100), int(y0 + vy * 100)), homography_matrix)
    if pt_base is None or pt_tip is None: return None
    real_vx, real_vy = pt_tip[0] - pt_base[0], pt_tip[1] - pt_base[1]
    norm = np.sqrt(real_vx**2 + real_vy**2)
    if norm == 0: return None
    return real_vx / norm, real_vy / norm

def draw_trajectory_arrow(frame, point, direction_vector, speed_kmh, min_len=40, speed_mult=3.0):
    if direction_vector is None: return
    vx, vy, _, _ = direction_vector
    arrow_length = max(min_len, int(speed_kmh * speed_mult)) 
    future_point = (int(point[0] + vx * arrow_length), int(point[1] + vy * arrow_length))
    cv2.arrowedLine(frame, tuple(point), future_point, (255, 255, 0), 3, tipLength=0.2)

def _ray_segment_intersection_2d(ox, oy, dx, dy, px, py, ex, ey):
    sx, sy = ex - px, ey - py
    denom = dx * sy - dy * sx
    if abs(denom) < 1e-10: return None
    t = ((px - ox) * sy - (py - oy) * sx) / denom
    u = ((px - ox) * dy - (py - oy) * dx) / denom
    if t >= 0 and 0.0 <= u <= 1.0: return t, u
    return None

def compute_ttc(point_a, point_b, dir_vec_a, dir_vec_b, speed_a_mps, speed_b_mps, homography_matrix, track_points_a, track_points_b, ttc_threshold, arrival_gap, ttc_lookahead_s):
    if not all([homography_matrix is not None, dir_vec_a, dir_vec_b, speed_a_mps > 0 or speed_b_mps > 0]): return None
    real_a, real_b = transform_point(point_a, homography_matrix), transform_point(point_b, homography_matrix)
    if real_a is None or real_b is None: return None
    rdir_a, rdir_b = _get_real_direction_vector(dir_vec_a, homography_matrix, track_points_a), _get_real_direction_vector(dir_vec_b, homography_matrix, track_points_b)
    if not rdir_a or not rdir_b: return None
    
    eff_a, eff_b = max(speed_a_mps, 0.5), max(speed_b_mps, 0.5)
    result = _ray_segment_intersection_2d(real_a[0], real_a[1], rdir_a[0], rdir_a[1], real_b[0], real_b[1], real_b[0] + rdir_b[0] * eff_b * ttc_lookahead_s, real_b[1] + rdir_b[1] * eff_b * ttc_lookahead_s)
    
    if result is None: return None 
    t_a, _ = result
    cx, cy = real_a[0] + t_a * rdir_a[0], real_a[1] + t_a * rdir_a[1]
    
    ttc_a = float(np.hypot(cx - real_a[0], cy - real_a[1])) / eff_a
    ttc_b = float(np.hypot(cx - real_b[0], cy - real_b[1])) / eff_b
    
    if (ttc_a < ttc_threshold or ttc_b < ttc_threshold) and (abs(ttc_a - ttc_b) < arrival_gap):
        return ttc_a, ttc_b
    return None

# ==================== Core Class ====================
class VideoProcessor:
    def __init__(self, video_path, model_path, calibration_path, output_dir=None, target_classes=None, 
                 ttc_threshold=3.0, arrival_gap=1.5, ttc_lookahead_s=4.0, frame_skip=1, speed_comp=0.0,
                 arrow_min_len=40, arrow_speed_mult=3.0, conf_threshold=0.50): # [เพิ่มใหม่] พารามิเตอร์ conf_threshold
        self.video_path = video_path
        self.model_path = model_path
        self.calibration_path = calibration_path
        
        self.base_output_dir = output_dir if output_dir else "output" 
        self.output_dir = self.base_output_dir
        
        self.target_classes = target_classes if target_classes is not None else [0, 1, 2, 3, 5, 7]
        self.is_running = False
        self.cap = None
        self.frame_queue = queue.Queue(maxsize=30)
        self.reader_thread = None
        self.thread = None 
        
        self.ttc_threshold = float(ttc_threshold)
        self.arrival_gap = float(arrival_gap)
        self.ttc_lookahead_s = float(ttc_lookahead_s)
        self.frame_skip = int(frame_skip)
        self.speed_comp = float(speed_comp)
        self.conf_threshold = float(conf_threshold) # [เพิ่มใหม่] เก็บค่า Confidence ขีดเริ่มเปลี่ยน
        
        self.arrow_min_len = int(arrow_min_len)
        self.arrow_speed_mult = float(arrow_speed_mult)
        
        self.conflict_logs = []
        self.target_size = None

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self._run_analysis, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False

    def load_zone_from_txt(self, scale=1.0):
        zones = []
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
                    w = float(zone_info[1]) if len(zone_info) > 1 else 10.0
                    h = float(zone_info[2]) if len(zone_info) > 2 else 20.0
                    l1, l2, l3, l4 = w, h, w, h
                
                points = []
                for j in range(1, 5):
                    if i + j < len(lines):
                        pts = lines[i+j].split(',')
                        if len(pts) >= 2: 
                            px = int(float(pts[0]) * scale)
                            py = int(float(pts[1]) * scale)
                            points.append((px, py))
                
                if len(points) == 4:
                    src_points = np.float32(points)
                    real_width, real_height = (l1 + l3) / 2.0, (l2 + l4) / 2.0
                    dst_points = np.float32([[0, 0], [real_width, 0], [real_width, real_height], [0, real_height]]) 
                    H, _ = cv2.findHomography(src_points, dst_points)
                    zones.append({'name': name, 'points': points, 'polygon': np.array(points, dtype=np.int32), 'homography_matrix': H})
                i += 5
            return zones
        except Exception as e:
            print(f"Error loading calibration: {e}")
            return []

    def _read_frames(self):
        while self.is_running and self.cap.isOpened():
            if not self.frame_queue.full():
                success, frame = self.cap.read()
                if not success: break
                
                if self.target_size:
                    frame = cv2.resize(frame, self.target_size)
                    
                self.frame_queue.put(frame)
            else:
                time.sleep(0.01)

    def _run_analysis(self):
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            print("Error: ไม่สามารถเปิดไฟล์วิดีโอได้")
            self.stop()
            return

        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_original = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        
        scale_factor = 1.0
        if width > 1920:
            scale_factor = 1920.0 / width
            width = 1920
            height = int(height * scale_factor)
            self.target_size = (width, height)
            print(f"⚠️ ตรวจพบวิดีโอความละเอียดสูง (4K+) ย่อขนาดเหลือ 1080p เพื่อความรวดเร็ว (Scale: {scale_factor:.2f})")
        else:
            self.target_size = None

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder_name = f"Run_TTC_{timestamp_str}"
        self.output_dir = os.path.join(self.base_output_dir, run_folder_name)
        os.makedirs(self.output_dir, exist_ok=True)

        out_video_path = os.path.join(self.output_dir, "result_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(out_video_path, fourcc, fps_original, (width, height))

        ZONES = self.load_zone_from_txt(scale=scale_factor)

        self.reader_thread = threading.Thread(target=self._read_frames, daemon=True)
        self.reader_thread.start()
        
        model = YOLO(self.model_path)
        byte_track = sv.ByteTrack(frame_rate=int(fps_original))
        box_annotator = sv.BoxAnnotator(thickness=2)
        label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)
        
        speed_memory = defaultdict(lambda: deque(maxlen=5))
        direction_memory = defaultdict(lambda: deque(maxlen=60))
        object_in_zone = defaultdict(bool)
        last_speed = defaultdict(float)
        speed_history = defaultdict(list)
        cached_dir_vec = {}
        tracker_classes = {} 
        risk_cooldown = {}   
        
        frame_count = 0
        last_annotated_frame = None

        cv2.namedWindow("StopSense - YOLO Analysis", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("StopSense - YOLO Analysis", 1280, 720)

        print("\n" + "="*50)
        print("🚀 เริ่มต้นการประมวลผลวิดีโอ (StopSense AI)")
        print(f"📁 บันทึกข้อมูลรอบนี้ลงใน: {self.output_dir}")
        print("="*50)
        start_time = time.time()
        processed_frames_count = 0

        while self.is_running:
            if self.frame_queue.empty():
                if not self.reader_thread.is_alive(): break
                time.sleep(0.01)
                continue
                
            frame = self.frame_queue.get()
            frame_count += 1
            current_time_s = frame_count / fps_original
            
            if frame_count % max(1, self.frame_skip) != 0:
                if last_annotated_frame is not None:
                    video_writer.write(last_annotated_frame)
                    cv2.imshow("StopSense - YOLO Analysis", last_annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
                continue

            # === [อัปเดตบรรทัดนี้] ใช้ค่า self.conf_threshold เพื่อปรับความมั่นใจผ่านอินเตอร์เฟซได้โดยตรง ===
            results = model.predict(source=frame, classes=self.target_classes, stream=True, conf=self.conf_threshold, imgsz=640, verbose=False)
            result = next(results)

            detections = sv.Detections.from_ultralytics(result)
            detections = byte_track.update_with_detections(detections=detections)
            points = detections.get_anchors_coordinates(anchor=sv.Position.BOTTOM_CENTER).astype(int)
            
            for tid, cid in zip(detections.tracker_id, detections.class_id):
                if tid is not None:
                    tracker_classes[tid] = model.names[cid]

            annotated_frame = box_annotator.annotate(scene=frame.copy(), detections=detections)
            labels = [f"{model.names[class_id]} {confidence:0.2f}" for class_id, confidence in zip(detections.class_id, detections.confidence)]
            annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections, labels=labels)

            for zone in ZONES:
                cv2.polylines(annotated_frame, [zone['polygon']], True, (0, 255, 255), 2)
                cx, cy = int(zone['polygon'][:, 0].mean()), int(zone['polygon'][:, 1].mean())
                cv2.putText(annotated_frame, zone['name'], (cx-40, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)

            for i, (tracker_id, point) in enumerate(zip(detections.tracker_id, points)):
                if tracker_id is None: continue
                matched_zones = [(zi, z) for zi, z in enumerate(ZONES) if is_point_in_polygon(point, z['polygon'])]
                in_zone = len(matched_zones) > 0

                direction_memory[tracker_id].append((int(point[0]), int(point[1]), frame_count))
                
                track_history = list(direction_memory[tracker_id])
                if len(track_history) > 1:
                    pts_history = np.array([(p[0], p[1]) for p in track_history], np.int32).reshape((-1, 1, 2))
                    cv2.polylines(annotated_frame, [pts_history], isClosed=False, color=(0, 255, 255), thickness=2)

                _, dir_vec = estimate_direction(direction_memory[tracker_id])
                if dir_vec is not None:
                    cached_dir_vec[tracker_id] = dir_vec
                    draw_trajectory_arrow(annotated_frame, point, dir_vec, last_speed.get(tracker_id, 0), self.arrow_min_len, self.arrow_speed_mult)

                if in_zone:
                    for zone_idx, zone in matched_zones:
                        key = (tracker_id, zone_idx)
                        speed_memory[key].append(point)
                        object_in_zone[key] = True
                        if len(speed_memory[key]) >= 2:
                            real_dist = calculate_real_distance(speed_memory[key][0], speed_memory[key][-1], zone['homography_matrix'])
                            if real_dist and real_dist > 0:
                                t_elapsed = (len(speed_memory[key]) - 1) / fps_original
                                if t_elapsed > 0:
                                    speed_kmh = (real_dist / t_elapsed) * 3.6
                                    
                                    if speed_kmh < 3.0:
                                        speed_kmh = 0.0
                                    elif speed_kmh >= 15.0:
                                        speed_kmh += self.speed_comp
                                        if speed_kmh < 0: speed_kmh = 0.0 

                                    speed_history[tracker_id].append(speed_kmh)
                                    display_speed = float(np.median(speed_history[tracker_id])) if len(speed_history[tracker_id]) >= 3 else speed_kmh
                                    last_speed[tracker_id] = display_speed
                                    cv2.putText(annotated_frame, f"Speed: {display_speed:.1f} km/h", (point[0]-50, point[1]-40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                else:
                    if last_speed.get(tracker_id, 0) > 0:
                        cv2.putText(annotated_frame, f"Speed: {last_speed[tracker_id]:.1f} km/h", (point[0]-50, point[1]-40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

            tracker_ids = [tid for tid in detections.tracker_id if tid is not None]
            for ii in range(len(tracker_ids)):
                for jj in range(ii + 1, len(tracker_ids)):
                    id_a, id_b = tracker_ids[ii], tracker_ids[jj]
                    pt_a, pt_b = points[ii], points[jj]

                    if abs(pt_a[0] - pt_b[0]) > 1200 or abs(pt_a[1] - pt_b[1]) > 1200: continue

                    H = None
                    zone_name = "Unknown"
                    for zone in ZONES:
                        if is_point_in_polygon(pt_a, zone['polygon']) and is_point_in_polygon(pt_b, zone['polygon']):
                            H = zone['homography_matrix']
                            zone_name = zone['name']
                            break
                    if H is None: continue 

                    dir_a, dir_b = cached_dir_vec.get(id_a), cached_dir_vec.get(id_b)
                    speed_a_mps, speed_b_mps = last_speed.get(id_a, 0.0) / 3.6, last_speed.get(id_b, 0.0) / 3.6

                    ttc_result = compute_ttc(pt_a, pt_b, dir_a, dir_b, speed_a_mps, speed_b_mps, H, list(direction_memory[id_a]), list(direction_memory[id_b]),
                                             self.ttc_threshold, self.arrival_gap, self.ttc_lookahead_s)

                    if ttc_result is not None:
                        ttc_a, ttc_b = ttc_result
                        min_ttc = min(ttc_a, ttc_b)
                        
                        cv2.line(annotated_frame, tuple(pt_a), tuple(pt_b), (0, 0, 255), 2)
                        mid_x, mid_y = int((pt_a[0] + pt_b[0]) / 2), int((pt_a[1] + pt_b[1]) / 2)
                        cv2.putText(annotated_frame, f"RISK TTC: {min_ttc:.1f}s", (mid_x - 40, mid_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

                        pair_key = tuple(sorted([id_a, id_b]))
                        last_logged = risk_cooldown.get(pair_key, -9999)
                        
                        if frame_count - last_logged > fps_original * 5:
                            cls_a = tracker_classes.get(id_a, "Unknown")
                            cls_b = tracker_classes.get(id_b, "Unknown")
                            
                            handle_risk_event(
                                tracker_id_a=id_a, tracker_id_b=id_b,
                                class_name_a=cls_a, class_name_b=cls_b,
                                event_type="TTC_RISK", metric_value=min_ttc, zone_name=zone_name,
                                save_log=True, save_frame=True, frame=annotated_frame.copy(),
                                output_dir=self.output_dir, frame_number=frame_count
                            )
                            risk_cooldown[pair_key] = frame_count
                            
                            timestamp_s = round(frame_count / fps_original, 2)
                            speed_a_kmh = speed_a_mps * 3.6
                            speed_b_kmh = speed_b_mps * 3.6
                            self.conflict_logs.append({
                                "time": f"{timestamp_s} s",
                                "type": "TTC_RISK",
                                "zone": zone_name,
                                "ttc": f"{min_ttc:.2f} s",
                                "speed": f"{speed_a_kmh:.1f} / {speed_b_kmh:.1f} km/h"
                            })

            if SHOW_FRAME_INFO:
                minutes, seconds = int(current_time_s // 60), current_time_s % 60
                cv2.putText(annotated_frame, f"Frame: {frame_count} Time: {minutes:02d}:{seconds:05.2f}", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            video_writer.write(annotated_frame)
            last_annotated_frame = annotated_frame
            processed_frames_count += 1

            cv2.imshow("StopSense - YOLO Analysis", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

        self.is_running = False
        end_time = time.time()
        elapsed_time = end_time - start_time
        avg_fps = processed_frames_count / elapsed_time if elapsed_time > 0 else 0
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        summary_msg = (
            f"\n{'='*50}\n"
            f"✅ สรุปผลการทำงาน (StopSense AI) - {now_str}\n"
            f"ไฟล์วิดีโอ: {os.path.basename(self.video_path)}\n"
            f"โมเดล: {os.path.basename(self.model_path)}\n"
            f"⏱️ เวลาที่ใช้ไปทั้งหมด: {elapsed_time:.2f} วินาที\n"
            f"🎬 จำนวนเฟรมที่ประมวลผล: {processed_frames_count} เฟรม\n"
            f"⚡ ความเร็วเฉลี่ย: {avg_fps:.2f} FPS\n"
            f"{'='*50}\n"
        )

        print(summary_msg)
        print(f"📁 ไฟล์ผลลัพธ์ทั้งหมดถูกบันทึกไว้ที่โฟลเดอร์: {self.output_dir}\n")

        summary_file_path = os.path.join(self.output_dir, "processing_summary.txt")
        with open(summary_file_path, "a", encoding="utf-8") as f:
            f.write(summary_msg)
            
        log_json_path = os.path.join(self.output_dir, "conflict_log.json")
        with open(log_json_path, "w", encoding="utf-8") as f:
            json.dump(self.conflict_logs, f, ensure_ascii=False, indent=4)

        while not self.frame_queue.empty(): self.frame_queue.get()
        if self.cap: self.cap.release()
        video_writer.release()
        cv2.destroyAllWindows()