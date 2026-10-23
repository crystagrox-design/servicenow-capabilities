# ServiceNow Capability Atlas

An interactive, searchable guide to ServiceNow capabilities, platform services, work domains and connected workflows. Capability pages combine curated explanations, related visuals, guided work journeys and links to current official product guidance.

## Run locally

Serve this folder over HTTP, for example:

```powershell
python -m http.server 8000
```

Then open `http://localhost:8000`. The capability guide works without a live connection to the original content package; official product references open on ServiceNow documentation pages.

## Content refresh

The site includes a prepared local content package used to associate diagrams and examples with capability areas. To regenerate it from the authorized source material, run `python scripts/build_atlas.py <input-file> --out .` and keep that source material in approved internal storage. The source file is excluded from Git by default.

The GitHub Actions workflow checks selected official ServiceNow release notes, model updates and Build Agent release notes daily, then updates the static site feed. The feed records dates and links to official sources. It is designed for GitHub Pages, but has not been published from this workspace.

## Access and publishing

Review the site's access controls and content permissions before publishing. The content package contains internal-use material, so keep the repository and hosted site private unless the content owner approves public release. A private GitHub repository does not by itself make a GitHub Pages site private. The Pages workflow excludes the raw source file from the deployed artifact.

## Scope

This is a learning and discovery aid. Product packaging, availability, licensing, model support and roadmap details can change. Confirm those details against current ServiceNow documentation and your organization's account team.
