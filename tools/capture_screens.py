"""Render actual Pygame screens for the book without opening desktop windows."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    entries = {"menu": "title", "scenarios": "campaigns", "select": "officer-selection", "map": "kingdom",
               "officers": "officers", "diplomacy": "diplomacy", "chronicle": "chronicle", "battle": "battle", "editor": "editor"}
    for view, name in entries.items():
        output = ROOT / "docs" / "images" / f"{name}.png"
        command = [sys.executable, "-m", "chaos_kingdom", "play", "--headless", "--frames", "2", "--view", view, "--screenshot", str(output)]
        subprocess.run(command, cwd=ROOT, check=True)
        print(output.name)
    from chaos_kingdom.ui.app import App
    import pygame
    app = App(headless=True)
    try:
        app.start_demo()
        for _ in range(25):
            app.battle.update(1)
        app.draw()
        output = ROOT / "docs/images/battle-engaged.png"
        pygame.image.save(app.canvas, str(output))
        print(output.name)
        app.dispatch("editor")
        region = next(s.id for s in app.world.locations.values() if s.terrain == "river")
        app.editor.open(region)
        app.draw()
        output = ROOT / "docs/images/editor-river.png"
        pygame.image.save(app.canvas, str(output))
        print(output.name)
        app.editor.open("s01")
        app.draw()
        output = ROOT / "docs/images/editor-castle.png"
        pygame.image.save(app.canvas, str(output))
        print(output.name)
        app.dispatch("editor_test")
        app.battle.update(1)
        app.draw()
        output = ROOT / "docs/images/battle-castle.png"
        pygame.image.save(app.canvas, str(output))
        print(output.name)
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
