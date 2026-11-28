{
    "name": "API Request",
    "version": "1.0.0",
    'application': True,
    "category": "Productivity",
    "summary": "Inspect API responses in Odoo and export JSON tables to Excel.",
    "description": """
API Request helps administrators configure HTTP GET endpoints and review their responses directly in Odoo.

Features
========
* Configure an endpoint URL and an optional API key.
* Test connectivity and see whether each endpoint is connected.
* Inspect JSON and XML responses, including nested field paths.
* Browse JSON responses in a table or formatted JSON view.
* Copy the formatted response to the clipboard.
* Export JSON tables to Excel worksheets; nested lists and objects get their own related worksheets.

The module sends GET requests. It is designed for reading and inspecting API responses; it does not provide tools for creating or updating data on external services.
""",
    "author": "TytencoSoft",
    "license": "OPL-1",
    'price': "0",
    'currency': 'USD',
    'images': ['static/description/icon.png'],
    "depends": ['base', 'mail', 'web'],
    "assets": {
        "web.assets_backend": [
            "api_request/static/src/js/api_response_dashboard.js",
            "api_request/static/src/xml/api_response_dashboard.xml",
        ],
    },
    "data": [
        "views/list_api_request.xml",
        "views/our_api_request.xml",
        "views/menu.xml",
        "security/ir.model.access.csv"
    ],
    "installable": True,
    "auto_install": False,
}
