# Jupyter Notebook Setup

> **Auth note:** Notebooks do not have a `scripts/` directory, so `scripts/auth.py` is not available. Use `InteractiveBrowserCredential` directly — this is the intended exception to the `scripts/auth.py` rule. For scripts (`.py` files), always use `scripts/auth.py`.

```python
# Cell 1: Setup
import os
from azure.identity import InteractiveBrowserCredential
from PowerPlatform.Dataverse.client import DataverseClient

credential = InteractiveBrowserCredential()
client = DataverseClient(
    base_url="https://<org>.crm.dynamics.com",  # replace with your org URL
    credential=credential,
)

# Cell 2: Load data into pandas (direct DataFrame, no manual iteration)
df = client.dataframe.get("account",
    select=["name", "industrycode", "revenue", "numberofemployees"],
)
df.head()
```

**Prerequisites:**
```bash
pip install --upgrade "PowerPlatform-Dataverse-Client>=0.1.0b9" "pandas" "matplotlib" "seaborn" "azure-identity"
```

`pandas>=2.0.0` is a required dependency of the SDK (since b7) and is installed automatically with `--upgrade`.
