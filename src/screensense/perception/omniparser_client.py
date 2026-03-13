"""OmniParser Model Client

Wraps Microsoft's OmniParser model for local UI element detection.
Detects interactive elements with bounding boxes, types, and text labels.

Uses:
- YOLOv8 for icon/element detection (microsoft/OmniParser-v2.0)
- Florence-2 for icon caption generation
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    YOLO = None  # type: ignore

try:
    from transformers import AutoProcessor, AutoModelForCausalLM
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    AutoProcessor = None  # type: ignore
    AutoModelForCausalLM = None  # type: ignore
    torch = None  # type: ignore


@dataclass
class BoundingBox:
    """Bounding box coordinates"""
    x: int  # top-left x
    y: int  # top-left y
    width: int
    height: int
    
    def center(self) -> tuple[int, int]:
        """Get center point of bounding box"""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    def overlaps(self, other: BoundingBox, tolerance: int = 10) -> bool:
        """Check if this bbox overlaps with another within tolerance"""
        return not (
            self.x + self.width + tolerance < other.x or
            other.x + other.width + tolerance < self.x or
            self.y + self.height + tolerance < other.y or
            other.y + other.height + tolerance < self.y
        )


@dataclass
class DetectedElement:
    """UI element detected by OmniParser"""
    element_id: str
    element_type: str  # button, input, link, text, image, etc.
    text_label: str
    bbox: BoundingBox
    confidence: float  # OmniParser's detection confidence
    attributes: dict[str, Any]


class OmniParserClient:
    """Client for OmniParser model inference"""
    
    # Element type mappings
    ELEMENT_TYPES = {
        'button', 'input', 'link', 'text', 'image', 
        'checkbox', 'radio', 'dropdown', 'menu', 'icon'
    }
    
    def __init__(
        self,
        model_path: str | None = None,
        device: str = "cpu",
        box_threshold: float = 0.05,
        use_simple_mode: bool = True,
    ):
        """
        Initialize OmniParser client.
        
        Args:
            model_path: Path to OmniParser model weights (None = use Hugging Face)
            device: Device for inference ("cpu", "cuda")
            box_threshold: Confidence threshold for detection (0.01-1.0)
            use_simple_mode: Use simple detection without caption model (faster)
        """
        self._model_path = model_path
        self._device = device
        self._box_threshold = box_threshold
        self._use_simple_mode = use_simple_mode
        self._yolo_model = None
        self._caption_model = None
        self._caption_processor = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        Load OmniParser model.
        
        Returns:
            True if successful, False otherwise
        """
        if not YOLO_AVAILABLE:
            print("[OmniParser] ultralytics not available, using stub mode")
            self._initialized = True
            return False
        
        try:
            # Load YOLO detection model
            if self._model_path:
                self._yolo_model = YOLO(self._model_path)
            else:
                # Use pre-trained model from Hugging Face
                print("[OmniParser] Downloading YOLOv8 model from Hugging Face...")
                # For now, use standard YOLOv8 - user can download OmniParser weights manually
                self._yolo_model = YOLO('yolov8n.pt')
            
            if self._device == "cuda" and torch and torch.cuda.is_available():
                self._yolo_model.to('cuda')
            
            # Load caption model if not in simple mode
            if not self._use_simple_mode and TRANSFORMERS_AVAILABLE:
                print("[OmniParser] Loading Florence-2 caption model...")
                self._caption_processor = AutoProcessor.from_pretrained(
                    "microsoft/Florence-2-base",
                    trust_remote_code=True
                )
                self._caption_model = AutoModelForCausalLM.from_pretrained(
                    "microsoft/Florence-2-base",
                    torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
                    trust_remote_code=True
                )
                if self._device == "cuda":
                    self._caption_model.to('cuda')
            
            self._initialized = True
            print("[OmniParser] Initialized successfully")
            return True
        except Exception as e:
            print(f"[OmniParser] Failed to load model: {e}")
            self._initialized = True  # Mark as initialized to use stub mode
            return False
    
    def detect_elements(self, frame_rgb: np.ndarray) -> list[DetectedElement]:
        """
        Detect interactive UI elements in screen frame.
        
        Args:
            frame_rgb: RGB frame as numpy array (H, W, 3)
        
        Returns:
            List of detected elements with bounding boxes
        """
        if not self._initialized:
            if not self.initialize():
                return []
        
        # If YOLO model not loaded, use stub
        if self._yolo_model is None:
            return self._stub_detection(frame_rgb)
        
        try:
            # Convert numpy array to PIL Image
            image = Image.fromarray(frame_rgb)
            
            # Run YOLO detection
            results = self._yolo_model.predict(
                image,
                conf=self._box_threshold,
                verbose=False
            )
            
            # Parse results
            elements = []
            for result in results:
                boxes = result.boxes
                for i, box in enumerate(boxes):
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    
                    # Get class name
                    class_name = result.names.get(cls, "unknown")
                    
                    # Generate caption if caption model available
                    text_label = class_name
                    if self._caption_model and not self._use_simple_mode:
                        text_label = self._generate_caption(image, (x1, y1, x2, y2))
                    
                    # Create element
                    element = DetectedElement(
                        element_id=f"omni_{i}_{int(x1)}_{int(y1)}",
                        element_type=self._map_class_to_type(class_name),
                        text_label=text_label,
                        bbox=BoundingBox(
                            x=int(x1),
                            y=int(y1),
                            width=int(x2 - x1),
                            height=int(y2 - y1),
                        ),
                        confidence=conf,
                        attributes={"class": class_name},
                    )
                    elements.append(element)
            
            return elements
        except Exception as e:
            print(f"[OmniParser] Detection failed: {e}")
            return []
    
    def get_bounding_box(self, element_id: str) -> BoundingBox | None:
        """
        Retrieve bounding box for a detected element.
        
        Args:
            element_id: Element identifier
        
        Returns:
            BoundingBox if found, None otherwise
        """
        # TODO: Implement element lookup from cache
        return None
    
    def _stub_detection(self, frame_rgb: np.ndarray) -> list[DetectedElement]:
        """
        Stub implementation for testing.
        Returns empty list until real model is integrated.
        """
        # Generate deterministic element ID from frame
        frame_hash = hashlib.md5(frame_rgb.tobytes()).hexdigest()[:8]
        
        # Return empty list for now
        # Real implementation will run OmniParser inference here
        return []
    
    def _generate_caption(self, image: Image.Image, bbox: tuple) -> str:
        """Generate caption for detected element using Florence-2"""
        try:
            # Crop image to bounding box
            x1, y1, x2, y2 = bbox
            cropped = image.crop((x1, y1, x2, y2))
            
            # Generate caption
            inputs = self._caption_processor(
                text="<CAPTION>",
                images=cropped,
                return_tensors="pt"
            )
            
            if self._device == "cuda":
                inputs = {k: v.to('cuda') for k, v in inputs.items()}
            
            generated_ids = self._caption_model.generate(
                **inputs,
                max_new_tokens=20
            )
            
            caption = self._caption_processor.batch_decode(
                generated_ids,
                skip_special_tokens=True
            )[0]
            
            return caption.strip()
        except Exception:
            return "icon"
    
    def _map_class_to_type(self, class_name: str) -> str:
        """Map YOLO class name to element type"""
        class_lower = class_name.lower()
        
        # Map common YOLO classes to UI element types
        if any(word in class_lower for word in ['button', 'btn']):
            return 'button'
        elif any(word in class_lower for word in ['text', 'label']):
            return 'text'
        elif any(word in class_lower for word in ['input', 'field', 'box']):
            return 'input'
        elif any(word in class_lower for word in ['link', 'hyperlink']):
            return 'link'
        elif any(word in class_lower for word in ['image', 'img', 'picture']):
            return 'image'
        elif any(word in class_lower for word in ['checkbox', 'check']):
            return 'checkbox'
        elif any(word in class_lower for word in ['radio']):
            return 'radio'
        elif any(word in class_lower for word in ['dropdown', 'select', 'combo']):
            return 'dropdown'
        elif any(word in class_lower for word in ['menu']):
            return 'menu'
        else:
            return 'icon'
