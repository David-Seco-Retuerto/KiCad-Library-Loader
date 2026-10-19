"""Local file adapters and browser search links; no HTTP client or downloads.

Identifiers are stable because they are used in saved preferences.
"""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode


@dataclass(frozen=True)
class LocalFileProvider:
    identifier: str
    label: str
    default_subfolder: str
    search_page: str
    search_parameter: str

    def default_folder(self, workspace):
        return Path(workspace) / "Imports" / self.default_subfolder

    def search_url(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Enter a manufacturer part number or keyword.")
        query = query.strip()
        if len(query) > 200 or any(ord(character) < 32 or ord(character) == 127 for character in query):
            raise ValueError("Use a search term of at most 200 characters without control characters.")
        return self.search_page + "?" + urlencode({self.search_parameter: query}, quote_via=quote)

    def scan(self, folder):
        # The native reader is shared by exporters that produce KiCad files.
        from library_core import scan_directory
        return scan_directory(folder)


PROVIDERS = {
    p.identifier: p for p in (
        LocalFileProvider("SamacSys", "SamacSys / Component Search Engine", "SamacSys",
                          "https://ms.componentsearchengine.com/search.html", "searchString"),
        LocalFileProvider("LCSC", "LCSC", "LCSC", "https://www.lcsc.com/search", "q"),
    )
}


def get_provider(identifier):
    try:
        return PROVIDERS[identifier]
    except KeyError as exc:
        raise ValueError(f"Unknown source provider: {identifier}") from exc
