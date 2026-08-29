"""Resource types an agent never reads."""

BLOCKED_RESOURCE_PATTERNS: tuple[str, ...] = (
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.avif", "*.ico", "*.bmp",
    "*.svg",
    "*.woff", "*.woff2", "*.ttf", "*.otf", "*.eot",
    "*.mp4", "*.webm", "*.ogg", "*.mp3", "*.wav", "*.avi", "*.mov", "*.m4a",
)
