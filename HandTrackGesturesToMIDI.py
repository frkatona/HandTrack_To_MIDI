import argparse
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
import mido
from mido import Message


DEFAULT_MODEL_PATH = Path(__file__).with_name("gesture_recognizer.task")
GESTURE_CC_MAP = {
    "Open_Palm": 2,
    "Closed_Fist": 3,
    "Pointing_Up": 4,
    "Victory": 5,
    "ILoveYou": 6,
    "Thumb_Up": 7,
    "Thumb_Down": 8,
}
DECAY_SECONDS = 2.0
DECAY_RATE = 127.0 / DECAY_SECONDS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hand gesture recognition to MIDI CC.")
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


def map_palm_height(y_coordinate: float) -> int:
    normalized = max(0.0, min(1.0, y_coordinate))
    return round((1.0 - normalized) * 127)


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
    )
    midi_channel = args.channel - 1
    cc_values = {control: 0.0 for control in (1, *GESTURE_CC_MAP.values())}
    last_sent = {control: 0 for control in cc_values}
    previous_time = time.perf_counter()
    start_time = previous_time
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

                current_time = time.perf_counter()
                elapsed = current_time - previous_time
                previous_time = current_time

                current_gestures = []
                for hand_gestures in result.gestures:
                    if hand_gestures:
                        current_gestures.append(hand_gestures[0].category_name)

                for gesture, control in GESTURE_CC_MAP.items():
                    if gesture in current_gestures:
                        cc_values[control] = 127.0
                    else:
                        cc_values[control] = max(
                            0.0, cc_values[control] - DECAY_RATE * elapsed
                        )

                if result.hand_landmarks:
                    cc_values[1] = float(map_palm_height(result.hand_landmarks[0][0].y))

                for control, value in cc_values.items():
                    rounded_value = round(value)
                    if rounded_value != last_sent[control]:
                        midi_out.send(
                            Message(
                                "control_change",
                                channel=midi_channel,
                                control=control,
                                value=rounded_value,
                            )
                        )
                        last_sent[control] = rounded_value

                gesture_text = ", ".join(current_gestures) or "None"
                cv2.putText(
                    frame,
                    f"Gestures: {gesture_text}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("Hand Gesture MIDI", frame)

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
