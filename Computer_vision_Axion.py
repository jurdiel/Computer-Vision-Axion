import math
import os
import socket
import struct
import threading
import time

import cv2
import numpy as np
import speech_recognition as sr
from mediapipe.python.solutions import drawing_utils as mp_drawing
from mediapipe.python.solutions import hands as mp_hands
from ultralytics import YOLO


os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp|buffer_size;1024000"
)

socket.setdefaulttimeout(8.0)

UDP_IP = "192.168.1.120"
UDP_PORT = 43893

CMD_HEARTBEAT  = 0x21040001
CMD_NAVIGATION = 0x21010C03
CMD_LINEAR     = 0x0140
CMD_ANGULAR    = 0x0141

CMD_STAND_SIT  = 0x21010202
CMD_HELLO      = 0x21010507
CMD_TWIST      = 0x21010204
VOICE_COMMAND  = 0x21010C0A

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def send(code):
    sock.sendto(
        struct.pack("<III", code, 0, 0),
        (UDP_IP, UDP_PORT)
    )


def send_speed(cmd_code, value):
    data = struct.pack("<III d", cmd_code, 8, 1, float(value))
    sock.sendto(data, (UDP_IP, UDP_PORT))


def send_voice_command(value):
    packet = struct.pack('<III', VOICE_COMMAND, value, 0)
    sock.sendto(packet, (UDP_IP, UDP_PORT))
    print(f"[SPEECH] Command suara terkirim: {value}")


linear_cmd = 0.0
angular_cmd = 0.0

follow_mode = False
stop_locked = False

lock = threading.Lock()

two_hand_start_time = None
one_hand_start_time = None
HOLD_TIME = 0.5

target_memory = []
MAX_MEMORY = 40
MEMORY_UPDATE_INTERVAL = 12
frame_counter = 0
hist_buffer = []

HIST_THRESHOLD_HIGH = 0.70  
HIST_THRESHOLD_LOW = 0.25   
target_lost_time = None
LOST_TIMEOUT = 1.5          

last_cmd_time = 0
COOLDOWN = 5

voice_trigger_time = 0.0

cap = cv2.VideoCapture("rtsp://192.168.1.120:8554/test")
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

latest_frame = None

kalman = cv2.KalmanFilter(4, 2)
kalman.measurementMatrix = np.array(
    [[1, 0, 0, 0], [0, 1, 0, 0]], np.float32
)
kalman.transitionMatrix = np.array([
    [1, 0, 1, 0],
    [0, 1, 0, 1],
    [0, 0, 1, 0],
    [0, 0, 0, 1]
], np.float32)
kalman.processNoiseCov = np.array([
    [1e-3, 0, 0, 0],
    [0, 1e-3, 0, 0],
    [0, 0, 1e-2, 0],
    [0, 0, 0, 1e-2]
], np.float32)
kalman.measurementNoiseCov = np.array(
    [[1e-1, 0], [0, 1e-1]], np.float32
)
kalman.statePre = np.array(
    [[0], [0], [0], [0]], np.float32
)
kalman_initialized = False


def heartbeat():
    while True:
        send(CMD_HEARTBEAT)
        send(CMD_NAVIGATION)
        time.sleep(0.1)


def control_loop():
    global linear_cmd, angular_cmd
    while True:
        with lock:
            send_speed(CMD_LINEAR, linear_cmd)
            send_speed(CMD_ANGULAR, angular_cmd)
        time.sleep(0.05)


def camera_thread():
    global latest_frame
    while True:
        for _ in range(2):
            cap.grab()
        ret, frame = cap.read()
        if ret:
            latest_frame = frame


def speech_recognition_thread():
    global voice_trigger_time
    
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 100 
    recognizer.dynamic_energy_threshold = False
    
    wake_words = ["hai robot", "halo robot", "robot", "hey robot"]
    wake_str = " / ".join(wake_words)

    with sr.Microphone(device_index=None) as source:
        print("[SPEECH] Menunggu 2 detik untuk inisialisasi Mic...")
        time.sleep(2)
        print("[SPEECH] Mempelajari noise latar belakang...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print(
            f"\n[SPEECH] TELINGA AKTIF! Panggil menggunakan: '{wake_str}'\n"
        )

        while True:
            try:
                audio_wake = recognizer.listen(
                    source, timeout=3, phrase_time_limit=3
                )
                text_wake = recognizer.recognize_google(
                    audio_wake, language='id-ID'
                ).strip().lower()
                
                if any(w in text_wake for w in wake_words):
                    print("\n" + "=" * 40)
                    print(
                        "ROBOT MENDENGAR: 'Ya! Silakan beri perintah...'"
                    )
                    print("=" * 40)
                    
                    try:
                        audio_cmd = recognizer.listen(
                            source, timeout=5, phrase_time_limit=5
                        )
                        text_cmd = recognizer.recognize_google(
                            audio_cmd, language='id-ID'
                        ).strip().lower()
                        print(f"[SPEECH] Perintah ditangkap: {text_cmd}")

                        if "ikuti saya" in text_cmd:
                            print(
                                "=> [SUARA] Aksi: Simulasi angkat tangan..."
                            )
                            voice_trigger_time = time.time()
                            
                        elif "berdiri" in text_cmd:
                            print("=> [SUARA] Aksi: Robot berdiri")
                            send_voice_command(1)
                            time.sleep(3)
                            send_voice_command(0)
                            
                        elif "duduk" in text_cmd:
                            print("=> [SUARA] Aksi: Robot duduk")
                            send_voice_command(2)
                            time.sleep(3)
                            send_voice_command(0)
                            
                        elif "halo" in text_cmd or "hallo" in text_cmd:
                            print("=> [SUARA] Aksi: Robot hello")
                            send_voice_command(22)
                            time.sleep(4) 
                            send_voice_command(1)
                            time.sleep(2)
                            send_voice_command(0) 
                        else:
                            print("=> [SUARA] Perintah tidak dikenali.")
                            
                    except sr.WaitTimeoutError:
                        print(
                            "Robot: 'Tidak ada perintah terdengar. "
                            "Kembali tidur...'"
                        )
                    except sr.UnknownValueError:
                        print(
                            "Robot: 'Suara perintah tidak jelas. "
                            "Kembali tidur...'"
                        )
            
            except (
                sr.WaitTimeoutError,
                sr.UnknownValueError,
                socket.timeout
            ):
                pass 
            except Exception:
                pass


threading.Thread(target=heartbeat, daemon=True).start()
threading.Thread(target=control_loop, daemon=True).start()
threading.Thread(target=camera_thread, daemon=True).start()
threading.Thread(target=speech_recognition_thread, daemon=True).start()

model = YOLO("yolov8n-pose.pt")

mp_hands_detector = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

kp_ang = 0.002
MAX_LIN = 0.6
MAX_ANG = 0.5
FRAME_SIZE = 520
STOP_THRESHOLD = FRAME_SIZE * (1 / 3)
prev_error = 0

print("SYSTEM READY")


def extract_torso_histogram(frame_img, person_kp):
    ls, rs = person_kp[5], person_kp[6]
    lh, rh = person_kp[11], person_kp[12]
    lk, rk = person_kp[13], person_kp[14]
    la, ra = person_kp[15], person_kp[16]

    center_x = (ls[0] + rs[0] + lh[0] + rh[0]) / 4
    shoulder_width = abs(ls[0] - rs[0])
    width = shoulder_width * 0.6 

    x_min = int(max(0, center_x - (width / 2)))
    x_max = int(min(FRAME_SIZE, center_x + (width / 2)))
    y_min = int(max(0, min(ls[1], rs[1]) - 5))
    ankle_y = max(la[1], ra[1])

    if ankle_y <= 0:
        ankle_y = max(lk[1], rk[1])
    if ankle_y <= 0:
        ankle_y = max(lh[1], rh[1]) + 60

    y_max = int(min(FRAME_SIZE, ankle_y))

    if x_max <= x_min or y_max <= y_min:
        return None

    person_crop = frame_img[y_min:y_max, x_min:x_max]
    hsv = cv2.cvtColor(person_crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    return hist


def compare_with_memory(current_hist):
    if len(target_memory) == 0:
        return -1
    scores = []
    for memory_hist in target_memory:
        score = cv2.compareHist(
            memory_hist, current_hist, cv2.HISTCMP_CORREL
        )
        scores.append(score)
    return max(scores)


def update_memory(new_hist):
    global target_memory
    if new_hist is None:
        return
    target_memory.append(new_hist.copy())
    if len(target_memory) > MAX_MEMORY:
        target_memory.pop(0)


while True:
    frame = latest_frame
    if frame is None:
        continue

    frame_counter += 1
    h, w, _ = frame.shape
    frame = frame[:, w // 4:3 * w // 4]
    frame = cv2.resize(frame, (FRAME_SIZE, FRAME_SIZE))
    clean_frame = frame.copy()

    results = model(frame, imgsz=224, verbose=False)
    annotated = results[0].plot()
    keypoints = results[0].keypoints.xy

    if keypoints is None or len(keypoints) == 0:
        with lock:
            if follow_mode and not stop_locked:
                linear_cmd = 0
                angular_cmd = 0.2
                print("SEARCH MODE - MENCARI TARGET")
            else:
                linear_cmd = 0
                angular_cmd = 0
        cv2.imshow("FOLLOW", annotated)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    best_person = None
    best_match_score = -1
    best_hist = None

    if follow_mode:
        for person_kp in keypoints:
            if len(person_kp) < 13:
                continue
            if person_kp[5][0] == 0:
                continue

            current_hist = extract_torso_histogram(clean_frame, person_kp)
            if current_hist is None:
                continue

            score = compare_with_memory(current_hist)
            if score > best_match_score:
                best_match_score = score
                best_person = person_kp
                best_hist = current_hist

    else:
        for person_kp in keypoints:
            if len(person_kp) < 13:
                continue
            if person_kp[5][0] == 0:
                continue

            lw, rw = person_kp[9], person_kp[10]
            ls, rs = person_kp[5], person_kp[6]

            left_up = lw[1] < ls[1]
            right_up = rw[1] < rs[1]
            hands_up = int(left_up) + int(right_up)

            if time.time() - voice_trigger_time < 1.5:
                hands_up = 1

            if hands_up == 1:
                best_person = person_kp
                best_hist = extract_torso_histogram(clean_frame, person_kp)
                break

    if best_person is None:
        if not follow_mode:
            with lock:
                linear_cmd = 0
                angular_cmd = 0
            one_hand_start_time = None
            hist_buffer = []
            cv2.putText(
                annotated,
                "STANDBY - TUNGGU TANGAN / SUARA",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2
            )
        cv2.imshow("FOLLOW", annotated)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    current_time = time.time()

    if follow_mode and best_person is not None:
        if best_match_score < HIST_THRESHOLD_LOW:
            if target_lost_time is None:
                target_lost_time = current_time
            elif current_time - target_lost_time > LOST_TIMEOUT:
                with lock:
                    linear_cmd = 0
                    angular_cmd = 0.2
                print(
                    f"Target hilang permanen! "
                    f"(Skor: {best_match_score:.2f} < "
                    f"{HIST_THRESHOLD_LOW})"
                )
                cv2.imshow("FOLLOW", annotated)
                cv2.waitKey(1)
                continue
            else:
                with lock:
                    linear_cmd = 0
                    angular_cmd = 0
                print(
                    f"Toleransi hilang... Tunggu sebentar "
                    f"(Skor: {best_match_score:.2f})"
                )
                cv2.imshow("FOLLOW", annotated)
                cv2.waitKey(1)
                continue
        else:
            target_lost_time = None
            if (best_match_score > HIST_THRESHOLD_HIGH
                    and best_hist is not None
                    and frame_counter % MEMORY_UPDATE_INTERVAL == 0):
                update_memory(best_hist)

    person = best_person
    lw, rw = person[9], person[10]
    ls, rs = person[5], person[6]
    left_up = lw[1] < ls[1]
    right_up = rw[1] < rs[1]
    hands_up = int(left_up) + int(right_up)

    if time.time() - voice_trigger_time < 1.5:
        hands_up = 1

    if hands_up == 2:
        one_hand_start_time = None
        hist_buffer = []
        if two_hand_start_time is None:
            two_hand_start_time = current_time
        elif current_time - two_hand_start_time > HOLD_TIME:
            follow_mode = False
            stop_locked = False
            target_memory = []
            kalman_initialized = False
            print(">>> RESET <<<")
    else:
        two_hand_start_time = None

    if hands_up == 1:
        if one_hand_start_time is None:
            one_hand_start_time = current_time
            hist_buffer = []
        elif current_time - one_hand_start_time <= HOLD_TIME:
            if best_hist is not None:
                hist_buffer.append(best_hist)
        elif current_time - one_hand_start_time > HOLD_TIME and not follow_mode:
            if len(hist_buffer) > 0:
                follow_mode = True
                stop_locked = False
                target_memory = []
                for hist in hist_buffer:
                    update_memory(hist)
                target_lost_time = None
                kalman_initialized = False
                print(f">>> START FOLLOW <<< MEMORY={len(target_memory)}")
            else:
                print("GAGAL LOCK TARGET")
                one_hand_start_time = None
    else:
        one_hand_start_time = None
        hist_buffer = []

    center_x = FRAME_SIZE // 2
    
    ls, rs = person[5], person[6]
    lh, rh = person[11], person[12]

    raw_x = int((ls[0] + rs[0]) / 2)
    shoulder_y = (ls[1] + rs[1]) / 2
    hip_y_raw = (lh[1] + rh[1]) / 2
    
    raw_y = int((shoulder_y + hip_y_raw) / 2) 

    measurement = np.array([[np.float32(raw_x)], [np.float32(raw_y)]])

    if not kalman_initialized:
        kalman.statePost = np.array(
            [[np.float32(raw_x)], [np.float32(raw_y)], [0], [0]],
            np.float32
        )
        kalman_initialized = True

    kalman.correct(measurement)
    prediction = kalman.predict()
    person_center_x = int(prediction[0][0])
    
    chest_y = int(prediction[1][0])

    error_x = person_center_x - center_x
    error_x = (0.7 * prev_error + 0.3 * error_x)
    prev_error = error_x

    with lock:
        if follow_mode and not stop_locked:
            angular = np.clip(error_x * kp_ang, -MAX_ANG, MAX_ANG)
            
            linear = (
                (chest_y - STOP_THRESHOLD) / (FRAME_SIZE - STOP_THRESHOLD)
            )
            linear = np.clip(linear, 0, 1)
            
            linear = (linear ** 0.5) * MAX_LIN

            if abs(error_x) > 70:
                linear = 0
            
            if chest_y <= STOP_THRESHOLD:
                stop_locked = True
                print(">>> STOP <<<")

            linear_cmd = linear
            angular_cmd = angular

        elif stop_locked:
            linear_cmd = 0
            angular_cmd = 0
        else:
            linear_cmd = 0
            angular_cmd = 0

    if stop_locked:
        rgb = cv2.cvtColor(clean_frame, cv2.COLOR_BGR2RGB)
        res = mp_hands_detector.process(rgb)

        total_fingers = None

        if res.multi_hand_landmarks:
            for hand_handedness, hand_landmarks in zip(
                    res.multi_handedness, res.multi_hand_landmarks):
                raw_label = hand_handedness.classification[0].label
                actual_label = 'Right' if raw_label == 'Left' else 'Left'

                if actual_label == 'Right':
                    mp_drawing.draw_landmarks(
                        annotated,
                        hand_landmarks,
                        mp_hands.HAND_CONNECTIONS
                    )

                    fingers = []
                    
                    thumb_tip_dist = math.hypot(
                        hand_landmarks.landmark[4].x 
                        - hand_landmarks.landmark[17].x, 
                        hand_landmarks.landmark[4].y 
                        - hand_landmarks.landmark[17].y
                    )
                    thumb_mcp_dist = math.hypot(
                        hand_landmarks.landmark[3].x 
                        - hand_landmarks.landmark[17].x, 
                        hand_landmarks.landmark[3].y 
                        - hand_landmarks.landmark[17].y
                    )
                    fingers.append(
                        1 if thumb_tip_dist > thumb_mcp_dist else 0
                    )

                    for tip, pip in zip([8, 12, 16, 20], [6, 10, 14, 18]):
                        tip_dist = math.hypot(
                            hand_landmarks.landmark[tip].x 
                            - hand_landmarks.landmark[0].x, 
                            hand_landmarks.landmark[tip].y 
                            - hand_landmarks.landmark[0].y
                        )
                        pip_dist = math.hypot(
                            hand_landmarks.landmark[pip].x 
                            - hand_landmarks.landmark[0].x, 
                            hand_landmarks.landmark[pip].y 
                            - hand_landmarks.landmark[0].y
                        )
                        fingers.append(1 if tip_dist > pip_dist else 0)

                    total_fingers = fingers.count(1)

                    cv2.putText(
                        annotated,
                        f"Tangan Kanan: {total_fingers}",
                        (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 0),
                        2
                    )
                    
                    break

        if (total_fingers is not None 
                and (current_time - last_cmd_time > COOLDOWN)):
            if total_fingers == 0:
                print("Toggle Stand/Sit")
                for _ in range(5):
                    send(CMD_STAND_SIT)
                    time.sleep(0.05)
                last_cmd_time = current_time

            elif total_fingers == 3:
                print("TWIST")
                for _ in range(5):
                    send(CMD_TWIST)
                    time.sleep(0.05)
                last_cmd_time = current_time

            elif total_fingers == 5:
                print("HELLO")
                for _ in range(5):
                    send(CMD_HELLO)
                    time.sleep(0.05)
                last_cmd_time = current_time

    cv2.line(
        annotated,
        (center_x, 0),
        (center_x, FRAME_SIZE),
        (255, 0, 0),
        2
    )
    cv2.line(
        annotated,
        (0, int(STOP_THRESHOLD)),
        (FRAME_SIZE, int(STOP_THRESHOLD)),
        (0, 255, 255),
        2
    )
    
    cv2.circle(
        annotated,
        (person_center_x, int(chest_y)),
        8,
        (0, 0, 255),
        -1
    )

    status_match = (
        f"Match:{best_match_score:.2f}" 
        if best_match_score != -1 else ""
    )
    cv2.putText(
        annotated,
        f"MEM:{len(target_memory)}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    cv2.putText(
        annotated,
        f"Follow={follow_mode}",
        (10, FRAME_SIZE - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2
    )

    cv2.imshow("FOLLOW", annotated)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
