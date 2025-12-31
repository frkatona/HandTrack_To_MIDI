import cv2
import mediapipe as mp
import numpy as np
import mido
from mido import Message
import time

# MediaPipe Task imports
BaseOptions = mp.tasks.BaseOptions
GestureRecognizer = mp.tasks.vision.GestureRecognizer
GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Initialize MIDI
print("Available MIDI output ports:")
print(mido.get_output_names())

try:
    # Using 'PythonMIDI 1' as discovered in previous step
    midi_out = mido.open_output('PythonMIDI 1')
except IOError:
    print("MIDI output port 'PythonMIDI 1' not found. Please check the port name.")
    exit()

# Gesture to CC mapping
GESTURE_CC_MAP = {
    'Open_Palm': 2,
    'Closed_Fist': 3,
    'Pointing_Up': 4,
    'Victory': 5,
    'ILoveYou': 6,
    'Thumb_Up': 7,
    'Thumb_Down': 8
}

# State for decay logic
cc_values = {cc: 0.0 for cc in GESTURE_CC_MAP.values()}
last_cc_sent = {cc: 0 for cc in GESTURE_CC_MAP.values()}
cc_values[1] = 0.0 # For palm height
last_cc_sent[1] = 0

DECAY_RATE = 127.0 / 2.0  # Units per second (127 over 2 seconds)
last_time = time.time()

# Setup Gesture Recognizer
options = GestureRecognizerOptions(
    base_options=BaseOptions(model_asset_path='gesture_recognizer.task'),
    running_mode=VisionRunningMode.VIDEO
)

# Initialize webcam
cap = cv2.VideoCapture(0)

with GestureRecognizer.create_from_options(options) as recognizer:
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Process frame
        timestamp_ms = int(time.time() * 1000)
        result = recognizer.recognize_for_video(mp_image, timestamp_ms)

        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time

        # Update decay for all gesture CCs
        current_gestures = []
        if result.gestures:
            # We assume one hand for simplicity, matching original script
            for hand_gestures in result.gestures:
                if hand_gestures:
                    top_gesture = hand_gestures[0].category_name
                    current_gestures.append(top_gesture)

        # Update CC values based on detection and decay
        for gesture, cc in GESTURE_CC_MAP.items():
            if gesture in current_gestures:
                cc_values[cc] = 127.0
            else:
                cc_values[cc] = max(0.0, cc_values[cc] - (DECAY_RATE * dt))

        # Handle palm height mapping (CC 1)
        if result.hand_landmarks:
            # HandLandmark.WRIST is 0
            wrist = result.hand_landmarks[0][0]
            palm_height_cc = int(np.interp(wrist.y, [0.0, 1.0], [127, 0]))
            cc_values[1] = float(palm_height_cc)
            
            # Optional: Draw landmarks
            # (Skipping full drawing utility to keep it lean, but could be added)

        # Send MIDI messages if value changed significantly
        for cc, val in cc_values.items():
            int_val = int(round(val))
            if int_val != last_cc_sent[cc]:
                midi_out.send(Message('control_change', channel=1, control=cc, value=int_val))
                last_cc_sent[cc] = int_val

        # UI Overlay
        cv2.putText(frame, f"Gestures: {', '.join(current_gestures)}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        cv2.imshow('Hand Gesture MIDI', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()
midi_out.close()
