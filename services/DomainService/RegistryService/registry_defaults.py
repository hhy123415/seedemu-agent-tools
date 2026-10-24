"""Pin the upstream version and simulation credentials for service instances and installers.
"""

NAMINGO_REGISTRY_COMMIT = "a783a3c37a5614827f7141f07028e9a6a2d4f5cb"
NAMINGO_REGISTRY_DB_PASSWORD = "b02a-registry-database"
NAMINGO_REGISTRY_ADMIN_EMAIL = "admin@example.com"
NAMINGO_REGISTRY_ADMIN_PASSWORD = "123456"


# Default initial TLDs; each instance can override them.
NAMINGO_REGISTRY_TLDS = ('com', 'net')


def normalize_tlds(tlds):
    """    The database field allows 32 characters including the leading dot; use Punycode for IDNs.
    """
    import re

    if not isinstance(tlds, (list, tuple)) or not tlds:
        raise ValueError('TLDs must be a non-empty list or tuple')
    result = []
    for value in tlds:
        if not isinstance(value, str):
            raise ValueError('Each TLD must be a string')
        name = value.removeprefix('.').lower()
        if not re.fullmatch(r'[a-z](?:[a-z0-9-]{0,29}[a-z0-9])?', name):
            raise ValueError(f'Invalid TLD: {value!r}; use a single ASCII label of at most 31 characters')
        if name not in result:
            result.append(name)
    return tuple(result)
