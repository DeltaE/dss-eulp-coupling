# 2. Installation & Build (Docs + Project)

The documentation does **not** require OpenDSS. Only Sphinx-related packages are installed on Read the Docs.

## 2.1 Prerequisites (Project side)

- **Conda**: 24.5.0
- **Python**: 3.9+ (project), 3.11 (docs build on RTD)
- **OpenDSS**: 9.8.0.1 (for simulations, Windows COM interface)
- **Data**: EULP via OEDI (open), SMART-DS feeders (NC, TX, CA)

## 2.2 Create a docs scaffold locally (optional)

```bash
# (Optional) Create a docs-only environment for local preview
conda create -n dss_docs python=3.11 -y
conda activate dss_docs
pip install -r docs/requirements.txt

# Build and preview locally
sphinx-build -b html docs _build/html
python -m http.server --directory _build/html 8000
```

## 2.3 Connect the repo to Read the Docs

1. Commit the **.readthedocs.yaml** and the **docs/** folder to your repository root.
2. Push to GitHub/GitLab/Bitbucket.
3. Create/Log into **Read the Docs** and **Import Project** → select your repository.
4. RTD will detect `.readthedocs.yaml` and build automatically.
5. On success, your docs will be live at a URL like: `https://<project>.readthedocs.io`.

```{admonition} Tip
:class: tip
Keep the project **Public** on RTD to make the site accessible to everyone. You can also add a badge in your README.
```
