import flet as ft

from main import main

ft.run(
    main,
    assets_dir="assets",
    view=ft.AppView.WEB_BROWSER,
    port=3000,
)
