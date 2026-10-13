"""
Multi-Modal & Sensory Endpoints (Section 03)
Streaming Audio Pipeline, Image Generation Gateway, DOM/Spatial Inspector, Document Extractor
"""
from .audio_pipeline import AudioConfig, AudioStream, StreamingAudioPipeline
from .document_extractor import DocumentExtractor, DocumentType, ExtractedDocument
from .dom_inspector import DOMSpatialInspector, SpatialBounds, UIElement
from .image_gateway import ImageGenerationGateway, ImageRequest, ImageResponse

__all__ = [
    "StreamingAudioPipeline",
    "AudioConfig",
    "AudioStream",
    "ImageGenerationGateway",
    "ImageRequest",
    "ImageResponse",
    "DOMSpatialInspector",
    "SpatialBounds",
    "UIElement",
    "DocumentExtractor",
    "ExtractedDocument",
    "DocumentType",
]
