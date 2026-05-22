import cv2

def get_video_fps_cv2(video_path):
    """ดึงค่า FPS ของวิดีโอเพื่อนำไปคำนวณความเร็ว"""
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return 30.0 # คืนค่าเริ่มต้นป้องกัน Error

    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    
    # ถ้าดึงค่าไม่ได้ หรือได้เป็น 0 ให้ใช้ค่า 30 แทน
    return fps if fps > 0 else 30.0