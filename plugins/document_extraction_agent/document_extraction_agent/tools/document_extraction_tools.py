"""Document extraction tools for OCR, layout, and VLM analysis."""

from typing import Any, Dict, List

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


def _not_implemented_result(tool_name: str, details: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standardized not-implemented ToolError payload."""
    tool_error = ToolError(
        f"{tool_name} is not implemented yet.",
        tool_name=tool_name,
        details=details,
    )
    return tool_error_payload(tool_error)


class OcrExtractTool(ToolProtocol):
    """Run OCR on a document and return text regions with bounding boxes."""

    @property
    def name(self) -> str:
        return "ocr_extract"

    @property
    def description(self) -> str:
        return "Extract OCR text regions with confidence scores and bounding boxes"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Path to the input image or PDF page.",
                }
            },
            "required": ["document_path"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    async def execute(self, document_path: str, **kwargs: Any) -> Dict[str, Any]:
        """Return OCR extraction results for a document path."""
        return _not_implemented_result(self.name, {"document_path": document_path})

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "document_path" not in kwargs:
            return False, "Missing required parameter: document_path"
        if not isinstance(kwargs["document_path"], str):
            return False, "Parameter 'document_path' must be a string"
        return True, None


class ReadingOrderTool(ToolProtocol):
    """Determine reading order for OCR regions using layout models."""

    @property
    def name(self) -> str:
        return "reading_order"

    @property
    def description(self) -> str:
        return "Order OCR regions into a reading sequence"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "regions": {
                    "type": "array",
                    "description": "OCR regions with bbox data",
                }
            },
            "required": ["regions"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    async def execute(self, regions: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
        """Return ordered OCR regions for downstream use."""
        return _not_implemented_result(self.name, {"regions": regions})

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "regions" not in kwargs:
            return False, "Missing required parameter: regions"
        if not isinstance(kwargs["regions"], list):
            return False, "Parameter 'regions' must be an array"
        return True, None


class LayoutDetectTool(ToolProtocol):
    """Detect document layout regions such as tables, charts, and text."""

    @property
    def name(self) -> str:
        return "layout_detect"

    @property
    def description(self) -> str:
        return "Detect layout regions (text, table, chart, figure) with boxes"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Path to the input image or PDF page.",
                }
            },
            "required": ["document_path"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    async def execute(self, document_path: str, **kwargs: Any) -> Dict[str, Any]:
        """Return detected layout regions for a document path."""
        return _not_implemented_result(self.name, {"document_path": document_path})

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "document_path" not in kwargs:
            return False, "Missing required parameter: document_path"
        if not isinstance(kwargs["document_path"], str):
            return False, "Parameter 'document_path' must be a string"
        return True, None


class CropRegionTool(ToolProtocol):
    """Crop a region from a document for VLM analysis."""

    @property
    def name(self) -> str:
        return "crop_region"

    @property
    def description(self) -> str:
        return "Crop a document region and return base64-encoded image data"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Path to the input image or PDF page.",
                },
                "bbox_xyxy": {
                    "type": "array",
                    "description": "Bounding box as [x1, y1, x2, y2]",
                },
            },
            "required": ["document_path", "bbox_xyxy"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    async def execute(
        self, document_path: str, bbox_xyxy: List[int], **kwargs: Any
    ) -> Dict[str, Any]:
        """Return a cropped region as base64 data for VLM tools."""
        return _not_implemented_result(
            self.name, {"document_path": document_path, "bbox_xyxy": bbox_xyxy}
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "document_path" not in kwargs:
            return False, "Missing required parameter: document_path"
        if "bbox_xyxy" not in kwargs:
            return False, "Missing required parameter: bbox_xyxy"
        if not isinstance(kwargs["document_path"], str):
            return False, "Parameter 'document_path' must be a string"
        if not isinstance(kwargs["bbox_xyxy"], list):
            return False, "Parameter 'bbox_xyxy' must be an array"
        return True, None


class AnalyzeTableTool(ToolProtocol):
    """Analyze a table region using a vision-language model."""

    @property
    def name(self) -> str:
        return "analyze_table"

    @property
    def description(self) -> str:
        return "Extract structured table data from an image region"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image content",
                },
                "region_id": {
                    "type": "integer",
                    "description": "Layout region identifier",
                },
            },
            "required": ["image_base64", "region_id"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    async def execute(
        self, image_base64: str, region_id: int, **kwargs: Any
    ) -> Dict[str, Any]:
        """Return structured table data from a region crop."""
        return _not_implemented_result(
            self.name, {"image_base64": image_base64, "region_id": region_id}
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "image_base64" not in kwargs:
            return False, "Missing required parameter: image_base64"
        if "region_id" not in kwargs:
            return False, "Missing required parameter: region_id"
        if not isinstance(kwargs["image_base64"], str):
            return False, "Parameter 'image_base64' must be a string"
        if not isinstance(kwargs["region_id"], int):
            return False, "Parameter 'region_id' must be an integer"
        return True, None


class AnalyzeChartTool(ToolProtocol):
    """Analyze a chart or figure region using a vision-language model."""

    @property
    def name(self) -> str:
        return "analyze_chart"

    @property
    def description(self) -> str:
        return "Extract chart metadata and data points from an image region"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image content",
                },
                "region_id": {
                    "type": "integer",
                    "description": "Layout region identifier",
                },
            },
            "required": ["image_base64", "region_id"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    async def execute(
        self, image_base64: str, region_id: int, **kwargs: Any
    ) -> Dict[str, Any]:
        """Return structured chart data from a region crop."""
        return _not_implemented_result(
            self.name, {"image_base64": image_base64, "region_id": region_id}
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "image_base64" not in kwargs:
            return False, "Missing required parameter: image_base64"
        if "region_id" not in kwargs:
            return False, "Missing required parameter: region_id"
        if not isinstance(kwargs["image_base64"], str):
            return False, "Parameter 'image_base64' must be a string"
        if not isinstance(kwargs["region_id"], int):
            return False, "Parameter 'region_id' must be an integer"
        return True, None
