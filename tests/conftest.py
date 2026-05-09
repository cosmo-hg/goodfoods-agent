import os

# Must be set before config.py is imported by any test module
os.environ.setdefault("GROQ_API_KEY", "test-key-for-unit-tests")
