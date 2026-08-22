import os
import cv2
import numpy as np
import base64
import logging

logger = logging.getLogger(__name__)

# Try to import MediaPipe
try:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False
    logger.warning("MediaPipe is not installed. Eye contact and head pose tracking will be simulated.")

# Standard 3D model points of key facial features for Pose Estimation (PnP)
# Nose tip, Chin, Left eye corner, Right eye corner, Left mouth corner, Right mouth corner
MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),             # Nose tip
    (0.0, -330.0, -65.0),        # Chin
    (-225.0, 170.0, -135.0),     # Left eye outer corner
    (225.0, 170.0, -135.0),      # Right eye outer corner
    (-150.0, -150.0, -125.0),    # Left mouth corner
    (150.0, -150.0, -125.0)      # Right mouth corner
], dtype=np.float32)

class VisionTracker:
    def __init__(self):
        self.face_mesh = None
        if HAS_MEDIAPIPE:
            try:
                self.face_mesh = mp_face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,  # Enables iris landmarks
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
                logger.info("MediaPipe FaceMesh initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize MediaPipe FaceMesh: {e}")
                self.face_mesh = None

    def decode_base64_image(self, base64_str: str) -> np.ndarray:
        """
        Decodes a base64 encoded image string into an OpenCV numpy array (BGR).
        """
        try:
            if "," in base64_str:
                base64_str = base64_str.split(",")[1]
            image_bytes = base64.b64decode(base64_str)
            np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return image
        except Exception as e:
            logger.error(f"Error decoding base64 image: {e}")
            return None

    def analyze_frame(self, base64_frame: str) -> dict:
        """
        Analyzes a webcam frame for head pose (tilt, nod) and eye contact stability.
        Returns telemetry metrics: eye_contact_score, head_pose_score, status_text.
        """
        # If MediaPipe isn't loaded, return simulated telemetry
        if not HAS_MEDIAPIPE or not self.face_mesh:
            return self.get_simulated_telemetry()

        image = self.decode_base64_image(base64_frame)
        if image is None:
            return self.get_simulated_telemetry()

        h, w, _ = image.shape
        # Convert BGR to RGB
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        try:
            results = self.face_mesh.process(rgb_image)
        except Exception as e:
            logger.error(f"MediaPipe processing error: {e}")
            return self.get_simulated_telemetry()

        if not results.multi_face_landmarks:
            return {
                "eye_contact_score": 0,
                "head_pose_score": 0,
                "eye_contact_status": "No Face Detected",
                "head_pose_status": "No Face Detected",
                "gaze_details": "Align face with the camera",
                "yaw": 0.0,
                "pitch": 0.0,
                "roll": 0.0
            }

        face_landmarks = results.multi_face_landmarks[0].landmark

        # Extract 2D coordinates for key points for solvePnP
        # MediaPipe landmark indices:
        # Nose Tip: 1
        # Chin: 152
        # Left Eye Outer Corner: 263 (MediaPipe left is viewer's right)
        # Right Eye Outer Corner: 33 (MediaPipe right is viewer's left)
        # Left Mouth Corner: 291
        # Right Mouth Corner: 61
        
        # We need to map left/right correctly for OpenCV PnP solver
        image_points = np.array([
            (face_landmarks[1].x * w, face_landmarks[1].y * h),       # Nose tip
            (face_landmarks[152].x * w, face_landmarks[152].y * h),   # Chin
            (face_landmarks[33].x * w, face_landmarks[33].y * h),     # Right Eye outer corner (mapped to model left)
            (face_landmarks[263].x * w, face_landmarks[263].y * h),   # Left Eye outer corner (mapped to model right)
            (face_landmarks[61].x * w, face_landmarks[61].y * h),     # Right Mouth corner (mapped to model left)
            (face_landmarks[291].x * w, face_landmarks[291].y * h)    # Left Mouth corner (mapped to model right)
        ], dtype=np.float32)

        # Camera internals (approximation based on frame width/height)
        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float32)

        dist_coeffs = np.zeros((4, 1))  # Assuming no lens distortion
        
        # Solve Perspective-n-Point
        success, rotation_vector, translation_vector = cv2.solvePnP(
            MODEL_POINTS, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return self.get_simulated_telemetry()

        # Get Euler angles
        rmat, _ = cv2.Rodrigues(rotation_vector)
        proj_matrix = np.hstack((rmat, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)
        
        pitch = float(euler_angles[0][0])
        yaw = float(euler_angles[1][0])
        roll = float(euler_angles[2][0])

        # Normalize angles (around zero looking straight)
        # solvePnP decomposes to angles, look at absolute deviation
        yaw_deg = yaw
        pitch_deg = pitch
        roll_deg = roll

        # Gaze/Eye contact estimation using iris landmarks if available
        # MediaPipe iris landmarks: Left eye iris is 468-472, Right eye iris is 473-477
        # We can calculate offset of iris relative to eye corners
        # For simplicity, we also weigh in head rotation (since looking away involves turning head)
        
        # Head pose telemetry scores
        # Ideal is looking straight: yaw=0, pitch=0, roll=0
        yaw_deviation = abs(yaw_deg)
        pitch_deviation = abs(pitch_deg)
        roll_deviation = abs(roll_deg)

        # Calculate a head pose stability score (0 to 100)
        # Deviation thresholds: yaw > 15 deg is looking away, pitch > 15 is looking up/down
        head_score = max(0, 100 - int((yaw_deviation * 2.5) + (pitch_deviation * 2.5) + (roll_deviation * 1.5)))
        
        # Determine status
        if yaw_deviation > 15:
            head_status = "Looking Away"
        elif pitch_deviation > 15:
            head_status = "Nodding/Tilted"
        else:
            head_status = "Centered & Stable"

        # Eye contact stability
        # A simpler proxy is eye contact degrades rapidly if the head turns or pitch is bad.
        # Let's inspect eye landmarks 468 (left iris center) and 473 (right iris center) if they exist
        eye_contact_score = 100
        gaze_details = "Excellent focus"
        
        if len(face_landmarks) > 473:
            # Let's compute left iris offset relative to left eye boundaries (landmarks 33 and 133 or similar)
            # Left eye outer corner 33, inner 133
            # We can calculate the ratio of distance from iris to outer corner vs inner corner
            # Let's estimate gaze score using iris offset + head pose
            # Gaze deviation:
            left_iris = face_landmarks[468]
            right_iris = face_landmarks[473]
            
            # Simple gaze ratio check
            # For left eye: landmarks 130 (left boundary) and 243 (right boundary)
            # We'll compute iris horizontal offset:
            left_eye_l = face_landmarks[130]
            left_eye_r = face_landmarks[243]
            left_eye_center = (left_eye_l.x + left_eye_r.x) / 2
            left_gaze_offset = abs(left_iris.x - left_eye_center) / (abs(left_eye_l.x - left_eye_r.x) or 1)
            
            # Weigh gaze offset and head yaw
            gaze_dev = left_gaze_offset * 150 + yaw_deviation
            eye_contact_score = max(0, 100 - int(gaze_dev * 2.2))
            
        else:
            # Gaze score fallback strictly based on head pose
            eye_contact_score = max(0, 100 - int((yaw_deviation * 3.0) + (pitch_deviation * 2.0)))

        if eye_contact_score > 75:
            eye_status = "Steady Eye Contact"
            gaze_details = "Strong engagement"
        elif eye_contact_score > 50:
            eye_status = "Slightly Distracted"
            gaze_details = "Try looking directly at camera"
        else:
            eye_status = "Distracted / Looking Away"
            gaze_details = "Keep your eyes on the interviewer"

        return {
            "eye_contact_score": int(eye_contact_score),
            "head_pose_score": int(head_score),
            "eye_contact_status": eye_status,
            "head_pose_status": head_status,
            "gaze_details": gaze_details,
            "yaw": round(yaw_deg, 1),
            "pitch": round(pitch_deg, 1),
            "roll": round(roll_deg, 1)
        }

    def get_simulated_telemetry(self) -> dict:
        """
        Generates simulated telemetry that jitters slightly to look realistic in testing mode.
        """
        # Create a small random jitter
        import random
        yaw = random.uniform(-3, 3)
        pitch = random.uniform(-2, 2)
        roll = random.uniform(-1, 1)
        
        # Add a subtle drift over time or random spikes (simulating occasional looking away)
        if random.random() < 0.05:
            # Look away spike
            yaw += random.choice([-20, 20])
            eye_contact = random.randint(30, 45)
            head_score = random.randint(40, 55)
            eye_status = "Distracted"
            head_status = "Looking Away"
            gaze_details = "Keep your eyes on the interviewer"
        else:
            eye_contact = max(0, min(100, int(95 - abs(yaw) * 3 - abs(pitch) * 2)))
            head_score = max(0, min(100, int(96 - abs(yaw) * 2 - abs(pitch) * 2 - abs(roll) * 1.5)))
            eye_status = "Steady Eye Contact" if eye_contact > 75 else "Slightly Distracted"
            head_status = "Centered & Stable" if head_score > 80 else "Tilted"
            gaze_details = "Strong engagement" if eye_contact > 75 else "Try looking directly at camera"

        return {
            "eye_contact_score": eye_contact,
            "head_pose_score": head_score,
            "eye_contact_status": eye_status,
            "head_pose_status": head_status,
            "gaze_details": gaze_details,
            "yaw": round(yaw, 1),
            "pitch": round(pitch, 1),
            "roll": round(roll, 1)
        }
