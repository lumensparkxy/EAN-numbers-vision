"""
Retry worker for failed barcode detections.

Gives failed images another chance at Gemini decoding,
leveraging its non-deterministic behavior.
"""
