{
    "name": "API Request",
    "version": "1.0.0",
    'application': True,
    "category": "",
    "summary": "",
    "description": "",
    "author": "TytencoSoft",
    "license": "OPL-1",
    'price': "5",
    'currency': 'USD',
    'images': [],
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
