from urllib.parse import urlparse

from app.normalization.azure_semantic_normalizer import AzureSemanticNormalizer
from app.normalization.models import PathParameter
from app.normalization.parameter_detector import detect_parameter_type, infer_parameter_name


def normalize_path(
    method: str,
    path_or_url: str,
    request_body=None,
    response_body=None,
    use_ai: bool = True,
) -> tuple[str, list[PathParameter]]:
    parsed = urlparse(path_or_url)
    path = parsed.path if parsed.scheme else path_or_url
    path = path.strip()

    if not path.startswith("/"):
        path = f"/{path}"

    raw_segments = [s for s in path.split("/") if s]

    normalized_segments: list[str] = []
    parameters: list[PathParameter] = []

    ai_normalizer = AzureSemanticNormalizer() if use_ai else None

    for index, segment in enumerate(raw_segments):
        previous_segment = raw_segments[index - 1] if index > 0 else None
        next_segment = raw_segments[index + 1] if index + 1 < len(raw_segments) else None

        detected_type = detect_parameter_type(segment)

        if detected_type:
            parameter_name, source, confidence = infer_parameter_name(
                previous_segment=previous_segment,
                detected_type=detected_type,
                raw_value=segment,
                request_body=request_body,
                response_body=response_body,
            )

            if use_ai and confidence < 0.70 and ai_normalizer:
                try:
                    ai_result = ai_normalizer.infer_parameter_name(
                        method=method,
                        path=path,
                        raw_segment=segment,
                        previous_segment=previous_segment,
                        next_segment=next_segment,
                        request_body=request_body,
                        response_body=response_body,
                    )
                    ai_confidence = float(ai_result.get("confidence", 0.0))
                    ai_name = ai_result.get("parameter_name", parameter_name)

                    if ai_confidence >= confidence:
                        parameter_name = ai_name
                        detected_type = ai_result.get("parameter_type", detected_type)
                        source = "azure_openai"
                        confidence = ai_confidence
                except Exception:
                    pass

            normalized_segments.append(f"{{{parameter_name}}}")
            parameters.append(PathParameter(
                name=parameter_name,
                raw_value=segment,
                type=detected_type,
                source=source,
                confidence=confidence,
            ))
        else:
            normalized_segments.append(segment.lower())

    normalized_path = "/" + "/".join(normalized_segments)
    if normalized_path != "/" and normalized_path.endswith("/"):
        normalized_path = normalized_path.rstrip("/")

    return normalized_path, parameters
