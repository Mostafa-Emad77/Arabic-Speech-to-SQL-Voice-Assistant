import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure the backend package is importable from tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Provide a stub for mysql.connector so database.py can be imported
# without the actual MySQL driver installed.
if "mysql" not in sys.modules:
    mysql_mock = MagicMock()
    sys.modules["mysql"] = mysql_mock
    sys.modules["mysql.connector"] = mysql_mock.connector
