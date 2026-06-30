import argparse
import math
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
import mido
from mido import Message


DEFAULT_MODEL_PATH = Path(__file__).with_name("gesture_recognizer.task")
FINGER_TIP_INDICES = (8, 12, 16, 20, 4)
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)
TRACK_COLORS = (
    (124, 124, 50),
    (200, 50, 0),
    (50, 200, 0),
    (0, 50, 200),
    (255, 150, 20),
    (200, 100, 255),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hand tracking to MIDI CC.")
    parser.add_argument("--port", default="PythonMIDI 1", help="MIDI output port name")
    parser.add_argument(
        "--channel",
        type=int,
        choices=range(1, 17),
        default=1,
        metavar="1-16",
        help="MIDI channel (default: 1)",
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera device index")
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help="Path to the MediaPipe gesture recognizer model",
    )
    return parser.parse_args()


def map_to_midi(value: float, input_min: float, input_max: float, invert: bool = False) -> int:
    normalized = (value - input_min) / (input_max - input_min)
    normalized = max(0.0, min(1.0, normalized))
    if invert:
        normalized = 1.0 - normalized
    return round(normalized * 127)


def finger_closedness(wrist, finger_tip) -> int:
    distance = math.hypot(wrist.x - finger_tip.x, wrist.y - finger_tip.y)
    return map_to_midi(distance, 0.0, 0.5, invert=True)


def draw_hand(frame, landmarks) -> None:
    height, width = frame.shape[:2]
    points = [(round(point.x * width), round(point.y * height)) for point in landmarks]

    for start, end in HAND_CONNECTIONS:
        cv2.line(frame, points[start], points[end], (180, 180, 180), 2)

    for index, color in zip((0, *FINGER_TIP_INDICES), TRACK_COLORS):
        cv2.circle(frame, points[index], 10, color, -1)


def open_midi_output(port_name: str):
    try:
        midi_out = mido.open_output(port_name)
    except (OSError, RuntimeError) as error:
        try:
            available = mido.get_output_names()
        except (OSError, RuntimeError):
            available = []
        ports = ", ".join(available) if available else "none"
        raise RuntimeError(
            f"MIDI output port '{port_name}' could not be opened. Available ports: {ports}"
        ) from error

    print(f"Opened MIDI output port: {port_name}")
    return midi_out


def run(args: argparse.Namespace) -> int:
    model_path = args.model.expanduser().resolve()
    if not model_path.is_file():
        print(f"Model file not found: {model_path}", file=sys.stderr)
        return 1

    try:
        midi_out = open_midi_output(args.port)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        print(f"Camera {args.camera} could not be opened.", file=sys.stderr)
        midi_out.close()
        return 1

    options = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.7,
        min_tracking_confidence=0.7,
    )
    midi_channel = args.channel - 1
    last_sent = {}
    start_time = time.perf_counter()
    last_timestamp_ms = -1

    try:
        with mp.tasks.vision.GestureRecognizer.create_from_options(options) as recognizer:
            while camera.isOpened():
                success, frame = camera.read()
                if not success:
                    print("Camera stopped returning frames.", file=sys.stderr)
                    return 1

                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                timestamp_ms = max(
                    last_timestamp_ms + 1,
                    int((time.perf_counter() - start_time) * 1000),
                )
                last_timestamp_ms = timestamp_ms
                result = recognizer.recognize_for_video(mp_image, timestamp_ms)

                if result.hand_landmarks:
                    landmarks = result.hand_landmarks[0]
                    wrist = landmarks[0]
                    values = {
                        1: map_to_midi(wrist.y, 0.0, 1.0, invert=True),
                        **{
                            control: finger_closedness(wrist, landmarks[index])
                            for control, index in enumerate(FINGER_TIP_INDICES, start=2)
                        },
                    }

                    for control, value in values.items():
                        if last_sent.get(control) != value:
                            midi_out.send(
                                Message(
                                    "control_change",
                                    channel=midi_channel,
                                    control=control,
                                    value=value,
                                )
                            )
                            last_sent[control] = value

                    draw_hand(frame, landmarks)

                cv2.imshow("Hand Tracking MIDI", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    return 0
    finally:
        camera.release()
        cv2.destroyAllWindows()
        midi_out.close()

    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
