import re


def sanitize_vm_name(name: str, max_length: int = 63) -> str:
    """Return a sanitized VM name suitable for Proxmox (RFC1123-like).

    - lowercase
    - replace invalid chars with '-'
    - collapse multiple '-' and trim
    - ensure starts/ends with alphanumeric
    - truncate to max_length
    """
    if not name:
        return ''
    s = name.strip().lower()
    # replace any character not a-z, 0-9, or '-' with '-'
    s = re.sub(r'[^a-z0-9-]', '-', s)
    # collapse dashes
    s = re.sub(r'-{2,}', '-', s)
    # trim leading/trailing dashes
    s = s.strip('-')
    # ensure starts with alnum
    if not s or not re.match(r'^[a-z0-9]', s):
        s = 'vm-' + s
    # truncate, prefer to keep last part
    if len(s) > max_length:
        s = s[:max_length]
        s = s.rstrip('-')
    return s
