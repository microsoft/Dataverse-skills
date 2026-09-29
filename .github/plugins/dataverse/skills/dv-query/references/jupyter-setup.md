# Jupyter Notebook Setup

> **Auth note:** Notebooks do not have a `scripts/` directory, so `scripts/auth.py` is not available. Use `InteractiveBrowserCredential` directly — this is the intended exception to the `scripts/auth.py` rule. For scripts (`.py` files), always use `scripts/auth.py`.

```python
# Cell 1: Setup
import os
from azure.identity import InteractiveBrowserCredential
from PowerPlatform.Dataverse.client import DataverseClient
from PowerPlatform.Dataverse.core.config import OperationContext

credential = InteractiveBrowserCredential()
# Telemetry attribution (same closed schema as scripts/auth.py): skill is fixed for this
# notebook. A fresh kernel does not auto-load .env, so read it (cwd or parent) first,
# then fall back to "unknown".
from pathlib import Path
for _p in (Path.cwd() / ".env", Path.cwd().parent / ".env"):
    if _p.exists():
        for _line in _p.read_text().splitlines():
            _s = _line.strip()
            if _s and not _s.startswith("#") and "=" in _s:
                _k, _, _v = _s.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())
        break
_ver = os.environ.get("DATAVERSE_PLUGIN_VERSION", "unknown")
_agent = os.environ.get("DATAVERSE_PLUGIN_AGENT", "unknown")
client = DataverseClient(
    base_url="https://<org>.crm.dynamics.com",  # replace with your org URL
    credential=credential,
    context=OperationContext(user_agent_context=f"app=dataverse-skills/{_ver};skill=dv-query;agent={_agent}"),
)

# Cell 2: Load data into pandas (direct DataFrame, no manual iteration)
df = client.query.builder("account") \
    .select("name", "industrycode", "revenue", "numberofemployees") \
    .execute() \
    .to_dataframe()
df.head()
```

**Prerequisites:**
```bash
pip install --upgrade PowerPlatform-Dataverse-Client pandas matplotlib seaborn azure-identity
```

`pandas>=2.0.0` is a required dependency of the SDK (since b7) and is installed automatically with `--upgrade`.
