from dataclasses import dataclass, fields

@dataclass
class Target:
    id: int
    name: str
    mac: str
    channels: list[int]
    connection_state: bool
    last_successful_send: int
    is_channels_overridden: bool
    override_timeout_remaining: int

    @classmethod
    def get_fields(cls) -> list[str]:
        """Return a list of all field names."""
        return [field.name for field in fields(cls)]