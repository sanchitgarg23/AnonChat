"""
Gender Verification AI Microservice

A privacy-first, stateless microservice for gender verification using live camera images.
Part of an anonymous chat platform implementing controlled anonymity to prevent catfishing.

This version uses OpenCV DNN for both face detection and gender classification.

Privacy Guarantees:
1. No image persistence - images are processed entirely in memory
2. No logging of image data - only metadata (success/error status) is logged
3. Immediate cleanup - image bytes are deleted immediately after inference
4. No database - completely stateless operation
5. No authentication data stored
"""

import io
import logging
from enum import Enum
from typing import Optional
import os
import urllib.request
import ssl
import onnxruntime as ort

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import numpy as np
from PIL import Image
import cv2

# Configure logging - NEVER log image data
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Gender Verification API",
    description="Privacy-first gender verification service for anonymous chat platform",
    version="1.0.0"
)

# Enable CORS
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Allowed image MIME types
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg", 
    "image/png",
    "image/webp"
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class GenderEnum(str, Enum):
    MALE = "M"
    FEMALE = "F"


class SuccessResponse(BaseModel):
    verified: bool = True
    gender: GenderEnum


class ErrorResponse(BaseModel):
    verified: bool = False
    error: str


# Model configuration
MODEL_DIR = os.path.dirname(os.path.abspath(__file__))

# Face detection model (OpenCV DNN)
FACE_PROTO = os.path.join(MODEL_DIR, "deploy.prototxt")
FACE_MODEL = os.path.join(MODEL_DIR, "res10_300x300_ssd_iter_140000.caffemodel")

# Gender classification model
GENDER_PROTO = os.path.join(MODEL_DIR, "gender_deploy.prototxt")
GENDER_MODEL = os.path.join(MODEL_DIR, "gender_net.caffemodel")

# Liveness detection model (MiniFASNetV2)
LIVENESS_MODEL_URL = "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx"
LIVENESS_MODEL_PATH = os.path.join(MODEL_DIR, "MiniFASNetV2.onnx")

GENDER_MODEL_MEAN_VALUES = (78.4263377603, 87.7689143744, 114.895847746)
GENDER_LIST = ['M', 'F']  # Male, Female

# Global model variables
face_net = None
gender_net = None
liveness_net = None


def download_models():
    """Download required models if not present."""
    models = [
        (FACE_PROTO, "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/dnn/face_detector/deploy.prototxt"),
        (FACE_MODEL, "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"),
        (GENDER_PROTO, "https://raw.githubusercontent.com/GilLevi/AgeGenderDeepLearning/master/gender_net_definitions/deploy.prototxt"),
        (GENDER_PROTO, "https://raw.githubusercontent.com/GilLevi/AgeGenderDeepLearning/master/gender_net_definitions/deploy.prototxt"),
        (GENDER_MODEL, "https://www.dropbox.com/s/iyv483wz7ztr9gh/gender_net.caffemodel?dl=1"),
        (LIVENESS_MODEL_PATH, LIVENESS_MODEL_URL),
    ]
    
    for path, url in models:
        if not os.path.exists(path):
            logger.info(f"Downloading {os.path.basename(path)}...")
            try:
                # Add headers to avoid 403 errors and ignore SSL errors
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(request, context=ctx) as response:
                    with open(path, 'wb') as out_file:
                        out_file.write(response.read())
                logger.info(f"Downloaded {os.path.basename(path)}")
            except Exception as e:
                logger.error(f"Failed to download {os.path.basename(path)}: {e}")
                raise


def load_models():
    """Load face detection and gender classification models."""
    global face_net, gender_net, liveness_net
    
    if face_net is None or gender_net is None or liveness_net is None:
        download_models()
        face_net = cv2.dnn.readNet(FACE_MODEL, FACE_PROTO)
        gender_net = cv2.dnn.readNet(GENDER_MODEL, GENDER_PROTO)
        
        # Load liveness model
        providers = ['CPUExecutionProvider']
        liveness_net = ort.InferenceSession(LIVENESS_MODEL_PATH, providers=providers)
        
        logger.info("Models loaded successfully")
    
    return face_net, gender_net, liveness_net


def validate_image_file(file: UploadFile) -> None:
    """
    Validate that the uploaded file is a valid image.
    
    Raises HTTPException if validation fails.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_CONTENT_TYPES)}"
        )
    
    if file.filename:
        ext = "." + file.filename.lower().split(".")[-1] if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )


def process_image_for_analysis(image_bytes: bytes) -> np.ndarray:
    """Convert image bytes to numpy array (BGR format for OpenCV)."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")
        # Convert to BGR for OpenCV
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Invalid or corrupted image file"
        )


def detect_faces(image_bgr: np.ndarray, confidence_threshold: float = 0.7) -> list:
    """
    Detect faces using OpenCV DNN face detector.
    
    Returns list of face bounding boxes.
    """
    h, w = image_bgr.shape[:2]
    
    # Create blob from image
    blob = cv2.dnn.blobFromImage(
        image_bgr, 1.0, (300, 300), 
        (104.0, 177.0, 123.0), 
        swapRB=False, crop=False
    )
    
    face_net.setInput(blob)
    detections = face_net.forward()
    
    faces = []
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        
        if confidence > confidence_threshold:
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            x1, y1, x2, y2 = box.astype(int)
            
            # Add padding
            padding = 20
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(w, x2 + padding)
            y2 = min(h, y2 + padding)
            
            faces.append((x1, y1, x2, y2))
    
    return faces


def classify_gender(image_bgr: np.ndarray, face_box: tuple) -> str:
    """
    Classify gender from a face region.
    
    Returns 'M' for male or 'F' for female.
    """
    x1, y1, x2, y2 = face_box
    face_img = image_bgr[y1:y2, x1:x2]
    
    # Prepare blob for gender classification
    blob = cv2.dnn.blobFromImage(
        face_img, 1.0, (227, 227), 
        GENDER_MODEL_MEAN_VALUES, 
        swapRB=False
    )
    
    gender_net.setInput(blob)
    gender_preds = gender_net.forward()
    gender_idx = gender_preds[0].argmax()
    
    return GENDER_LIST[gender_idx]


def check_liveness(image_bgr: np.ndarray, face_box: tuple) -> float:
    """
    Check if the face is real or fake using MiniFASNetV2.
    Returns a liveness score (higher is more likely real).
    """
    # Parameters for MiniFASNetV2
    scale = 2.7
    model_input_size = (80, 80)
    
    x1, y1, x2, y2 = face_box
    box_w = x2 - x1
    box_h = y2 - y1
    h, w = image_bgr.shape[:2]
    
    # Calculate center
    center_x = x1 + box_w / 2
    center_y = y1 + box_h / 2
    
    # Apply scaling
    new_w = box_w * scale
    new_h = box_h * scale
    
    # Calculate new coordinates
    left = max(0, int(center_x - new_w / 2))
    top = max(0, int(center_y - new_h / 2))
    right = min(w, int(center_x + new_w / 2))
    bottom = min(h, int(center_y + new_h / 2))
    
    # Crop face
    face_img = image_bgr[top:bottom, left:right]
    
    if face_img.size == 0:
        return 0.0
        
    # Resize to model input size
    face_img = cv2.resize(face_img, model_input_size)
    
    # Preprocess
    face_img = face_img.astype(np.float32)
    face_img = np.transpose(face_img, (2, 0, 1)) # HWC -> CHW
    face_img = np.expand_dims(face_img, axis=0)  # Add batch dimension
    
    # Inference
    input_name = liveness_net.get_inputs()[0].name
    output_name = liveness_net.get_outputs()[0].name
    
    logits = liveness_net.run([output_name], {input_name: face_img})[0]
    
    # Softmax
    probs = np.exp(logits - np.max(logits, axis=1, keepdims=True))
    probs = probs / probs.sum(axis=1, keepdims=True)
    
    # Class 1 is "Real", Class 0 is "Fake"
    real_score = probs[0][1]
    
    return float(real_score)


def analyze_gender(image_bgr: np.ndarray) -> dict:
    """
    Analyze the image for face detection and gender classification.
    """
    try:
        # Ensure models are loaded
        load_models()
        
        # Detect faces
        faces = detect_faces(image_bgr)
        
        if len(faces) == 0:
            return {"success": False, "error": "Face not detected"}
        
        if len(faces) > 1:
            return {
                "success": False,
                "error": "Multiple faces detected. Please ensure only one face is visible."
            }
        
        # Check liveness
        liveness_score = check_liveness(image_bgr, faces[0])
        is_real = liveness_score > 0.5  # Threshold can be adjusted
        
        if not is_real:
            return {
                "success": False,
                "error": "Liveness check failed. Please ensure you are capturing a real person."
            }
        
        # Classify gender
        gender = classify_gender(image_bgr, faces[0])
        
        return {
            "success": True, 
            "gender": GenderEnum.MALE if gender == "M" else GenderEnum.FEMALE,
            "liveness_score": liveness_score
        }
            
    except Exception as e:
        logger.error(f"Gender analysis failed: {type(e).__name__}")
        return {
            "success": False,
            "error": "Analysis failed. Please try again with a clearer image."
        }


@app.post("/verify-gender", response_model=None)
async def verify_gender(image: UploadFile = File(..., description="Live camera image for gender verification")):
    """
    Verify gender from a live camera image.
    
    **Privacy Guarantees:**
    - Image is processed entirely in memory
    - Image bytes are deleted immediately after inference
    - No image data is logged or stored
    - Completely stateless operation
    
    **Requirements:**
    - Single face must be clearly visible
    - Valid image format (JPEG, PNG, WebP)
    
    **Returns:**
    - Success: `{"verified": true, "gender": "M" or "F"}`
    - Failure: `{"verified": false, "error": "error message"}`
    """
    image_bytes = None
    image_array = None
    
    try:
        validate_image_file(image)
        
        image_bytes = await image.read()
        
        if len(image_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty file received")
        
        image_array = process_image_for_analysis(image_bytes)
        result = analyze_gender(image_array)
        
        if result["success"]:
            logger.info("Gender verification successful")
            return JSONResponse(
                status_code=200,
                content={"verified": True, "gender": result["gender"].value}
            )
        else:
            logger.info(f"Gender verification failed: {result['error']}")
            return JSONResponse(
                status_code=200,
                content={"verified": False, "error": result["error"]}
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}")
        return JSONResponse(
            status_code=500,
            content={"verified": False, "error": "Internal server error"}
        )
    finally:
        # CRITICAL: Clean up image data immediately
        if image_bytes is not None:
            del image_bytes
        if image_array is not None:
            del image_array
        await image.close()


@app.on_event("startup")
async def startup_event():
    """Pre-load models on startup."""
    logger.info("Loading models...")
    load_models()
    logger.info("Service ready!")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "gender-verification"}


@app.get("/")
async def root():
    """Service information."""
    return {
        "service": "Gender Verification API",
        "version": "1.0.0",
        "privacy": "No images are stored. All processing is done in-memory.",
        "endpoint": "POST /verify-gender"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
