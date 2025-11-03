import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html, register_page
from dash_improve_my_llms import mark_important, register_page_metadata

register_page(
    __name__,
    path="/equipment",
    name="Equipment Catalog",
)

register_page_metadata(
    path="/equipment",
    name="Equipment Catalog",
    description="Browse and filter the complete equipment catalog with search and category filters",
)


def layout():
    return html.Div(
        [
            html.H1("Equipment Catalog"),
            mark_important(
                html.Div(
                    [
                        html.H2("Filters"),
                        dmc.TextInput(
                            id="equipment-search",
                            placeholder="Search equipment...",
                            style={"marginBottom": "10px", "width": "300px"},
                        ),
                        dmc.Select(
                            id="equipment-category",
                            data=[
                                {"value": "all", "label": "All Categories"},
                                {"value": "tools", "label": "Tools"},
                                {"value": "machinery", "label": "Machinery"},
                                {"value": "vehicles", "label": "Vehicles"},
                            ],
                            value="all",
                            placeholder="Select category",
                            style={"marginBottom": "20px", "width": "300px"},
                        ),
                    ],
                    id="filters",
                )
            ),
            html.Div(
                [
                    html.H2("Equipment List"),
                    html.Div(id="equipment-list"),
                ]
            ),
            html.Div(
                [
                    html.H3("Statistics"),
                    html.P(id="equipment-stats", children="Loading statistics..."),
                ],
                style={"marginTop": "20px", "padding": "15px", "background": "#f5f5f5"},
            ),
            html.Div(
                [
                    dcc.Link("← Back to Home", href="/"),
                    " | ",
                    dcc.Link("View Analytics →", href="/analytics"),
                ],
                style={"marginTop": "20px"},
            ),
        ]
    )


@callback(
    Output("equipment-list", "children"),
    Output("equipment-stats", "children"),
    Input("equipment-search", "value"),
    Input("equipment-category", "value"),
)
def update_equipment_list(search, category):
    # Mock data
    equipment = [
        {"name": "Drill Press", "category": "tools", "status": "Available"},
        {"name": "Forklift", "category": "vehicles", "status": "In Use"},
        {"name": "CNC Machine", "category": "machinery", "status": "Maintenance"},
        {"name": "Hand Tools Set", "category": "tools", "status": "Available"},
    ]

    # Filter
    filtered = equipment
    if category and category != "all":
        filtered = [e for e in filtered if e["category"] == category]
    if search:
        filtered = [e for e in filtered if search.lower() in e["name"].lower()]

    # Build list
    list_items = [
        html.Div(
            [
                html.Strong(e["name"]),
                f" - {e['category'].title()} - ",
                html.Span(
                    e["status"],
                    style={"color": "green" if e["status"] == "Available" else "orange"},
                ),
            ],
            style={"marginBottom": "10px"},
        )
        for e in filtered
    ]

    available_count = sum(1 for e in equipment if e["status"] == "Available")
    stats = (
        f"Total Items: {len(equipment)} | Showing: {len(filtered)} | "
        f"Available: {available_count}"
    )

    return list_items, stats
