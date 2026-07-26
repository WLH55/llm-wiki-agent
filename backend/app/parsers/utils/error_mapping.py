"""旧 parser 错误到稳定错误码的映射。"""

from app.parsers.core.schemas import ParseErrorCode


def map_legacy_error(value: object) -> ParseErrorCode:
    """把现有 parser 的 metadata.error 收敛为稳定错误码。"""

    message = str(value or "").strip().lower()
    if message.startswith(("unsupported_file_type", "legacy_ppt_not_supported")):
        return ParseErrorCode.UNSUPPORTED_TYPE
    if message.startswith(("dependency_unavailable", "no_doc_tool")):
        return ParseErrorCode.ENGINE_UNAVAILABLE
    if "too_large" in message or "zip_bomb" in message:
        return ParseErrorCode.TOO_LARGE
    if message.startswith("unsafe_url"):
        return ParseErrorCode.UNSAFE_URL
    if message == "empty_result":
        return ParseErrorCode.EMPTY_CONTENT
    return ParseErrorCode.PARSE_FAILED
