import cv2
import mediapipe as mp
import numpy as np
import mido
from mido import Message

# init track/draw module
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

print("Available MIDI output ports:")
print(mido.get_output_names())

try:
    midi_out = mido.open_output('PythonMIDI 2')
except IOError:
    print("MIDI output port 'PythonMIDI' not found. Please check the port name.")
    exit()

# init webcam feed
cap = cv2.VideoCapture(0)
with mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7) as hands:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        # draw landmarks and process MIDI
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                # extract key landmarks for MIDI CC mapping
                wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
                index_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                middle_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
                ring_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_TIP]
                pinky_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_TIP]
                thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]

                # color parameterized locations
                track_locations = [wrist, index_finger_tip, middle_finger_tip, ring_finger_tip, pinky_finger_tip, thumb_tip]
                colors = [(124, 124, 50), (200, 50, 0), (50, 200, 0), (0, 50, 200), (255, 150, 20), (200, 100, 255)]  # BGR colors

                for tip, color in zip(track_locations, colors):
                    cv2.circle(frame, (int(tip.x * frame.shape[1]), int(tip.y * frame.shape[0])), 10, color, -1)

                # Calculate height of palm (y-coordinate of wrist)
                palm_height = wrist.y

                # Normalize palm height to a value between 0 and 127 for MIDI CC
                palm_height_cc = int(np.interp(palm_height, [0.0, 1.0], [127, 0]))

                # palm height CC (channel 1, CC 1)
                midi_out.send(Message('control_change', control=1, value=palm_height_cc))

                # calculate finger closedness
                def calculate_closedness(finger_tip):
                    distance = np.linalg.norm(np.array([wrist.x, wrist.y]) - np.array([finger_tip.x, finger_tip.y]))
                    return int(np.interp(distance, [0.0, 0.5], [127, 0]))

                # calculate closedness 
                index_closedness = calculate_closedness(index_finger_tip)
                middle_closedness = calculate_closedness(middle_finger_tip)
                ring_closedness = calculate_closedness(ring_finger_tip)
                pinky_closedness = calculate_closedness(pinky_finger_tip)
                thumb_closedness = calculate_closedness(thumb_tip)

                # send midi (channel 1, CC 2 through 6)
                midi_out.send(Message('control_change', control=2, value=index_closedness))
                midi_out.send(Message('control_change', control=3, value=middle_closedness))
                midi_out.send(Message('control_change', control=4, value=ring_closedness))
                midi_out.send(Message('control_change', control=5, value=pinky_closedness))
                midi_out.send(Message('control_change', control=6, value=thumb_closedness))

        # display frame
        cv2.imshow('Hand Tracking', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'): # exit with 'q'
            break

cap.release()
cv2.destroyAllWindows()
midi_out.close()
