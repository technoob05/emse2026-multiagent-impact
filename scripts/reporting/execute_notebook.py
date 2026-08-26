from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from ipykernel.kernelspec import install as install_kernel_spec
import nbformat
from nbclient import NotebookClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_PATH = (
    Path(sys.argv[1]).resolve()
    if len(sys.argv) > 1
    else PROJECT_ROOT / "notebooks" / "01_multiagent_exploration.ipynb"
)
KERNEL_NAME = "aidev-local"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Register the active virtual environment as a project-local execution kernel.
# This removes any dependency on a separately installed Anaconda/Jupyter kernel.
install_kernel_spec(
    prefix=sys.prefix,
    kernel_name=KERNEL_NAME,
    display_name="Python (AIDev local)",
)

notebook = nbformat.read(NOTEBOOK_PATH, as_version=4)
client = NotebookClient(
    notebook,
    timeout=600,
    kernel_name=KERNEL_NAME,
    resources={"metadata": {"path": str(PROJECT_ROOT)}},
)
client.execute()
nbformat.write(notebook, NOTEBOOK_PATH)
print(f"Executed {NOTEBOOK_PATH}")
