"""
UpFront: Unit allocation editor
"""

# Standard library
import sys

# Third-party
import arcade
import arcade.gui
import pandas as pd
import pyperclip
import yaml



# ──[ Parameters ]─────────────────────────────────────────────────────────────

WINDOW_WIDTH = 1600 # start size, the window is resizable
WINDOW_HEIGHT = 900
WINDOW_TITLE = "Up Front – Unit Allocation"
GROUPS = ["A", "B", "C", "D"]
SCENARIOS = ["A", "B"]
ALLOCATION_FILE = "userdata/unit_allocation.yaml"
NATIONS = {"american": "Americans", "british": "British", "french": "French", "german": "Germans",
           "italian": "Italians", "japanese": "Japanese", "russian": "Russians"}
SUPPORT_WEAPONS = ["Light Machinegun", "Medium Machinegun", "BAR"]
UNIT_WIDTH = 160
UNIT_HEIGHT = UNIT_WIDTH * 775 / 600
UNIT_GAP = 10
STATS_WIDTH = 280 # stats block at the start of each row
ROW_HEIGHT = UNIT_HEIGHT + 20
ROW_GAP = 20
TREE_WIDTH = 320 # tree on the right (longest AFV names)
TREE_LINE = 30
SAVE_BAR_HEIGHT = 110 # save bar at the bottom of the tree
BACKGROUND_COLOR = (50, 59, 64, 255)
PANEL_COLOR = (40, 47, 51, 255)
LINE_COLOR = arcade.color.WHITE
DROP_COLOR = (255, 255, 255, 18) # row under the dragged units
MOVE_SPEED = 15 # cards glide to their place (higher = faster)
HOVER_ENLARGE = 1.05 # card under the mouse, as in the game

# Row header
LABEL_COLOR = (160, 170, 175, 255)
BADGE_COLOR = (90, 110, 120, 255)
NO_LEADER_COLOR = (170, 50, 50, 255)
BAR_COLOR = (200, 210, 215, 255)
FIREPOWER_FULL = 60 # firepower of a full bar
BAR_MAX_HEIGHT = 72
HEADER_TEXT_X = 82 # headline and badges, right of the group letter
MORALE_COLORS = {1: (210, 50, 50, 255), 2: (235, 140, 140, 255), 3: (245, 245, 245, 255),
                 4: (140, 180, 240, 255), 5: (70, 130, 230, 255), 6: (30, 80, 200, 255)}



# ──[ Classes ]────────────────────────────────────────────────────────────────

class UnitCard(arcade.Sprite):

    def __init__(self, unit_id, row):

        self.id = unit_id
        self.function = row["function"] # SL, ASL or empty
        self.weapon = row["weapon"]
        self.kind = row["kind"] # Soldiers, Ordnance or AFVs
        self.morale = row["morale"]
        self.points = row["points"]

        # Firepower per range 0-5 (crew-served weapons: crewed values)
        crewed = row["firepower"].split("/")[0]
        self.firepower = []
        for value in crewed.split("|"):
            if value == "NA": # flamethrower out of range
                value = 0
            self.firepower.append(int(value))

        super().__init__(f"assets/units/{row['nation']}/{unit_id}.jpg")
        self.width = UNIT_WIDTH
        self.height = UNIT_HEIGHT

        # Place the card glides to
        self.target_left = 0
        self.target_top = 0



class EditorView(arcade.View):

    def __init__(self, scenario, nation):
        super().__init__()

        # Data
        self.scenarios = yaml.safe_load(open("assets/scenarios.yaml", encoding="utf-8"))
        self.allocations = yaml.safe_load(open(ALLOCATION_FILE, encoding="utf-8"))
        unit_table = pd.read_csv("assets/units/unit_table.csv", sep=",").set_index("id")
        afv_table = pd.read_csv("assets/units/afv_table.csv", sep=",").set_index("id")
        afv_table["firepower"] = afv_table["mg"].fillna("0|0|0|0|0|0") # AFVs fire with their MG
        unit_table["kind"] = "Soldiers"
        unit_table.loc[unit_table["to_hit"].notna(), "kind"] = "Ordnance"
        afv_table["kind"] = "AFVs"
        self.unit_table = pd.concat([unit_table, afv_table])

        # Rows (groups A-D), list order = position, front first
        self.rows = {}
        for group in GROUPS:
            self.rows[group] = []
        self.units = arcade.SpriteList()

        # Tree; opened entries (paths): collapsed, or opened at scenario and nation from the game
        self.build_tree()
        self.tree_open = set()
        if nation is not None:
            self.tree_open = {(scenario,), (scenario, nation)}
        self.tree_scroll = 0

        # Save bar: scenario of the allocation and name field as in the lobby (transparent, bold)
        self.save_scenario = scenario
        self.manager = arcade.gui.UIManager()
        input_style = arcade.gui.widgets.text.UIInputTextStyle(bg=(0, 0, 0, 0), border=None, border_width=0)
        self.name_widget = arcade.gui.UIInputText(
            font_name=("calibri", "arial"), # default font of the editor texts
            font_size=13,
            border_width=0,
            style={state: input_style for state in ["normal", "hover", "focus", "press", "disabled", "invalid"]}
        )
        self.name_widget.doc.set_style(0, 0, {"weight": "bold"})
        self.place_name_widget()
        self.manager.add(self.name_widget)

        # Scrolling of the rows
        self.scroll_x = 0
        self.scroll_y = 0
        self.shift_held = False

        # Selected units (each click adds or removes one)
        self.selected = []
        self.pressed_card = None
        self.pressed_was_selected = False

        # Unit under the mouse and mouse cursor
        self.hover_card = None
        self.hand_cursor = False

        # Board texture and corner frame of selected units, as in the game
        self.board_texture = arcade.load_texture("assets/boardelements/board.texture.png")
        self.selection_overlay = arcade.Sprite("assets/overlays/unit.overlay.png")

        # Built texts by content (building one is slow)
        self.text_cache = {}

        # Dragging: units, a tree entry or a whole row
        self.dragged_cards = []
        self.dragged_node = None
        self.dragged_row = None
        self.press_position = (0, 0)
        self.mouse_position = (0, 0)



    # ──[ Tree ]───────────────────────────────────────────────────────────────

    def build_tree(self):

        # Entries as (label, path, unit_ids, kind), path = keys from the top, kind = folder, allocation or unit
        self.tree = []
        for scenario in SCENARIOS:
            scenario_ids = []
            for nation in NATIONS:
                scenario_ids.extend(self.scenarios[scenario]["units"][nation])
            self.tree.append(("Scenario " + scenario, (scenario,), scenario_ids, "folder"))
            for nation, nation_label in NATIONS.items():
                unit_ids = self.scenarios[scenario]["units"][nation]
                self.tree.append((nation_label, (scenario, nation), unit_ids, "folder"))
                self.add_tree_allocations(scenario, nation)
                for unit_id in unit_ids:
                    label = unit_id + "  " + self.unit_table.loc[unit_id, "name"]
                    self.tree.append((label, (scenario, nation, unit_id), [unit_id], "unit"))

        # DYO: all units of each nation, by kind
        self.tree.append(("DYO", ("DYO",), list(self.unit_table.index), "folder"))
        for nation, nation_label in NATIONS.items():
            nation_table = self.unit_table[self.unit_table["nation"] == nation]
            kinds = {"Soldiers": [], "Ordnance": [], "AFVs": []}
            for unit_id, row in nation_table.iterrows():
                kinds[row["kind"]].append(unit_id)
            self.tree.append((nation_label, ("DYO", nation), list(nation_table.index), "folder"))
            self.add_tree_allocations("DYO", nation)
            for kind, unit_ids in kinds.items():
                self.tree.append((kind, ("DYO", nation, kind), unit_ids, "folder"))
                for unit_id in unit_ids:
                    label = unit_id + "  " + self.unit_table.loc[unit_id, "name"]
                    self.tree.append((label, ("DYO", nation, kind, unit_id), [unit_id], "unit"))



    def add_tree_allocations(self, scenario, nation):

        # Saved allocations of a scenario and nation, before its units
        allocations = self.allocations.get("scenario " + scenario, {}).get(nation, {})
        for name, groups in allocations.items():
            unit_ids = []
            for group_ids in groups.values():
                unit_ids.extend(group_ids)
            self.tree.append(("■ " + name, (scenario, nation, name), unit_ids, "allocation"))



    def tree_items(self):

        # Visible entries as (label, depth, path, unit_ids, kind): all entries above are open
        items = []
        for label, path, unit_ids, kind in self.tree:
            parents_open = all(path[:depth] in self.tree_open for depth in range(1, len(path)))
            if parents_open:
                items.append((label, len(path) - 1, path, unit_ids, kind))
        return items



    def tree_item_at(self, x, y):

        if x < self.window.width - TREE_WIDTH or y < SAVE_BAR_HEIGHT:
            return None
        index = int((self.window.height - 50 + self.tree_scroll - y) // TREE_LINE)
        items = self.tree_items()
        if 0 <= index < len(items):
            return items[index]
        return None



    def add_units(self, unit_ids, group):

        # Each unit only once, nothing added if an AFV would not stand alone
        placed = [card.id for card in self.units]
        new_ids = []
        for unit_id in unit_ids:
            if unit_id not in placed:
                new_ids.append(unit_id)
        if not self.fits_in_row(group, new_ids):
            return
        for unit_id in new_ids:
            card = UnitCard(unit_id, self.unit_table.loc[unit_id])
            card.position = self.mouse_position # start at the drop point
            self.rows[group].append(card)
            self.units.append(card)



    def fits_in_row(self, group, unit_ids):

        # An AFV forms its own group: in a row only alone
        row_ids = []
        for card in self.rows[group]:
            if card.id not in unit_ids:
                row_ids.append(card.id)
        row_ids.extend(unit_ids)
        for unit_id in row_ids:
            if self.unit_table.loc[unit_id, "kind"] == "AFVs" and len(row_ids) > 1:
                return False
        return True



    def toggle_tree(self, path):

        if path in self.tree_open:
            self.tree_open.remove(path)
        else:
            self.tree_open.add(path)



    # ──[ Allocation file ]────────────────────────────────────────────────────

    def load_allocation(self, path):

        # Saved allocation replaces the rows; saving under its name overwrites it
        scenario, nation, name = path
        groups = self.allocations["scenario " + scenario][nation][name]
        self.units.clear()
        self.selected = []
        for group in GROUPS:
            self.rows[group] = []
        for group, unit_ids in groups.items():
            self.add_units(unit_ids, group)
        self.save_scenario = scenario
        self.name_widget.text = name



    def save_allocation(self):

        # Rows as allocation of the units' nation (one with the same name is overwritten)
        name = self.name_widget.text.strip()
        if not self.units or not name:
            return
        nation = self.unit_table.loc[self.units[0].id, "nation"]
        groups = {}
        for group in GROUPS:
            if self.rows[group]:
                groups[group] = [card.id for card in self.rows[group]]
        scenario_allocations = self.allocations.setdefault("scenario " + self.save_scenario, {})
        nation_allocations = scenario_allocations.setdefault(nation, {})
        nation_allocations[name] = groups
        with open(ALLOCATION_FILE, "w", encoding="utf-8", newline="\r\n") as file:
            yaml.safe_dump(self.allocations, file, default_flow_style=None, sort_keys=False, allow_unicode=True, width=1000)

        # Saved allocation visible in the tree
        self.build_tree()
        self.tree_open.add((self.save_scenario,))
        self.tree_open.add((self.save_scenario, nation))
        self.name_widget.deactivate()



    # ──[ Layout ]─────────────────────────────────────────────────────────────

    def row_top(self, group):

        # Screen position, shifted by the vertical scrolling
        index = GROUPS.index(group)
        return self.window.height - 30 - index * (ROW_HEIGHT + ROW_GAP) + self.scroll_y



    def row_at(self, y):

        for group in GROUPS:
            top = self.row_top(group)
            if top - ROW_HEIGHT <= y <= top:
                return group
        return None



    def units_left(self):

        # Left edge of the first unit, shifted by the horizontal scrolling
        return 20 + STATS_WIDTH + UNIT_GAP + self.scroll_x



    def save_bar_rects(self):

        # Scenario buttons, name field and save button at the bottom of the tree
        left = self.window.width - TREE_WIDTH + 20
        right = self.window.width - 20
        scenario_rects = {}
        for index, scenario in enumerate(SCENARIOS + ["DYO"]):
            scenario_rects[scenario] = arcade.LBWH(left + index * (48 + 6), 64, 48, 28)
        name_rect = arcade.LBWH(left, 18, right - left - 96, 34)
        button_rect = arcade.LBWH(right - 88, 18, 88, 34)
        return scenario_rects, name_rect, button_rect



    def place_name_widget(self):

        # Text widget inside the drawn name field (the widget writes from its top edge)
        name_rect = self.save_bar_rects()[1]
        self.name_widget.rect = arcade.LBWH(name_rect.left + 8, name_rect.bottom + 6, name_rect.width - 16, 22)



    def drop_index(self, group, x):

        # Position in the row (without the dragged units) for a drop at x
        remaining = [card for card in self.rows[group] if card not in self.dragged_cards]
        index = round((x - self.units_left() - UNIT_WIDTH / 2) / (UNIT_WIDTH + UNIT_GAP))
        return min(max(index, 0), len(remaining))



    def layout_units(self):

        # Target places; dragged units stay at the mouse and leave a gap where they would drop
        x, y = self.mouse_position
        drop_group = None
        if self.dragged_cards and x < self.window.width - TREE_WIDTH:
            drop_group = self.row_at(y)

        for group in GROUPS:
            slot = 0
            gap_index = None
            if group == drop_group:
                gap_index = self.drop_index(group, x)
            for card in self.rows[group]:
                if card in self.dragged_cards:
                    continue
                if slot == gap_index:
                    slot += len(self.dragged_cards)
                card.target_left = self.units_left() + slot * (UNIT_WIDTH + UNIT_GAP)
                card.target_top = self.row_top(group) - 10
                slot += 1



    def on_update(self, delta_time):

        # Cards glide to their place, the one under the mouse slightly larger
        step = min(delta_time * MOVE_SPEED, 1)
        for card in self.units:
            enlarge = 1
            if card is self.hover_card:
                enlarge = HOVER_ENLARGE
            card.width = UNIT_WIDTH * enlarge
            card.height = UNIT_HEIGHT * enlarge
            if card in self.dragged_cards:
                continue
            target_x = card.target_left + UNIT_WIDTH / 2
            target_y = card.target_top - UNIT_HEIGHT / 2
            card.center_x += (target_x - card.center_x) * step
            card.center_y += (target_y - card.center_y) * step



    def clamp_scrolling(self):

        # Content moves left and up, but not past its end
        longest_row = max(len(row) for row in self.rows.values())
        content_width = STATS_WIDTH + longest_row * (UNIT_WIDTH + UNIT_GAP) + 40
        content_height = len(GROUPS) * (ROW_HEIGHT + ROW_GAP) + 30
        max_scroll_x = max(content_width - (self.window.width - TREE_WIDTH), 0)
        max_scroll_y = max(content_height - self.window.height, 0)
        self.scroll_x = min(max(self.scroll_x, -max_scroll_x), 0)
        self.scroll_y = min(max(self.scroll_y, 0), max_scroll_y)

        # Tree moves up, but not past its last entry
        tree_height = 50 + len(self.tree_items()) * TREE_LINE + 20 + SAVE_BAR_HEIGHT
        max_tree_scroll = max(tree_height - self.window.height, 0)
        self.tree_scroll = min(max(self.tree_scroll, 0), max_tree_scroll)



    # ──[ Drawing ]────────────────────────────────────────────────────────────

    def on_draw(self):

        self.clear(color=BACKGROUND_COLOR)
        screen = arcade.LBWH(0, 0, self.window.width, self.window.height)
        arcade.draw_texture_rect(self.board_texture, screen)

        # Row frames and units
        for group in GROUPS:
            top = self.row_top(group)
            arcade.draw_lrbt_rectangle_outline(20, self.window.width, top - ROW_HEIGHT, top, (255, 255, 255, 60), 1)
        x, y = self.mouse_position
        drop_group = self.row_at(y)
        dragging = self.dragged_cards or self.dragged_node is not None
        if dragging and drop_group is not None and x < self.window.width - TREE_WIDTH:
            top = self.row_top(drop_group)
            arcade.draw_lrbt_rectangle_filled(20, self.window.width, top - ROW_HEIGHT, top, DROP_COLOR)
        self.units.draw()

        # Hovered unit on top of its neighbours, corner frames on selected units
        if self.hover_card is not None:
            arcade.draw_sprite(self.hover_card)
        for card in self.selected:
            self.draw_selection_frame(card)

        # Stats blocks stay in place: the background strip beneath covers scrolled units
        arcade.draw_lrbt_rectangle_filled(0, 20 + STATS_WIDTH, 0, self.window.height, BACKGROUND_COLOR)
        self.window.ctx.scissor = (0, 0, 20 + STATS_WIDTH, self.window.height)
        arcade.draw_texture_rect(self.board_texture, screen)
        self.window.ctx.scissor = None
        for group in GROUPS:
            top = self.row_top(group)
            stats_rect = arcade.LBWH(20, top - ROW_HEIGHT, STATS_WIDTH, ROW_HEIGHT)
            if group == self.dragged_row:
                arcade.draw_rect_filled(stats_rect, (255, 255, 255, 40))
            arcade.draw_rect_outline(stats_rect, LINE_COLOR, 2)
            self.draw_row_header(group, top)

        # Dragged units on top, still with their frames
        for card in self.dragged_cards:
            arcade.draw_sprite(card)
            self.draw_selection_frame(card)

        # Tree on the right (not scrolled)
        tree_left = self.window.width - TREE_WIDTH
        arcade.draw_lrbt_rectangle_filled(tree_left, self.window.width, 0, self.window.height, PANEL_COLOR)
        for index, (label, depth, path, unit_ids, kind) in enumerate(self.tree_items()):
            y = self.window.height - 50 + self.tree_scroll - index * TREE_LINE - TREE_LINE / 2
            if kind == "folder":
                label = ("▾ " if path in self.tree_open else "▸ ") + label
            self.draw_text(label, tree_left + 20 + depth * 24, y, 16 - depth)

        # Save bar: scenario buttons, nation of the units, name field and save button
        scenario_rects, name_rect, button_rect = self.save_bar_rects()
        arcade.draw_lrbt_rectangle_filled(tree_left, self.window.width, 0, SAVE_BAR_HEIGHT, PANEL_COLOR)
        arcade.draw_line(tree_left, SAVE_BAR_HEIGHT, self.window.width, SAVE_BAR_HEIGHT, LABEL_COLOR)
        for scenario, rect in scenario_rects.items():
            if scenario == self.save_scenario:
                arcade.draw_rect_filled(rect, BADGE_COLOR)
                self.draw_text(scenario, rect.x, rect.y, 12, anchor_x="center")
            else:
                arcade.draw_rect_outline(rect, BADGE_COLOR, 1)
                self.draw_text(scenario, rect.x, rect.y, 12, LABEL_COLOR, anchor_x="center")
        nation_label = "No units"
        if self.units:
            nation_label = NATIONS[self.unit_table.loc[self.units[0].id, "nation"]]
        self.draw_text(nation_label, button_rect.right, scenario_rects["A"].y, 13, LABEL_COLOR, anchor_x="right")
        arcade.draw_rect_filled(name_rect, BACKGROUND_COLOR)
        if self.name_widget.active:
            arcade.draw_rect_outline(name_rect, arcade.color.WHITE, 1)
        elif not self.name_widget.text:
            self.draw_text("Name", name_rect.left + 10, name_rect.y, 13, LABEL_COLOR)
        arcade.draw_rect_filled(button_rect, BADGE_COLOR)
        self.draw_text("Save", button_rect.x, button_rect.y, 13, anchor_x="center")
        self.manager.draw()

        # Dragged tree entry follows the mouse
        if self.dragged_node is not None:
            x, y = self.mouse_position
            self.draw_text(self.dragged_node[0], x + 12, y, 16)



    def draw_row_header(self, group, top):

        cards = self.rows[group]
        points = sum(card.points for card in cards)

        # Group letter and headline
        self.draw_text(group, 32, top - 34, 36)
        self.draw_text(f"{len(cards)} Units  ·  {points} Pts", HEADER_TEXT_X, top - 24, 15)
        if not cards:
            return

        # Badges: leaders (red without one, not needed by an AFV), support weapons, ordnance and AFV
        badges = []
        for card in cards:
            if card.function in ("SL", "ASL"):
                badges.append((card.function, BADGE_COLOR))
        is_afv = cards[0].kind == "AFVs" # alone in its row
        if not badges and not is_afv:
            badges.append(("No leader", NO_LEADER_COLOR))
        support = sum(1 for card in cards if card.weapon in SUPPORT_WEAPONS)
        if support:
            badges.append((f"MG ×{support}", BADGE_COLOR))
        ordnance = sum(1 for card in cards if card.kind == "Ordnance")
        if ordnance:
            badges.append((f"Ord ×{ordnance}", BADGE_COLOR))
        if is_afv:
            badges.append(("AFV", BADGE_COLOR))
        x = HEADER_TEXT_X
        for label, color in badges:
            width = 14 + 8 * len(label)
            arcade.draw_lrbt_rectangle_filled(x, x + width, top - 60, top - 42, color)
            self.draw_text(label, x + 7, top - 51, 11)
            x += width + 6

        # Morale: average and one dot per unit (red low, white medium, blue high)
        morales = sorted((card.morale for card in cards), reverse=True)
        average = sum(morales) / len(morales)
        self.draw_text("Morale", 34, top - 84, 11, LABEL_COLOR)
        self.draw_text(f"{average:.1f}", 96, top - 84, 13)
        for index, morale in enumerate(morales):
            arcade.draw_circle_filled(140 + index * 11, top - 84, 4.5, MORALE_COLORS[morale], num_segments=16)

        # Firepower per range 0-5 as bars
        self.draw_text("Firepower", 34, top - 110, 11, LABEL_COLOR)
        bottom = top - ROW_HEIGHT + 22
        for distance in range(6):
            value = sum(card.firepower[distance] for card in cards)
            fill = min(value / FIREPOWER_FULL, 1)
            height = fill * BAR_MAX_HEIGHT
            x = 40 + distance * 42
            arcade.draw_lrbt_rectangle_filled(x, x + 26, bottom, bottom + height, BAR_COLOR)
            self.draw_text(str(value), x + 13, bottom + height + 9, 11, anchor_x="center")
            self.draw_text(str(distance), x + 13, bottom - 10, 10, LABEL_COLOR, anchor_x="center")



    def draw_selection_frame(self, card):

        # Corner frame as in the game, sized like the card (AFV images are larger)
        self.selection_overlay.position = card.position
        self.selection_overlay.width = card.width
        self.selection_overlay.height = card.height
        arcade.draw_sprite(self.selection_overlay)



    def draw_text(self, label, x, y, size, color=arcade.color.WHITE, anchor_x="left"):

        key = (label, size, color, anchor_x)
        if key not in self.text_cache:
            self.text_cache[key] = arcade.Text(label, 0, 0, color, size, anchor_x=anchor_x, anchor_y="center", bold=True)
        text = self.text_cache[key]
        text.position = (x, y)
        text.draw()



    # ──[ Input ]──────────────────────────────────────────────────────────────

    def on_mouse_press(self, x, y, button, modifiers):

        self.press_position = (x, y)
        self.mouse_position = (x, y)

        # Save bar: scenario buttons and save button (the name field handles its clicks itself)
        scenario_rects, name_rect, button_rect = self.save_bar_rects()
        for scenario, rect in scenario_rects.items():
            if rect.point_in_rect((x, y)):
                self.save_scenario = scenario
                return
        if button_rect.point_in_rect((x, y)):
            self.save_allocation()
            return

        # Tree entry
        item = self.tree_item_at(x, y)
        if item is not None:
            self.dragged_node = item
            return
        if x >= self.window.width - TREE_WIDTH:
            return

        # Stats block of a row (covers scrolled units)
        group = self.row_at(y)
        if group is not None and x <= 20 + STATS_WIDTH:
            self.dragged_row = group
            return

        # Click on the background clears the selection
        cards = arcade.get_sprites_at_point((x, y), self.units)
        if not cards:
            self.selected = []
            return
        card = cards[-1]

        # The unit joins the selection; all selected units are dragged
        self.pressed_was_selected = card in self.selected
        if not self.pressed_was_selected:
            self.selected.append(card)
        self.dragged_cards = list(self.selected)
        self.pressed_card = card



    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):

        self.mouse_position = (x, y)
        for card in self.dragged_cards:
            card.center_x += dx
            card.center_y += dy
        if self.dragged_cards:
            self.layout_units()



    def on_mouse_release(self, x, y, button, modifiers):

        in_tree = x >= self.window.width - TREE_WIDTH
        group = self.row_at(y)
        moved = abs(x - self.press_position[0]) + abs(y - self.press_position[1]) > 5

        # Tree entry: a click opens a folder or loads an allocation, a drop on a row adds its units
        if self.dragged_node is not None:
            label, depth, path, unit_ids, kind = self.dragged_node
            self.dragged_node = None
            if moved:
                if group is not None and not in_tree:
                    self.add_units(unit_ids, group)
            elif kind == "folder":
                self.toggle_tree(path)
            elif kind == "allocation":
                self.load_allocation(path)

        # Units: into a row at the drop position, back on the tree removes them
        if self.dragged_cards:
            cards = self.dragged_cards
            if moved:
                self.selected = []
            elif self.pressed_was_selected:
                self.selected.remove(self.pressed_card)

            dragged_ids = [card.id for card in cards]
            if moved and group is not None and not self.fits_in_row(group, dragged_ids):
                group = None # an AFV would not stand alone: the units glide back
            if moved and (in_tree or group is not None):
                for row in self.rows.values():
                    for card in cards:
                        if card in row:
                            row.remove(card)
            if moved and in_tree:
                for card in cards:
                    self.units.remove(card)
            elif moved and group is not None:
                index = self.drop_index(group, x)
                for offset, card in enumerate(cards):
                    self.rows[group].insert(index + offset, card)
            self.dragged_cards = []

        # Row: swap with the row it is dropped on
        if self.dragged_row is not None:
            source = self.dragged_row
            self.dragged_row = None
            if group is not None and group != source:
                self.rows[source], self.rows[group] = self.rows[group], self.rows[source]

        self.clamp_scrolling()
        self.layout_units()
        self.update_hover()



    def on_resize(self, width, height):

        # Layout follows the window (e.g. restored smaller after minimizing)
        self.clamp_scrolling()
        self.layout_units()
        self.place_name_widget()



    def on_show_view(self):

        self.manager.enable()



    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):

        # Wheel over the tree scrolls the tree
        if x >= self.window.width - TREE_WIDTH:
            self.tree_scroll -= scroll_y * 60
            self.clamp_scrolling()
            self.update_hover()
            return

        # Wheel: vertical, Shift+wheel or sideways: horizontal
        if scroll_x != 0:
            self.scroll_x += scroll_x * 60
        elif self.shift_held:
            self.scroll_x += scroll_y * 60
        else:
            self.scroll_y -= scroll_y * 60
        self.clamp_scrolling()
        self.layout_units()

        # Scrolling moves the cards at once (only dropped or swapped ones glide)
        for card in self.units:
            if card in self.dragged_cards:
                continue
            card.center_x = card.target_left + UNIT_WIDTH / 2
            card.center_y = card.target_top - UNIT_HEIGHT / 2
        self.update_hover()



    def on_mouse_motion(self, x, y, dx, dy):

        self.mouse_position = (x, y)
        self.update_hover()



    def update_hover(self):

        # Unit under the mouse by its place (enlarging must not change the hit area)
        x, y = self.mouse_position
        self.hover_card = None
        if 20 + STATS_WIDTH < x < self.window.width - TREE_WIDTH and not self.dragged_cards:
            for card in self.units:
                inside_x = card.target_left <= x <= card.target_left + UNIT_WIDTH
                inside_y = card.target_top - UNIT_HEIGHT <= y <= card.target_top
                if inside_x and inside_y:
                    self.hover_card = card

        # Hand cursor over units and tree entries
        hand_cursor = self.hover_card is not None or self.tree_item_at(x, y) is not None
        if hand_cursor != self.hand_cursor:
            self.hand_cursor = hand_cursor
            cursor = self.window.CURSOR_HAND if hand_cursor else self.window.CURSOR_DEFAULT
            self.window.set_mouse_cursor(self.window.get_system_mouse_cursor(cursor))



    def on_key_press(self, key, modifiers):

        if key in (arcade.key.LSHIFT, arcade.key.RSHIFT):
            self.shift_held = True

        # Name field (typing itself goes to the widget): Enter saves, Ctrl+A selects the text, Ctrl+V pastes
        if self.name_widget.active:
            if key in (arcade.key.ENTER, arcade.key.NUM_ENTER):
                self.save_allocation()
            elif key == arcade.key.A and modifiers & arcade.key.MOD_CTRL:
                self.name_widget.caret.mark = 0
                self.name_widget.caret.position = len(self.name_widget.text)
            elif key == arcade.key.V and modifiers & arcade.key.MOD_CTRL:
                clipboard_text = pyperclip.paste()
                cursor_pos = self.name_widget.caret.position
                current_text = self.name_widget.text
                self.name_widget.text = current_text[:cursor_pos] + clipboard_text + current_text[cursor_pos:]
                self.name_widget.caret.position = cursor_pos + len(clipboard_text)
            return

        # Delete removes the selected units, Ctrl+A selects all units in board order
        if key == arcade.key.DELETE:
            for card in self.selected:
                self.units.remove(card)
                for row in self.rows.values():
                    if card in row:
                        row.remove(card)
            self.selected = []
            self.clamp_scrolling()
            self.layout_units()
            self.update_hover()
        elif key == arcade.key.A and modifiers & arcade.key.MOD_CTRL:
            self.selected = []
            for group in GROUPS:
                self.selected.extend(self.rows[group])



    def on_key_release(self, key, modifiers):

        if key in (arcade.key.LSHIFT, arcade.key.RSHIFT):
            self.shift_held = False



# ──[ Main ]───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Scenario and nation to start with, e.g. from the game: python cardallocation.py B german
    scenario = "A"
    nation = None
    if len(sys.argv) == 3:
        scenario = sys.argv[1]
        nation = sys.argv[2]
    window = arcade.Window(WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_TITLE, resizable=True)
    window.show_view(EditorView(scenario, nation))
    arcade.run()
