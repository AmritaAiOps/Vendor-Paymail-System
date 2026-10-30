from fastapi.responses import JSONResponse


def stub(payload, status_code: int = 200) -> JSONResponse:
    """STUB(contract): example response with the contract shape. The owner replaces the endpoint and drops X-Stub."""
    return JSONResponse(payload, status_code=status_code, headers={"X-Stub": "true"})
