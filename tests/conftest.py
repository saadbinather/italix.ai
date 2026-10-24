"""Non-secret test credentials installed before application modules import."""

import os


os.environ.setdefault("ITALIX_VIEWER_TOKEN", "test-viewer-token-0123456789abcdef")
os.environ.setdefault("ITALIX_OPERATOR_TOKEN", "test-operator-token-0123456789abcde")
