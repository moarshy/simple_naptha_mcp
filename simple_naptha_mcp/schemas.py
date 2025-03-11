from pydantic import BaseModel


class InputSchema(BaseModel):
    port: int