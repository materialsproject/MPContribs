from pydantic import BaseModel


class Limits(BaseModel):
    """Server-enforced request limits, advertised so callers can size their requests.

    These mirror the values enforced by the body-size middleware and the bulk write endpoints;
    consumers (e.g. the mpcontribs client) should read them here rather than hardcoding. The three
    infra limits are global; ``max_components`` is the caller's effective per-consumer contribution
    component cap.
    """

    max_request_bytes: int
    bulk_write_limit: int
    max_components: int
    component_insert_chunk_size: int
